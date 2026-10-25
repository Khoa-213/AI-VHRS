"""The technician's session key: login, short-lived key, silent renewal, refusal when the robot is held, release.
The backend is a fake (httpx.MockTransport). Nothing moves a robot."""
import json

import httpx
import pytest

from vhrs_agent.link import LinkClient
from vhrs_agent.session_key import SessionKeyError, SessionKeyProvider
from test_link import Clock, LinkBackend, make
from test_server_api import USERS


class SessionBackend(LinkBackend):
    def __init__(self, robots=(3,), in_use=False):
        super().__init__()
        self.robots, self.in_use = list(robots), in_use
        self.issued: list[str] = []
        self.released: list[str] = []
        self.logins = 0
        self.expire_access = False
        self.accepted_keys: set[str] = set()

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path.removeprefix("/api/v1")
        body = json.loads(req.content) if req.content else None
        if path == "/auth/login":
            self.logins += 1
            if body["password"] != "good":
                return httpx.Response(401, json={"error": {"code": "INVALID_CREDENTIALS", "message": "x", "details": None}})
            return httpx.Response(200, json={"access_token": f"acc{self.logins}", "refresh_token": "ref", "account": {"role": "TECHNICAL_STAFF"}})
        if path == "/auth/refresh":
            return httpx.Response(401, json={"error": {"code": "TOKEN_EXPIRED", "message": "x", "details": None}})
        if path.startswith("/technician/robot"):
            if self.expire_access:
                self.expire_access = False
                return httpx.Response(401, json={"error": {"code": "NOT_AUTHENTICATED", "message": "x", "details": None}})
            if path == "/technician/robot-status":
                return httpx.Response(200, json=[{"robot_id": r} for r in self.robots])
            if req.method == "POST" and path.endswith("/agent-session"):
                if self.in_use:
                    return httpx.Response(409, json={"error": {"code": "ROBOT_IN_USE", "message": "Robot đang do người khác điều khiển.", "details": None}})
                key = f"vhrs_ak_session{len(self.issued)}"
                self.issued.append(key)
                self.accepted_keys.add(key)
                USERS[key] = USERS["tech-token"]                                # the backend would treat it as this technician on /technician/*
                assert body["instance_id"]
                return httpx.Response(201, json={"robot_id": 3, "key": key, "key_prefix": key[:12], "expires_at": "2099-01-01T00:00:00Z", "renew_after_s": 100})
            if req.method == "DELETE":
                self.released.append(req.url.params["instance_id"])
                return httpx.Response(204)
        if path in ("/agent/sync",) or path.startswith("/agent/commands/"):
            key = req.headers.get("authorization", "")[7:]
            if key not in self.accepted_keys:
                return httpx.Response(401, json={"error": {"code": "INVALID_AGENT_KEY", "message": "x", "details": None}})
        return super().__call__(req)


def provider(be, clock=None, **kw):
    return SessionKeyProvider("https://be.test", "tech@x.vn", kw.pop("password", "good"), transport=httpx.MockTransport(be),
                              clock=clock or Clock(), **kw)


def test_start_logs_in_finds_the_robot_and_gets_a_key():
    be = SessionBackend()
    p = provider(be)
    key = p.start()
    assert key == "vhrs_ak_session0" and p.robot_id == 3 and be.logins == 1
    assert p.instance_id and len(p.instance_id) >= 8


def test_wrong_password_and_ambiguous_robot_stop_before_any_key():
    with pytest.raises(SessionKeyError) as e:
        provider(SessionBackend(), password="bad").start()
    assert e.value.code == "LOGIN_FAILED"
    with pytest.raises(SessionKeyError) as e2:
        provider(SessionBackend(robots=(3, 4))).start()
    assert e2.value.code == "ROBOT_AMBIGUOUS"
    assert provider(SessionBackend(robots=(3, 4)), robot_id=4).start()                      # chosen explicitly
    with pytest.raises(SessionKeyError) as e3:
        provider(SessionBackend(robots=())).start()
    assert e3.value.code == "NO_ROBOT"


def test_a_robot_held_by_someone_else_is_refused_not_taken():
    be = SessionBackend(in_use=True)
    with pytest.raises(SessionKeyError) as e:
        provider(be).start()
    assert e.value.code == "ROBOT_IN_USE" and e.value.status == 409 and be.issued == []


def test_the_key_renews_itself_with_the_same_instance_before_it_ends():
    be, clock = SessionBackend(), Clock()
    p = provider(be, clock)
    first = p.start()
    clock.t += 50
    assert p.current() == first and len(be.issued) == 1                                      # not yet
    clock.t += 60                                                                             # past renew_after_s (100)
    second = p.current()
    assert second != first and len(be.issued) == 2 and p.renewals == 1
    assert p.current() == second and len(be.issued) == 2


def test_a_failed_renewal_keeps_the_old_key_and_retries_later():
    be, clock = SessionBackend(), Clock()
    p = provider(be, clock)
    first = p.start()
    be.in_use = True
    clock.t += 110
    assert p.current() == first and p.renewals == 0                                          # could not renew: still using the old key
    be.in_use = False
    clock.t += 31
    assert p.current() != first and p.renewals == 1


def test_an_expired_access_token_is_replaced_silently():
    be = SessionBackend()
    p = provider(be)
    p.start()
    be.expire_access = True
    assert p.renew_now() is True and be.logins == 2


def test_release_gives_the_key_back():
    be = SessionBackend()
    p = provider(be)
    p.start()
    p.release()
    assert be.released == [p.instance_id]
    p.release()                                                                               # twice is harmless
    assert len(be.released) == 1


def link_with_provider(tmp_path, be, clock):
    svc, _, _, _ = make(tmp_path)
    svc.transport = httpx.MockTransport(be)
    p = provider(be, clock)
    p.start()
    return svc, LinkClient(svc, provider=p, transport=httpx.MockTransport(be), clock=clock), p


def test_the_link_uses_the_current_key_and_follows_a_renewal(tmp_path):
    be, clock = SessionBackend(), Clock()
    svc, link, p = link_with_provider(tmp_path, be, clock)
    link.tick()
    assert be.last_status["busy"] is False
    old = p._key
    clock.t += 120
    link.tick()                                                                               # renews, then syncs with the NEW key
    assert p._key != old and p._key in be.accepted_keys
    cid = be.send("LOAD")
    link.tick()
    assert be.results[cid]["ok"] is True                                                     # the answer also went out with the current key


def test_a_refused_key_is_replaced_and_the_next_sync_works(tmp_path):
    be, clock = SessionBackend(), Clock()
    svc, link, p = link_with_provider(tmp_path, be, clock)
    link.tick()
    be.accepted_keys.clear()                                                                  # the backend cut our key (restart, revoke)
    link.tick()                                                                               # refused -> asks for a new key
    assert p._key in be.accepted_keys
    link.tick()
    assert be.last_status["busy"] is False


def test_the_link_needs_exactly_one_credential(tmp_path):
    svc, _, _, _ = make(tmp_path)
    with pytest.raises(ValueError):
        LinkClient(svc)
    with pytest.raises(ValueError):
        LinkClient(svc, key="vhrs_ak_x", provider=object())
