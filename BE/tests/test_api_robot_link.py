"""Robot Agent link: per-robot key, durable commands pulled by the agent, live frames, agent acting as the job's technician.

Real database. The agent is simulated by the test (it calls the same HTTP routes the real agent calls); no robot is involved.
"""
import pytest

from app.services.robot_link import hub
from tests.test_api_orders import API, _sql
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_technician import CAL, T, _err, _job, _post
from tests.test_api_workshop import _user, cust, policy, staff, store, wcat  # noqa: F401

M = f"{API}/manager"
A = f"{API}/agent"


@pytest.fixture(autouse=True)
def fresh_hub():
    hub.reset()
    yield
    hub.reset()


def key_for(client, mgr, robot_id):
    r = client.post(f"{M}/robots/{robot_id}/agent-key", headers=mgr[0] if isinstance(mgr, tuple) else mgr)
    assert r.status_code == 201, r.text
    return r.json()["key"], {"Authorization": "Bearer " + r.json()["key"]}


def sync(client, ah, **body):
    r = client.post(f"{A}/sync", headers=ah, json={"status": {"mode": "SIM"}, **body})
    assert r.status_code == 200, r.text
    return r.json()


def _h(x):
    return x[0] if isinstance(x, tuple) else x


def test_key_is_manager_only_shown_once_and_revocable(client, mgr, robot, tech):
    key, ah = key_for(client, mgr, robot)
    assert key.startswith("vhrs_ak_") and len(key) > 30
    info = client.get(f"{M}/robots/{robot}/agent", headers=_h(mgr)).json()
    assert info["has_key"] and info["key_prefix"] == key[:12] and info["online"] is False
    assert "key" not in info
    assert client.post(f"{M}/robots/{robot}/agent-key", headers=_h(tech)).status_code == 403
    assert _sql("select count(*) from robot_agents where robot_id=:r and key_hash=:h", r=robot, h=key) == 0   # no plaintext stored
    assert sync(client, ah)["robot_id"] == robot
    key2, ah2 = key_for(client, mgr, robot)                                       # rotating revokes the old key
    assert client.post(f"{A}/sync", headers=ah, json={}).status_code == 401
    assert client.post(f"{A}/sync", headers=ah2, json={}).status_code == 200
    assert client.delete(f"{M}/robots/{robot}/agent-key", headers=_h(mgr)).status_code == 204
    r = client.post(f"{A}/sync", headers=ah2, json={})
    assert r.status_code == 401 and _err(r) == "INVALID_AGENT_KEY"
    assert client.post(f"{M}/robots/99999999/agent-key", headers=_h(mgr)).status_code == 404


def test_command_needs_an_online_agent_and_is_pulled_once(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    body = {"kind": "PREFLIGHT", "job_id": jid, "params": {"mode": "SIM"}}
    r = client.post(f"{T}/robot-commands", headers=tech[0], json=body)
    assert r.status_code == 409 and _err(r) == "AGENT_OFFLINE"                       # never queue for a robot nobody can reach
    sync(client, ah)                                                                  # the agent comes online
    r = client.post(f"{T}/robot-commands", headers=tech[0], json={**body, "idempotency_key": "k1"})
    assert r.status_code == 201 and r.json()["status"] == "PENDING"
    cid = r.json()["id"]
    again = client.post(f"{T}/robot-commands", headers=tech[0], json={**body, "idempotency_key": "k1"})
    assert again.status_code == 201 and again.json()["id"] == cid                     # a retried request is one command
    other = client.post(f"{T}/robot-commands", headers=tech[0], json={"kind": "LOAD", "job_id": jid, "idempotency_key": "k1"})
    assert other.status_code == 409 and _err(other) == "IDEMPOTENCY_KEY_REUSED"

    got = sync(client, ah)["commands"]
    assert [c["id"] for c in got] == [cid] and got[0]["kind"] == "PREFLIGHT" and got[0]["params"] == {"mode": "SIM"}
    assert sync(client, ah)["commands"] == []                                         # delivered once, never again
    st = client.get(f"{T}/robot-commands/{cid}", headers=tech[0]).json()
    assert st["status"] == "DELIVERED" and st["delivered_at"]

    res = client.post(f"{A}/commands/{cid}/result", headers=ah, json={"ok": True, "result": {"ok": True}})
    assert res.status_code == 200 and res.json()["status"] == "DONE" and res.json()["result"] == {"ok": True}
    assert client.post(f"{A}/commands/{cid}/result", headers=ah, json={"ok": False}).json()["status"] == "DONE"   # idempotent
    mine = client.get(f"{T}/jobs/{jid}/robot-commands", headers=tech[0]).json()
    assert [c["id"] for c in mine] == [cid]
    stranger = _user(client, "TECHNICAL_STAFF")
    assert client.get(f"{T}/robot-commands/{cid}", headers=stranger[0]).status_code == 404
    assert client.get(f"{T}/jobs/{jid}/robot-commands", headers=stranger[0]).status_code == 404


def test_validation_of_commands(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    post = lambda **b: client.post(f"{T}/robot-commands", headers=tech[0], json=b)   # noqa: E731
    assert post(kind="RUN", params={"mode": "SIM"}).status_code == 422                # RUN needs a job
    assert post(kind="DANCE", job_id=jid).status_code == 422
    assert _err(post(kind="DRY_RUN", job_id=jid, params={})) == "MODE_REQUIRED"
    assert _err(post(kind="RUN", job_id=jid, params={"mode": "REAL"})) == "AUTHORIZATION_REQUIRED"
    assert _err(post(kind="RUN", job_id=jid, params={"mode": "REAL", "authorization": "yes"})) == "AUTHORIZATION_REQUIRED"
    notyet = post(kind="RUN", job_id=jid, params={"mode": "SIM"})
    assert notyet.status_code == 409 and _err(notyet) == "JOB_STATE_CONFLICT"            # the job must be started (WRITING) first
    assert _err(post(kind="DRY_RUN", job_id=jid, params={"mode": "SIM"})) == "JOB_STATE_CONFLICT"      # still SCHEDULED, not PREPARING
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 200
    _post(client, tech, jid, "prepare", status=200)
    assert post(kind="RUN", job_id=jid, params={"mode": "SIM"}).status_code == 409          # PREPARING is still not WRITING
    _post(client, tech, jid, "calibration", CAL, status=201)
    _post(client, tech, jid, "simulation", {"passed": True}, status=200)
    assert post(kind="DRY_RUN", job_id=jid, params={"mode": "SIM"}).status_code == 201       # rehearsal is allowed while PREPARING
    _post(client, tech, jid, "start", status=200)
    ok = post(kind="RUN", job_id=jid, params={"mode": "REAL", "authorization": f"AUTHORIZE-{jid}-abcd1234"})
    assert ok.status_code == 201                                                       # the agent still checks the token and the on-site file
    _sql("update production_jobs set status='PAUSED' where id=:j returning 1", j=jid)
    assert post(kind="DRY_RUN", job_id=jid, params={"mode": "SIM"}).status_code == 201      # a pen-up rehearsal is allowed after an abort (PAUSED)
    assert post(kind="RUN", job_id=jid + 999999, params={"mode": "SIM"}).status_code == 404
    assert post(kind="STOP", robot_id=robot + 999999).status_code == 404
    stranger = _user(client, "TECHNICAL_STAFF")
    r = client.post(f"{T}/robot-commands", headers=stranger[0], json={"kind": "STOP", "robot_id": robot})
    assert r.status_code == 404                                                        # no job on this robot, no control of it


def test_stale_commands_expire_and_stop_goes_first(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    first = client.post(f"{T}/robot-commands", headers=tech[0], json={"kind": "PAUSE", "job_id": jid}).json()["id"]
    stop = client.post(f"{T}/robot-commands", headers=tech[0], json={"kind": "STOP", "job_id": jid}).json()["id"]
    old = client.post(f"{T}/robot-commands", headers=tech[0], json={"kind": "PREFLIGHT", "job_id": jid, "params": {"mode": "SIM"}}).json()["id"]
    _sql("update robot_commands set expires_at = now() - interval '1 second' where id=:i returning 1", i=old)
    got = [c["id"] for c in sync(client, ah)["commands"]]
    assert got == [stop, first]                                                        # STOP first; the stale one is not replayed
    assert client.get(f"{T}/robot-commands/{old}", headers=tech[0]).json()["status"] == "EXPIRED"
    r = client.post(f"{A}/commands/{old}/result", headers=ah, json={"ok": True})
    assert r.status_code == 409 and _err(r) == "COMMAND_NOT_DELIVERED"
    assert client.post(f"{A}/commands/{first}/result", headers=ah, json={"ok": False, "error_code": "BUSY", "message": "x"}).json()["status"] == "FAILED"


def test_manager_may_only_pause_resume_stop(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    r = client.post(f"{M}/robots/{robot}/robot-commands", headers=_h(mgr), json={"kind": "RUN", "job_id": jid, "params": {"mode": "SIM"}})
    assert r.status_code == 403
    r = client.post(f"{M}/robots/{robot}/robot-commands", headers=_h(mgr), json={"kind": "STOP"})
    assert r.status_code == 201 and r.json()["kind"] == "STOP"
    assert [c["kind"] for c in sync(client, ah)["commands"]] == ["STOP"]


def test_live_frames_and_scene(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    live = client.get(f"{T}/robots/{robot}/live", headers=tech[0]).json()
    assert live["agent_online"] is False and live["frames"] == [] and live["last_seq"] == 0
    sync(client, ah, frames=[{"joints_deg": [0, -30, 90, 0, 0, 0], "state": "IDLE"}, {"joints_deg": [1, -30, 90, 0, 0, 0], "state": "WRITING"}])
    live = client.get(f"{T}/robots/{robot}/live", headers=tech[0]).json()
    assert live["agent_online"] is True and live["mode"] == "SIM" and [f["seq"] for f in live["frames"]] == [1, 2]
    after = client.get(f"{T}/robots/{robot}/live", headers=tech[0], params={"after": 1}).json()
    assert [f["state"] for f in after["frames"]] == ["WRITING"] and after["last_seq"] == 2
    assert client.get(f"{M}/robots/{robot}/live", headers=_h(mgr)).json()["agent_online"] is True
    assert client.get(f"{T}/robots/{robot}/scene", headers=tech[0]).status_code == 404         # nothing loaded yet

    cid = client.post(f"{T}/robot-commands", headers=tech[0], json={"kind": "LOAD", "job_id": jid}).json()["id"]
    sync(client, ah)
    client.post(f"{A}/commands/{cid}/result", headers=ah, json={"ok": True, "result": {"scene": {"paper": {"w": 148}}}})
    sc = client.get(f"{T}/robots/{robot}/scene", headers=tech[0]).json()
    assert sc["job_id"] == jid and sc["scene"]["paper"]["w"] == 148
    stranger = _user(client, "TECHNICAL_STAFF")
    assert client.get(f"{T}/robots/{robot}/live", headers=stranger[0]).status_code == 404


def test_agent_key_acts_as_the_jobs_technician_on_technician_routes_only(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    pkg = client.get(f"{T}/jobs/{jid}/package", headers=ah)
    assert pkg.status_code == 200 and pkg.json()["job_id"] == jid                       # same answer the technician gets
    assert client.get(f"{T}/jobs/{jid}", headers=ah).status_code == 200
    me = client.get(f"{API}/me", headers=ah)
    assert me.status_code == 401 and _err(me) == "INVALID_AGENT_KEY"                    # not a general login
    assert client.get(f"{M}/robots/{robot}/agent", headers=ah).status_code == 401
    cmd = client.post(f"{T}/robot-commands", headers=ah, json={"kind": "STOP", "job_id": jid})
    assert cmd.status_code == 401                                                       # the agent cannot command itself
    other_oid, other_jid = _job(client, cust, staff, mgr, wcat, _sql_new_robot(), _user(client, "TECHNICAL_STAFF"))
    assert client.get(f"{T}/jobs/{other_jid}/package", headers=ah).status_code == 401    # another robot's job is out of reach
    r = client.post(f"{T}/alerts", headers=ah, json={"robot_id": robot, "code": "BACKEND_LINK_LOST"})
    assert r.status_code == 201 and r.json()["level"] == 3, r.text                      # reachable as the technician; orange, not red
    _sql("update production_jobs set status='CANCELLED' where id=:j returning 1", j=jid)
    gone = client.get(f"{T}/jobs/{jid}/package", headers=ah)
    assert gone.status_code == 401 and _err(gone) == "AGENT_HAS_NO_ACTIVE_JOB"


def _sql_new_robot():
    from tests.test_api_scheduling import _robot
    return _robot()


def test_view_ticket_gives_read_only_access_to_one_robot(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah, frames=[{"joints_deg": [0, 0, 0, 0, 0, 0], "state": "IDLE"}])
    r = client.post(f"{T}/robots/{robot}/view-ticket", headers=tech[0])
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["viewer_path"] == f"/viewer/robot.html?ticket={t['ticket']}" and t["expires_in"] == 3600
    live = client.get(f"{API}/viewer/{t['ticket']}/live")                                # no bearer token: the ticket is the credential
    assert live.status_code == 200 and live.json()["agent_online"] is True and live.json()["frames"][0]["state"] == "IDLE"
    assert client.get(f"{API}/viewer/{t['ticket']}/scene").status_code == 404           # nothing loaded yet
    bad = client.get(f"{API}/viewer/{t['ticket']}x/live")
    assert bad.status_code == 401 and _err(bad) == "INVALID_VIEW_TICKET"
    access = tech[0]["Authorization"].split(" ", 1)[1]
    assert _err(client.get(f"{API}/viewer/{access}/live")) == "INVALID_VIEW_TICKET"        # a login token is not a view ticket
    stranger = _user(client, "TECHNICAL_STAFF")
    assert client.post(f"{T}/robots/{robot}/view-ticket", headers=stranger[0]).status_code == 404
    assert client.post(f"{M}/robots/{robot}/view-ticket", headers=_h(mgr)).status_code == 201
    assert client.get(f"{API}/viewer/{t['ticket']}/live").headers["cache-control"] == "no-store"


def test_robot_model_is_served_from_storage_with_a_long_cache(client, store):
    from app.services import robot_view
    robot_view._cache.clear()
    assert _err(client.get(f"{API}/robot-model/fairino3_v6.urdf")) == "MODEL_NOT_UPLOADED"
    store.put(robot_view.MODEL_PREFIX + "fairino3_v6.urdf", b"<robot/>")
    store.put(robot_view.MODEL_PREFIX + "meshes/base_link.STL", b"solid x")
    r = client.get(f"{API}/robot-model/fairino3_v6.urdf")
    assert r.status_code == 200 and r.content == b"<robot/>" and "max-age=86400" in r.headers["cache-control"]
    m = client.get(f"{API}/robot-model/meshes/fairino3_v6/base_link.STL")
    assert m.status_code == 200 and m.content == b"solid x" and m.headers["content-type"] == "model/stl"
    assert client.get(f"{API}/robot-model/meshes/fairino3_v6/..%2Fsecret.txt").status_code == 404     # only STL names, never a path
    assert client.get(f"{API}/robot-model/meshes/fairino3_v6/x.txt").status_code == 404
    robot_view._cache.clear()


def test_the_viewer_page_is_static_and_embeddable_only_by_allowed_origins(client):
    page = client.get("/viewer/robot.html")
    assert page.status_code == 200 and "importmap" in page.text and "Chỉ xem" in page.text
    csp = page.headers["content-security-policy"]
    assert "frame-ancestors 'self'" in csp and "https://cdn.jsdelivr.net" in csp and "x-frame-options" not in page.headers
    assert client.get("/viewer/twin.js").status_code == 200
    api = client.get(f"{API}/health")
    assert api.headers["x-frame-options"] == "DENY" and api.headers["cache-control"] == "no-store"


# ---------------------------------------------------------------- session keys (desktop app login, migration 0012)
def session_key(client, tech, robot, instance, expect=201):
    r = client.post(f"{T}/robots/{robot}/agent-session", headers=tech[0], json={"instance_id": instance})
    assert r.status_code == expect, r.text
    return r.json()


def bearer(key):
    return {"Authorization": "Bearer " + key}


def test_session_key_belongs_to_the_technician_expires_and_acts_only_as_them(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    k = session_key(client, tech, robot, "app-instance-0001")
    assert k["key"].startswith("vhrs_ak_") and k["renew_after_s"] == 10800 and k["key_prefix"] == k["key"][:12]
    row = _sql("select kind||'|'||account_id||'|'||instance_id from robot_agents where key_hash=:h", h=__import__("hashlib").sha256(k["key"].encode()).hexdigest())
    assert row == f"SESSION|{tech[1]}|app-instance-0001"
    assert sync(client, bearer(k["key"]))["robot_id"] == robot                              # works as an agent key
    assert client.get(f"{T}/jobs/{jid}/package", headers=bearer(k["key"])).status_code == 200   # and as THIS technician on /technician/*
    assert _err(client.post(f"{T}/robots/{robot}/agent-session", headers=bearer(k["key"]), json={"instance_id": "app-instance-0001"})) == "INVALID_AGENT_KEY"
    assert _err(client.post(f"{T}/robot-commands", headers=bearer(k["key"]), json={"kind": "STOP", "job_id": jid})) == "INVALID_AGENT_KEY"
    # who may ask
    stranger = _user(client, "TECHNICAL_STAFF")
    assert client.post(f"{T}/robots/{robot}/agent-session", headers=stranger[0], json={"instance_id": "app-instance-0002"}).status_code == 404
    assert client.post(f"{T}/robots/{robot}/agent-session", headers=tech[0], json={"instance_id": "x"}).status_code == 422
    # expiry is enforced even for a cached key
    _sql("update robot_agents set expires_at = now() - interval '1 second' where key_prefix=:p returning 1", p=k["key_prefix"])
    hub.reset()
    r = client.post(f"{A}/sync", headers=bearer(k["key"]), json={})
    assert r.status_code == 401 and _err(r) == "INVALID_AGENT_KEY"


def test_renewal_overlaps_so_there_is_no_gap(client, cust, staff, mgr, wcat, robot, tech):
    _job(client, cust, staff, mgr, wcat, robot, tech)
    a = session_key(client, tech, robot, "app-instance-0001")
    assert sync(client, bearer(a["key"]))                                                 # the agent is online on key A
    b = session_key(client, tech, robot, "app-instance-0001")                            # same instance asks again: renewal, not a takeover
    assert a["key"] != b["key"]
    assert sync(client, bearer(a["key"]))["robot_id"] == robot and sync(client, bearer(b["key"]))["robot_id"] == robot   # both work in the overlap
    left = _sql("select extract(epoch from (expires_at - now())) from robot_agents where key_prefix=:p", p=a["key_prefix"])
    assert 0 < float(left) <= 120                                                         # the old key ends within the grace period
    assert float(_sql("select extract(epoch from (expires_at - now())) from robot_agents where key_prefix=:p", p=b["key_prefix"])) > 3 * 3600


def test_one_controlling_app_per_robot_nobody_is_pushed_out(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    a = session_key(client, tech, robot, "app-instance-0001")
    sync(client, bearer(a["key"]))                                                         # app 1 is online
    r = client.post(f"{T}/robots/{robot}/agent-session", headers=tech[0], json={"instance_id": "app-instance-0002"})
    assert r.status_code == 409 and _err(r) == "ROBOT_IN_USE"                              # a second window / PC of the same person too
    assert sync(client, bearer(a["key"]))["robot_id"] == robot                             # the first one is untouched
    # a key just issued whose app has not connected yet still holds the robot
    _sql("update robot_agents set last_seen_at = null where key_prefix=:p returning 1", p=a["key_prefix"])
    hub.reset()
    assert _err(client.post(f"{T}/robots/{robot}/agent-session", headers=tech[0], json={"instance_id": "app-instance-0003"})) == "ROBOT_IN_USE"
    # an abandoned key (offline, not fresh) is replaced by a new login
    _sql("update robot_agents set created_at = now() - interval '5 minutes' where key_prefix=:p returning 1", p=a["key_prefix"])
    hub.reset()
    c = session_key(client, tech, robot, "app-instance-0003")
    assert client.post(f"{A}/sync", headers=bearer(a["key"]), json={}).status_code == 401           # the old app lost its key
    assert sync(client, bearer(c["key"]))["robot_id"] == robot
    # a run that is open cannot be taken over, even when the agent is offline
    _sql("""insert into robot_runs (run_id, job_id, robot_id, mode, created_by) values ('pytest-run-open', :j, :r, 'SIM', :u) returning 1""",
         j=jid, r=robot, u=tech[1])
    hub.reset()
    assert _err(client.post(f"{T}/robots/{robot}/agent-session", headers=tech[0], json={"instance_id": "app-instance-0009"})) == "ROBOT_IN_USE"
    assert session_key(client, tech, robot, "app-instance-0003")["key"]                    # the instance that holds it may renew mid-run
    rel = client.delete(f"{T}/robots/{robot}/agent-session", headers=tech[0], params={"instance_id": "app-instance-0003"})
    assert rel.status_code == 409 and _err(rel) == "RUN_OPEN"
    _sql("update robot_runs set ended_at = now() where run_id='pytest-run-open' returning 1")
    assert client.delete(f"{T}/robots/{robot}/agent-session", headers=tech[0], params={"instance_id": "app-instance-0003"}).status_code == 204
    hub.reset()
    assert client.post(f"{A}/sync", headers=bearer(c["key"]), json={}).status_code == 401           # released keys are dead


def test_a_workstation_key_from_the_manager_also_holds_the_robot(client, cust, staff, mgr, wcat, robot, tech):
    _job(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)                                                                        # the Manager-keyed agent is online
    r = client.post(f"{T}/robots/{robot}/agent-session", headers=tech[0], json={"instance_id": "app-instance-0001"})
    assert r.status_code == 409 and _err(r) == "ROBOT_IN_USE"
    info = client.get(f"{M}/robots/{robot}/agent", headers=_h(mgr)).json()
    assert info["has_key"] and info["session_keys"] == []
    # a Manager key is not touched by session keys, and revoking the robot's keys kills both kinds
    hub.reset()
    s = session_key(client, tech, robot, "app-instance-0001")
    assert sync(client, ah)["robot_id"] == robot and sync(client, bearer(s["key"]))["robot_id"] == robot
    assert client.delete(f"{M}/robots/{robot}/agent-key", headers=_h(mgr)).status_code == 204
    assert client.post(f"{A}/sync", headers=bearer(s["key"]), json={}).status_code == 401


def test_align_start_is_a_job_command_that_needs_the_authorization_for_real(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    post = lambda **b: client.post(f"{T}/robot-commands", headers=tech[0], json=b)   # noqa: E731
    assert post(kind="ALIGN_START", params={"mode": "SIM"}).status_code == 422                       # needs a job
    assert _err(post(kind="ALIGN_START", job_id=jid, params={})) == "MODE_REQUIRED"
    assert _err(post(kind="ALIGN_START", job_id=jid, params={"mode": "REAL"})) == "AUTHORIZATION_REQUIRED"
    ok = post(kind="ALIGN_START", job_id=jid, params={"mode": "REAL", "authorization": f"AUTHORIZE-{jid}-abcd1234"})
    assert ok.status_code == 201 and ok.json()["kind"] == "ALIGN_START"
    assert [c["kind"] for c in sync(client, ah)["commands"]] == ["ALIGN_START"]
    mgr_try = client.post(f"{M}/robots/{robot}/robot-commands", headers=_h(mgr), json={"kind": "ALIGN_START", "job_id": jid, "params": {"mode": "SIM"}})
    assert mgr_try.status_code == 403                                                                  # a Manager only pauses/resumes/stops
