"""Chat, Phase 4f: the order card, the conversation lists, the unread badge and the "nobody has claimed the order" alert.

Real database. Chat itself (text, images, permissions) is covered in test_api_workshop.py; here only what was added.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.order import OrderStatus
from app.services import messages as messages_service
from tests.conftest import auth
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import (W, _accepted, _err, _ot3, _user, cust, manager, policy, staff, store,  # noqa: F401
                                     wcat)


def _msgs(oid):
    return f"{API}/orders/{oid}/messages"


def _card(client, headers, oid, expect=201):
    r = client.post(_msgs(oid), headers=headers, json={"kind": "ORDER_CARD"})
    assert r.status_code == expect, r.text
    return r.json()


def _say(client, headers, oid, text="Xin chào"):
    r = client.post(_msgs(oid), headers=headers, json={"body": text})
    assert r.status_code == 201, r.text
    return r.json()


def _convs(client, headers, scope="me", **params):
    r = client.get(f"{API}/{scope}/conversations", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _unread(client, headers, scope="me"):
    r = client.get(f"{API}/{scope}/conversations/unread-count", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["unread"]


@pytest.fixture
def alerts(monkeypatch):
    """Records every notification the chat sends instead of only logging it."""
    sent = []
    monkeypatch.setattr(messages_service.notifications, "notify", lambda **kw: sent.append(kw))
    return sent


# ---- the order card ---------------------------------------------------------------------------------------------------
def test_customer_sends_the_order_card_and_both_sides_see_it(client, cust, staff, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat, qty=3)
    c = _card(client, cust, oid)
    assert c["kind"] == "ORDER_CARD" and c["mine"] is True and c["body"] is None and c["attachments"] == []
    code = _sql("select code from orders where id=:o", o=oid)
    assert c["order_card"] == {"code": code, "order_type": "OT3_TEMPLATE", "order_status": "ACCEPTED", "quantity": 3,
                               "total_amount": None}
    for who in (cust, sh):
        items = client.get(_msgs(oid), headers=who).json()["items"]
        assert [(m["kind"], m["order_card"]["code"] if m["order_card"] else None) for m in items] == [("ORDER_CARD", code)]
    assert [m["mine"] for m in client.get(_msgs(oid), headers=sh).json()["items"]] == [False]
    assert client.get(_msgs(oid), headers=sh).json()["unread"] == 1            # a card counts as a message for the other side
    text = _say(client, cust, oid)
    assert text["kind"] == "TEXT" and text["order_card"] is None               # plain messages are unchanged


def test_the_card_always_shows_the_order_as_it_is_now(client, cust, staff, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat, qty=2)
    _card(client, cust, oid)
    _sql("update orders set quantity=9, total_amount=123000 where id=:o returning 1", o=oid)
    card = client.get(_msgs(oid), headers=sh).json()["items"][0]["order_card"]
    assert card["quantity"] == 9 and card["total_amount"] == "123000"


def test_asking_for_the_card_again_within_ten_minutes_returns_the_same_card(client, cust, staff, wcat, alerts):
    sh, sid = staff
    oid = _accepted(client, cust, sh, wcat)
    first = _card(client, cust, oid)
    n_alerts = len(alerts)
    again = _card(client, cust, oid, expect=200)                               # 200: nothing new was created
    assert again["id"] == first["id"] and len(alerts) == n_alerts              # and nobody is alerted twice
    assert _sql("select count(*) from messages where order_id=:o and kind='ORDER_CARD'", o=oid) == 1
    _sql("update messages set created_at = now() - interval '11 minutes' where id=:i returning 1", i=first["id"])
    third = _card(client, cust, oid)                                           # the window has passed: a new card
    assert third["id"] != first["id"]
    assert _sql("select count(*) from messages where order_id=:o and kind='ORDER_CARD'", o=oid) == 2


def test_a_double_tap_makes_one_card(client, cust, staff, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat)
    token = cust["Authorization"]

    def tap(_):
        with TestClient(app) as c:
            return c.post(_msgs(oid), headers={"Authorization": token}, json={"kind": "ORDER_CARD"}).status_code

    with ThreadPoolExecutor(3) as pool:
        codes = sorted(pool.map(tap, range(3)))
    assert codes == [200, 200, 201]
    assert _sql("select count(*) from messages where order_id=:o and kind='ORDER_CARD'", o=oid) == 1


def test_sending_a_card_locks_the_order_row_so_simultaneous_requests_take_turns(client, cust, staff, wcat, monkeypatch):
    """The threads above rarely collide on a fast machine, so also pin the mechanism: the order row is locked before the check."""
    from app.repositories.orders import OrderRepository
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat)
    real_get, locked = OrderRepository.get, []

    def spy(self, order_id, *, lock=False):
        locked.append((order_id, lock))
        return real_get(self, order_id, lock=lock)

    monkeypatch.setattr(OrderRepository, "get", spy)
    _card(client, cust, oid)
    assert (oid, True) in locked


def test_only_the_customer_may_send_a_card_and_it_carries_nothing_else(client, cust, staff, manager, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat)
    for who in (sh, manager[0]):
        r = client.post(_msgs(oid), headers=who, json={"kind": "ORDER_CARD"})
        assert r.status_code == 403 and _err(r) == "CARD_CUSTOMER_ONLY"
    for extra in ({"body": "kèm chữ"}, {"attachments": [{"path": f"orders/{oid}/messages/1/x.png"}]}):
        r = client.post(_msgs(oid), headers=cust, json={"kind": "ORDER_CARD", **extra})
        assert r.status_code == 422 and _err(r) == "INVALID_CARD"
    assert client.post(_msgs(oid), headers=cust, json={"kind": "SOMETHING"}).status_code == 422
    assert _sql("select count(*) from messages where order_id=:o", o=oid) == 0
    other = auth(client, "CUSTOMER")                                           # a card is always about the sender's own order
    assert client.post(_msgs(oid), headers=other, json={"kind": "ORDER_CARD"}).status_code == 404


def test_card_rules_follow_the_chat_rules(client, cust, staff, wcat):
    sh, _ = staff
    draft = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT3_TEMPLATE", "quantity": 1}).json()["id"]
    assert _err(client.post(_msgs(draft), headers=cust, json={"kind": "ORDER_CARD"})) == "ORDER_NOT_SUBMITTED"
    oid = _ot3(client, cust, wcat)
    assert client.post(f"{W}/orders/{oid}/reject", headers=sh, json={"reason": "TOO_OLD"}).status_code == 200
    r = client.post(_msgs(oid), headers=cust, json={"kind": "ORDER_CARD"})
    assert r.status_code == 409 and _err(r) == "ORDER_CLOSED"                  # a rejected order takes no new card
    # a delivered order keeps its chat (complaints): only REJECTED and CANCELLED close it
    assert OrderStatus.COMPLETED not in messages_service.CLOSED
    assert messages_service.CLOSED == {OrderStatus.REJECTED, OrderStatus.CANCELLED}


# ---- the conversation lists -----------------------------------------------------------------------------------------------
def test_customer_inbox_lists_orders_with_messages_newest_first(client, cust, staff, wcat):
    sh, _ = staff
    a, b, quiet = (_accepted(client, cust, sh, wcat) for _ in range(3))
    _say(client, cust, a, "Tin đầu của A")
    _say(client, sh, b, "Xưởng nhắn B")
    _say(client, cust, a, "Tin sau của A")
    items = _convs(client, cust)["items"]
    assert [i["order_id"] for i in items] == [a, b] and quiet not in [i["order_id"] for i in items]
    ia, ib = items
    assert ia["last_message"]["body"] == "Tin sau của A" and ia["last_message"]["mine"] is True and ia["unread"] == 0
    assert ib["last_message"]["mine"] is False and ib["unread"] == 1 and ib["customer_name"] is None
    assert ia["code"] == _sql("select code from orders where id=:o", o=a)
    assert (ia["order_type"], ia["order_status"]) == ("OT3_TEMPLATE", "ACCEPTED")
    assert set(ia["last_message"]) == {"body", "kind", "has_attachment", "created_at", "mine"}
    _card(client, cust, b)                                                     # a card becomes the newest message of its order
    items = _convs(client, cust)["items"]
    assert items[0]["order_id"] == b and items[0]["last_message"]["kind"] == "ORDER_CARD" and items[0]["last_message"]["body"] is None
    assert not any(i["order_id"] in (a, b) for i in _convs(client, auth(client, "CUSTOMER"))["items"])    # other customers' chats


def test_inbox_pagination_and_attachment_flag(client, cust, staff, wcat):
    sh, _ = staff
    a, b = _accepted(client, cust, sh, wcat), _accepted(client, cust, sh, wcat)
    _say(client, cust, a)
    _say(client, cust, b)
    cust_id = _sql("select customer_id from orders where id=:o", o=a)
    _sql("""insert into messages (order_id, sender_id, body, attachments) values (:o, :s, null,
            '[{"path":"orders/x/messages/1/a.png","mime":"image/png"}]'::jsonb) returning id""", o=a, s=cust_id)
    p1 = _convs(client, cust, page=1, page_size=1)
    p2 = _convs(client, cust, page=2, page_size=1)
    assert p1["total"] == p2["total"] == 2 and p1["page_size"] == 1
    assert [p1["items"][0]["order_id"], p2["items"][0]["order_id"]] == [a, b]
    assert p1["items"][0]["last_message"]["has_attachment"] is True and p1["items"][0]["last_message"]["body"] is None
    assert p2["items"][0]["last_message"]["has_attachment"] is False
    assert client.get(f"{API}/me/conversations", headers=cust, params={"page_size": 101}).status_code == 422


def test_workshop_inbox_follows_who_may_see_the_order(client, cust, staff, manager, wcat):
    sh, sid = staff
    mine = _accepted(client, cust, sh, wcat)
    other_sh, _ = _user(client, "STAFF")
    theirs = _accepted(client, cust, other_sh, wcat)
    pool = _ot3(client, cust, wcat)                                            # submitted, nobody has claimed it
    for oid in (mine, theirs, pool):
        _say(client, cust, oid, f"Đơn {oid}")
    ids = {i["order_id"]: i for i in _convs(client, sh, "workshop")["items"]}
    assert mine in ids and pool in ids and theirs not in ids                   # own orders + the unclaimed pool, not a colleague's
    assert ids[mine]["customer_name"] == "Test CUSTOMER" and ids[mine]["unread"] == 1
    assert ids[pool]["last_message"]["body"] == f"Đơn {pool}"
    mids = {i["order_id"] for i in _convs(client, manager[0], "workshop", page_size=100)["items"]}
    assert {mine, theirs, pool} <= mids                                        # a Manager sees them all
    for denied in (cust, auth(client, "TECHNICAL_STAFF"), auth(client, "ADMIN")):
        assert client.get(f"{API}/workshop/conversations", headers=denied).status_code == 403
        assert client.get(f"{API}/workshop/conversations/unread-count", headers=denied).status_code == 403
    for denied in (sh, manager[0], auth(client, "TECHNICAL_STAFF"), auth(client, "ADMIN")):
        assert client.get(f"{API}/me/conversations", headers=denied).status_code == 403
        assert client.get(f"{API}/me/conversations/unread-count", headers=denied).status_code == 403
    for url in ("me/conversations", "me/conversations/unread-count", "workshop/conversations"):
        assert client.get(f"{API}/{url}").status_code == 401


def test_unread_badge_counts_across_orders_and_drops_when_read(client, cust, staff, wcat):
    sh, _ = staff
    a, b = _accepted(client, cust, sh, wcat), _accepted(client, cust, sh, wcat)
    assert _unread(client, cust) == 0
    staff_before = _unread(client, sh, "workshop")                              # the unclaimed pool is shared: count only the change
    _say(client, sh, a)
    _say(client, sh, a)
    _say(client, sh, b)
    _say(client, cust, b)                                                      # my own messages never count for me
    assert _unread(client, cust) == 3
    assert _unread(client, sh, "workshop") == staff_before + 1                 # only the customer's message in b
    assert client.post(f"{_msgs(a)}/read", headers=cust).json() == {"marked": 2}
    assert _unread(client, cust) == 1
    assert client.post(f"{_msgs(b)}/read", headers=cust).json() == {"marked": 1}
    assert _unread(client, cust) == 0
    assert [i["unread"] for i in _convs(client, cust)["items"]] == [0, 0]
    assert _unread(client, auth(client, "CUSTOMER")) == 0                      # someone else's inbox is unaffected


# ---- nobody has claimed the order: the managers are told ----------------------------------------------------------------------
def test_a_customer_message_on_an_unclaimed_order_alerts_every_active_manager(client, cust, staff, wcat, alerts):
    sh, sid = staff
    m1, m1_id = _user(client, "MANAGER")
    m2, m2_id = _user(client, "MANAGER")
    m3, m3_id = _user(client, "MANAGER")
    _sql("update accounts set status='DISABLED' where id=:i returning 1", i=m3_id)             # a disabled manager hears nothing
    pool = _ot3(client, cust, wcat)
    _say(client, cust, pool)
    told = {a["account_id"] for a in alerts if a["msg_code"] == "MESSAGE_UNCLAIMED" and a["order_id"] == pool}
    assert {m1_id, m2_id} <= told and m3_id not in told and sid not in told
    del alerts[:]
    _card(client, cust, pool)                                                  # a card is a message too
    assert {a["account_id"] for a in alerts if a["msg_code"] == "MESSAGE_UNCLAIMED"} >= {m1_id, m2_id}
    # claimed: only the assigned Staff is told, exactly as before
    oid = _accepted(client, cust, sh, wcat)
    del alerts[:]
    _say(client, cust, oid)
    assert [(a["account_id"], a["msg_code"]) for a in alerts] == [(sid, "MESSAGE")]
    del alerts[:]
    _say(client, sh, oid)
    cust_id = _sql("select customer_id from orders where id=:o", o=oid)
    assert [(a["account_id"], a["msg_code"]) for a in alerts] == [(cust_id, "MESSAGE")]


def test_staff_still_cannot_post_on_an_unclaimed_order(client, cust, staff, wcat):
    pool = _ot3(client, cust, wcat)
    r = client.post(_msgs(pool), headers=staff[0], json={"body": "Xin chào"})
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_CLAIMED"             # rule unchanged: the Manager answers (option a)
