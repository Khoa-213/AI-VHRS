"""Phase 4e: the notification center (FR-27, FR-57). Real database.

What is checked: the events of an order land in the customer's list (and by e-mail for the SRS "Email + in-app" ones), the
list / badge / read endpoints, chat notifications do not stack, nothing is stored or sent when the action rolls back, and the
Server-Sent Events stream.
"""
import threading

from app.db.session import _factory
from app.services import notifications as ns
from app.services.notification_stream import broker
from tests.conftest import auth
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _paid
from tests.test_api_workshop import _err, _user, cust, policy, staff, store, wcat  # noqa: F401

N = f"{API}/me/notifications"


def _me(client, h):
    return client.get(f"{API}/me", headers=h).json()


def _list(client, h, **params):
    r = client.get(N, headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_order_events_reach_the_customer_in_app_and_by_email(client, cust, staff, wcat, mailbox):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    me = _me(client, cust)
    page = _list(client, cust)
    mine = [n for n in page["items"] if n["order_id"] == oid]
    types = [n["type"] for n in mine]
    assert "QUOTATION_AVAILABLE" in types and "PAYMENT" in types                        # MSG10, then the deposit
    quote = next(n for n in mine if n["type"] == "QUOTATION_AVAILABLE")
    assert quote["msg_code"] == "MSG10" and quote["is_read"] is False and "chưa gồm phí giao hàng" in quote["body"]
    assert page["unread_count"] >= 2 and page["unread_count"] == client.get(f"{N}/unread-count", headers=cust).json()["unread_count"]
    # MSG10 goes by e-mail too; the deposit notice does not
    to_me = [m for m in mailbox if m[0] == me["email"]]
    assert any("báo giá" in subject for _, subject, _ in to_me) and not any("cọc" in s for _, s, _ in to_me)
    assert _sql("""select count(*) from notifications where order_id=:o and channel='EMAIL' and msg_code='MSG10'
                   and sent_at is not null""", o=oid) == 1
    assert _sql("select count(*) from notifications where order_id=:o and channel='IN_APP'", o=oid) == len(mine)


def test_reading_one_and_all(client, cust, staff, wcat):
    _paid(client, cust, staff[0], wcat)
    items = _list(client, cust)["items"]
    first = items[0]["id"]
    r = client.post(f"{N}/{first}/read", headers=cust)
    assert r.status_code == 200 and r.json()["is_read"] is True and r.json()["read_at"] is not None
    assert client.post(f"{N}/{first}/read", headers=cust).status_code == 200                # idempotent
    assert first not in [n["id"] for n in _list(client, cust, unread_only=True)["items"]]
    other = auth(client, "CUSTOMER")
    r = client.post(f"{N}/{first}/read", headers=other)
    assert r.status_code == 404 and _err(r) == "NOTIFICATION_NOT_FOUND"
    assert _list(client, other)["items"] == []
    r = client.post(f"{N}/read-all", headers=cust)
    assert r.status_code == 200 and r.json()["updated"] == len(items) - 1
    assert client.get(f"{N}/unread-count", headers=cust).json()["unread_count"] == 0


def test_paging_newest_first(client):
    h, uid = _user(client, "CUSTOMER")
    with _factory()() as s:
        for i in range(5):
            ns.notify(s, account_id=uid, order_id=None, msg_code="SOMETHING_NEW", code=f"P{i}")
        s.commit()
    page = _list(client, h, limit=2)
    assert len(page["items"]) == 2 and page["next_before_id"] == page["items"][-1]["id"]
    assert page["items"][0]["id"] > page["items"][1]["id"]
    rest = _list(client, h, limit=10, before_id=page["next_before_id"])
    assert len(rest["items"]) == 3 and rest["next_before_id"] is None


def test_chat_notifications_do_not_stack(client):
    h, uid = _user(client, "STAFF")
    with _factory()() as s:
        for _ in range(3):
            ns.notify(s, account_id=uid, order_id=None, msg_code="MESSAGE", code="X")
        s.commit()
    assert [n["type"] for n in _list(client, h)["items"]] == ["NEW_MESSAGE"]
    client.post(f"{N}/read-all", headers=h)
    with _factory()() as s:
        ns.notify(s, account_id=uid, order_id=None, msg_code="MESSAGE", code="X")
        s.commit()
    assert _list(client, h)["unread_count"] == 1                                        # a new one once the old was read


def test_nothing_is_stored_or_sent_when_the_action_rolls_back(client, mailbox):
    h, uid = _user(client, "CUSTOMER")
    with _factory()() as s:
        ns.notify(s, account_id=uid, order_id=None, msg_code="MSG12", code="RB")
        s.rollback()
    assert _list(client, h)["items"] == [] and mailbox == []
    with _factory()() as s:
        ns.notify(s, account_id=uid, order_id=None, msg_code="MSG12", code="OK")
        s.commit()
    assert len(_list(client, h)["items"]) == 1 and len(mailbox) == 1 and "OK" in mailbox[0][2]
    assert _sql("select count(*) from notifications where account_id=:a and channel='EMAIL' and sent_at is not null", a=uid) == 1


def test_a_broken_mailer_never_breaks_anything(client, monkeypatch):
    h, uid = _user(client, "CUSTOMER")

    class Broken:
        def send(self, *a):
            raise OSError("smtp down")
    monkeypatch.setattr(ns, "get_mailer", lambda: Broken())
    monkeypatch.setattr(ns.threading, "Thread", _Inline)
    with _factory()() as s:
        ns.notify(s, account_id=uid, order_id=None, msg_code="MSG12", code="X")
        s.commit()
    assert len(_list(client, h)["items"]) == 1
    assert _sql("select count(*) from notifications where account_id=:a and channel='EMAIL' and sent_at is null", a=uid) == 1


class _Inline:
    def __init__(self, target, args, **kw):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def test_the_stream_says_ready_then_pushes_new_notifications(client, monkeypatch):
    from app.api.v1 import notifications as notification_api
    monkeypatch.setattr(notification_api, "MAX_STREAM_S", 8.0)       # writing + committing on Supabase takes a second or more
    h, uid = _user(client, "TECHNICAL_STAFF")
    assert client.get(f"{N}/stream").status_code == 401

    def later():
        for _ in range(200):                                                           # wait for the connection to subscribe
            if broker.listeners(uid):
                break
            threading.Event().wait(0.05)
        with _factory()() as s:
            ns.notify(s, account_id=uid, order_id=None, msg_code="JOB_ASSIGNED", code="SSE-1",
                      slot_start="2026-11-05T01:30:00+00:00")
            s.commit()
    t = threading.Thread(target=later)
    t.start()
    r = client.get(f"{N}/stream", headers=h)
    t.join()
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    text = r.text
    assert 'event: ready\ndata: {"unread_count": 0}' in text
    assert "event: notification" in text and "SSE-1" in text and "08:30 05/11/2026" in text
    assert broker.listeners(uid) == 0                                                  # unsubscribed when the stream ended
