"""Phase 4c-1: how the customer receives the product, the final payment (G - D) + F_ship, and the hand-over at the workshop
(FR-18, FR-21, FR-23, BR-11, BR-12). Real database and triggers; storage is the in-memory double; the payment gateway is the
MOCK adapter (every payment says mode=MOCK, no money moves). Each test builds its own accepted order with its own robot.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import get_engine
from app.main import app
from tests.conftest import auth
from tests.test_api_orders import API, _sql
from tests.test_api_payments import GW, _code, _hook, _paid, _signed
from tests.test_api_photos_acceptance import _awaiting, _ost
from tests.test_api_scheduling import CAL, _at, _prod, mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import _err, _user, cust, manager, policy, staff, store, wcat  # noqa: F401

ADDRESS = {"receiver": "Nguyễn An", "phone": "0901234567", "street": "1 Lê Lợi", "province_code": "1000001",
           "ward_code": "1003506"}                                   # Hồ Chí Minh / Phường Sài Gòn (GHN two-level ids)
O = f"{API}/orders"
W = f"{API}/workshop"


# ---- helpers ----------------------------------------------------------------------------------------
def _final_stage(client, cust, staff, mgr, wcat, robot, tech, store, **kw):
    """An order the customer has accepted: it waits for the final payment."""
    oid, jid = _awaiting(client, cust, staff, mgr, wcat, robot, tech, store, **kw)
    assert client.post(f"{O}/{oid}/accept", headers=cust).status_code == 200
    assert _ost(oid) == "AWAITING_FINAL_PAYMENT"
    return oid


def _money(oid) -> tuple[Decimal, Decimal]:
    row = _sql("select total_amount::text || '|' || deposit_amount::text from orders where id=:o", o=oid)
    total, deposit = (Decimal(x) for x in row.split("|"))
    return total, deposit


def _fee(package: str) -> Decimal:
    return Decimal(_sql("select value->>:p from system_settings where key='fallback_shipping_fees'", p=package))


def _slot(h=9, minutes=60, days=1) -> dict:
    start = _at(days, h)
    return {"pickup_slot_start": start.isoformat(), "pickup_slot_end": (start + timedelta(minutes=minutes)).isoformat()}


def _pickup(phone="0901234567", **slot) -> dict:
    return {"method": "PICKUP", "contact_phone": phone, "receiver": "Nguyễn An", **(slot or _slot())}


def _delivery(**over) -> dict:
    return {"method": "DELIVERY", "address": {**ADDRESS, **over}}


def _put(client, cust, oid, body, expect=200):
    r = client.put(f"{O}/{oid}/delivery", headers=cust, json=body)
    assert r.status_code == expect, r.text
    return r


def _final(client, cust, oid, expect=201, gateway="VNPAY"):
    r = client.post(f"{O}/{oid}/payments/final", headers=cust, json={"gateway": gateway})
    assert r.status_code == expect, r.text
    return r


def _rows(oid, ptype=None):
    q = "select id, type::text t, amount::text a, status::text s, gateway_txn_id x, gateway_payload->>'group_txn' g from payments where order_id=:o"
    q += " and type = cast(:t as payment_type)" if ptype else ""
    with get_engine().connect() as c:
        return [dict(r) for r in c.execute(text(q + " order by id"), {"o": oid, "t": ptype}).mappings()]


def _sunday():
    d = datetime.now(CAL.tz)
    d = d + timedelta(days=(7 - d.isoweekday()) % 7 or 7)
    return d.replace(hour=9, minute=0, second=0, microsecond=0)


# ---- the wrong moment: nothing is available before acceptance --------------------------------------------
def test_final_payment_routes_refuse_an_order_that_is_not_waiting_for_it(client, cust, staff, wcat):
    oid, _, _ = _paid(client, cust, staff[0], wcat)                      # deposit paid: CONFIRMED, nothing accepted yet
    assert _ost(oid) == "CONFIRMED"
    for method, path, body in (("get", "delivery-quote", None), ("put", "delivery", _pickup()),
                               ("post", "payments/final", {"gateway": "VNPAY"})):
        r = client.request(method.upper(), f"{O}/{oid}/{path}", headers=cust, json=body)
        assert r.status_code == 409 and _err(r) == "FINAL_PAYMENT_NOT_EXPECTED", path
    r = client.post(f"{O}/{oid}/receipt", headers=cust)
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_DELIVERED"
    r = client.post(f"{W}/orders/{oid}/pickup/confirm", headers=staff[0], json={"phone": "0901234567"})
    assert r.status_code == 409 and _err(r) == "PICKUP_NOT_EXPECTED"
    assert _rows(oid, "FINAL") == [] and _rows(oid, "SHIPPING") == []


# ---- FR-21 / FR-23: the quote and the choice -------------------------------------------------------------
def test_quote_and_the_choice_of_delivery_are_validated(client, cust, staff, mgr, wcat, robot, tech, store):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    total, deposit = _money(oid)
    fee = _fee("FLAT_BOX_A5")                                              # the test paper is A5

    q = client.get(f"{O}/{oid}/delivery-quote", headers=cust).json()
    assert q["paper_size"] == "A5" and q["package_type"] == "FLAT_BOX_A5" and q["is_fallback_fee"] is True
    assert Decimal(q["balance"]) == total - deposit and q["chosen"] is None
    assert Decimal(q["options"]["PICKUP"]["fee"]) == 0 and Decimal(q["options"]["PICKUP"]["total_due"]) == total - deposit
    assert Decimal(q["options"]["DELIVERY"]["fee"]) == fee
    assert Decimal(q["options"]["DELIVERY"]["total_due"]) == total - deposit + fee          # (G - D) + F_ship

    assert _err(client.post(f"{O}/{oid}/payments/final", headers=cust, json={"gateway": "VNPAY"})) == "DELIVERY_NOT_CHOSEN"
    bad = [({"method": "DELIVERY"}, "VALIDATION_ERROR"),                                       # no address
           ({"method": "PICKUP", **_slot()}, "VALIDATION_ERROR"),                              # no contact phone
           ({"method": "PICKUP", "contact_phone": "12ab", **_slot()}, "VALIDATION_ERROR"),
           ({"method": "PICKUP", "contact_phone": "0901234567"}, "VALIDATION_ERROR"),          # no slot
           ({"method": "COD", "address": ADDRESS}, "VALIDATION_ERROR"),                        # no cash on delivery (LI-08)
           (_delivery(ward_code=""), "INVALID_ADDRESS"), (_delivery(street="  "), "INVALID_ADDRESS"),
           (_delivery(ward_code="999"), "INVALID_ADDRESS"),                                    # not in the catalogue
           (_delivery(province_code="1000000"), "INVALID_ADDRESS"),                            # the ward is not in that province
           (_pickup(**_slot(days=-2)), "SLOT_IN_PAST"),
           # _at() rolls a closed hour forward to opening time, so build the 07:00 start by hand
           (_pickup(pickup_slot_start=_at(1, 9).replace(hour=7).isoformat(),
                    pickup_slot_end=_at(1, 9).replace(hour=8).isoformat()), "OUTSIDE_WORKING_HOURS"),
           (_pickup(**_slot(h=16, minutes=120)), "OUTSIDE_WORKING_HOURS"),
           (_pickup(pickup_slot_start=_sunday().isoformat(),
                    pickup_slot_end=(_sunday() + timedelta(hours=1)).isoformat()), "OUTSIDE_WORKING_HOURS"),
           (_pickup(**_slot(minutes=5)), "INVALID_SLOT"), (_pickup(**_slot(minutes=600)), "INVALID_SLOT"),
           (_pickup(pickup_slot_start="2031-01-05T09:00:00", pickup_slot_end="2031-01-05T10:00:00"), "INVALID_SLOT"),  # no timezone
           (_pickup(**_slot(days=40)), "SLOT_TOO_FAR")]
    for body, code in bad:
        r = _put(client, cust, oid, body, expect=422)
        assert _err(r) == code, (code, r.text)
    assert _sql("select delivery_method is null from orders where id=:o", o=oid) is True            # none of them stuck

    stranger = auth(client, "CUSTOMER")
    for method, path, body in (("get", "delivery-quote", None), ("put", "delivery", _pickup()),
                               ("post", "payments/final", {"gateway": "VNPAY"}), ("post", "receipt", None)):
        r = client.request(method.upper(), f"{O}/{oid}/{path}", headers=stranger, json=body)
        assert r.status_code == 404 and _err(r) == "ORDER_NOT_FOUND", path

    r = _put(client, cust, oid, _pickup(phone="+84901234567", **_slot())).json()
    assert r["delivery_method"] == "PICKUP" and r["pickup_slot_start"] and r["delivery_address"]["phone"] == "0901234567"
    r = _put(client, cust, oid, _delivery(label="Nhà riêng")).json()                               # change of mind
    assert r["delivery_method"] == "DELIVERY" and r["pickup_slot_start"] is None and r["delivery_address"]["street"] == "1 Lê Lợi"
    assert client.get(f"{O}/{oid}/delivery-quote", headers=cust).json()["chosen"] == "DELIVERY"
    assert _sql("select count(*) from audit_logs where action='DELIVERY_CHOOSE' and entity_id=:o", o=oid) == 2


# ---- BR-12: collect at the workshop, pay the rest, hand over -------------------------------------------------
def test_pickup_order_is_paid_once_then_handed_over_at_the_workshop(client, cust, staff, manager, mgr, wcat, robot, tech, store):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    total, deposit = _money(oid)
    _put(client, cust, oid, _pickup())

    r = _final(client, cust, oid).json()
    assert r["payment_required"] is True and Decimal(r["total_due"]) == total - deposit and len(r["payments"]) == 1
    p = r["payments"][0]
    assert p["type"] == "FINAL" and Decimal(p["amount"]) == total - deposit and p["mode"] == "MOCK" and p["checkout_path"]
    assert _rows(oid, "SHIPPING") == []                                                     # BR-12: no shipping at the workshop
    assert _final(client, cust, oid).json()["payments"][0]["id"] == p["id"]                 # same intent: the open one is reused
    assert _ost(oid) == "AWAITING_FINAL_PAYMENT"

    code = _code(oid)
    r = client.post(f"{API}/webhooks/payments/VNPAY", content=_signed(p["gateway_txn_id"], code, int(total - deposit) + 100)[0],
                    headers={"X-Signature": _signed(p["gateway_txn_id"], code, int(total - deposit) + 100)[1]})
    assert r.status_code == 422 and _err(r) == "PAYMENT_MISMATCH" and _ost(oid) == "AWAITING_FINAL_PAYMENT"

    failed = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "FAILED"})
    assert failed.status_code == 200 and failed.json()["status"] == "FAILED" and _ost(oid) == "AWAITING_FINAL_PAYMENT"
    p2 = _final(client, cust, oid).json()["payments"][0]
    assert p2["id"] != p["id"]                                                              # a failed attempt is not reused
    ok = client.post(f"{API}/payments/{p2['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert ok.status_code == 200 and ok.json()["order_status"] == "READY_TO_DELIVER", ok.text
    assert (_ost(oid), _prod(oid)) == ("READY_TO_DELIVER", "FINISHED")
    assert [x["s"] for x in _rows(oid, "FINAL")] == ["FAILED", "SUCCESS"]
    assert _sql("select actor_id is null from status_histories where order_id=:o and to_status='READY_TO_DELIVER'", o=oid) is True
    body, sig = _signed(p2["gateway_txn_id"], code, int(total - deposit))
    again = _hook(client, "VNPAY", body, sig)
    assert again.json()["result"] == "ALREADY_PROCESSED" and _sql("select count(*) from status_histories where order_id=:o and to_status='READY_TO_DELIVER'", o=oid) == 1

    # paid: the choice and the payment are closed
    assert _err(_final(client, cust, oid, expect=409)) == "FINAL_ALREADY_PAID"
    assert _err(client.put(f"{O}/{oid}/delivery", headers=cust, json=_delivery())) == "FINAL_ALREADY_PAID"
    assert client.get(f"{O}/{oid}/delivery-quote", headers=cust).status_code == 409
    r = client.post(f"{O}/{oid}/receipt", headers=cust)
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_DELIVERED"                       # not handed over yet

    # hand-over: only the Staff of the order, only with the phone given at the time of the choice
    stranger = _user(client, "STAFF")
    assert client.post(f"{W}/orders/{oid}/pickup/confirm", headers=stranger[0], json={"phone": "0901234567"}).status_code == 404
    assert client.post(f"{W}/orders/{oid}/pickup/confirm", headers=manager[0], json={"phone": "0901234567"}).status_code == 403
    assert client.post(f"{W}/orders/{oid}/pickup/confirm", headers=cust, json={"phone": "0901234567"}).status_code == 403
    r = client.post(f"{W}/orders/{oid}/pickup/confirm", headers=staff[0], json={"phone": "0909999999"})
    assert r.status_code == 422 and _err(r) == "PICKUP_PHONE_MISMATCH" and _ost(oid) == "READY_TO_DELIVER"
    assert _sql("select count(*) from audit_logs where action='PICKUP_VERIFY_FAILED' and entity_id=:o", o=oid) == 1   # kept despite the 422
    assert client.post(f"{W}/orders/{oid}/pickup/confirm", headers=staff[0], json={"phone": "123"}).status_code == 422

    r = client.post(f"{W}/orders/{oid}/pickup/confirm", headers=staff[0], json={"phone": "+84901234567"})   # same number, other spelling
    assert r.status_code == 200 and r.json()["order_status"] == "COMPLETED" and r.json()["completed_at"], r.text
    assert (_ost(oid), _prod(oid)) == ("COMPLETED", "FINISHED")
    assert _sql("select actor_id from status_histories where order_id=:o and to_status='COMPLETED'", o=oid) == staff[1]
    again = client.post(f"{W}/orders/{oid}/pickup/confirm", headers=staff[0], json={"phone": "0901234567"})
    assert again.status_code == 409 and _err(again) == "PICKUP_NOT_EXPECTED"

    r = client.post(f"{O}/{oid}/receipt", headers=cust)                                     # UC-20: only a record
    assert r.status_code == 200 and r.json()["received_confirmed_at"] and r.json()["order_status"] == "COMPLETED"
    assert _err(client.post(f"{O}/{oid}/receipt", headers=cust)) == "RECEIPT_ALREADY_CONFIRMED"


# ---- FR-18: delivery = two rows paid by ONE transaction -------------------------------------------------------
def test_delivery_final_payment_is_two_rows_settled_together(client, cust, staff, mgr, wcat, robot, tech, store):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    total, deposit = _money(oid)
    fee = _fee("FLAT_BOX_A5")
    _put(client, cust, oid, _delivery())

    r = _final(client, cust, oid).json()
    assert r["payment_required"] is True and Decimal(r["total_due"]) == total - deposit + fee
    final, ship = r["payments"]
    assert (final["type"], ship["type"]) == ("FINAL", "SHIPPING")
    assert (Decimal(final["amount"]), Decimal(ship["amount"])) == (total - deposit, fee)
    assert ship["gateway_txn_id"] == final["gateway_txn_id"] + ":SHIP"                      # distinct ids, one transaction
    assert {x["g"] for x in _rows(oid)[-2:]} == {final["gateway_txn_id"]}
    assert all(p["checkout_path"] and p["mode"] == "MOCK" for p in r["payments"])
    assert [p["id"] for p in _final(client, cust, oid).json()["payments"]] == [final["id"], ship["id"]]      # reused as a pair

    code, txn = _code(oid), final["gateway_txn_id"]
    for amount in (int(total - deposit), int(fee), int(total - deposit + fee) - 100):       # a part is not the whole payment
        r = _hook(client, "VNPAY", *_signed(txn, code, amount))
        assert r.status_code == 422 and _err(r) == "PAYMENT_MISMATCH", amount
    assert _ost(oid) == "AWAITING_FINAL_PAYMENT" and {x["s"] for x in _rows(oid)[-2:]} == {"PENDING"}

    ok = client.post(f"{API}/payments/{ship['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})   # either row can be used
    assert ok.status_code == 200 and ok.json()["order_status"] == "READY_TO_DELIVER", ok.text
    assert [x["s"] for x in _rows(oid)[-2:]] == ["SUCCESS", "SUCCESS"]                       # both settled together
    assert _sql("select count(*) from payments where order_id=:o and status='SUCCESS' and type in ('FINAL','SHIPPING')", o=oid) == 2
    for t in (txn, txn + ":SHIP"):                                                            # a replay on either id changes nothing
        r = _hook(client, "VNPAY", *_signed(t, code, int(total - deposit + fee)))
        assert r.json()["result"] == "ALREADY_PROCESSED", t
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='READY_TO_DELIVER'", o=oid) == 1

    # a delivery order is not handed over at the counter, and nothing is "received" before it was delivered
    r = client.post(f"{W}/orders/{oid}/pickup/confirm", headers=staff[0], json={"phone": "0901234567"})
    assert r.status_code == 409 and _err(r) == "PICKUP_NOT_EXPECTED"
    assert client.post(f"{O}/{oid}/receipt", headers=cust).status_code == 409
    listing = client.get(f"{O}/{oid}/payments", headers=cust).json()
    assert [(x["type"], x["status"]) for x in listing if x["type"] != "DEPOSIT"] == [("FINAL", "SUCCESS"), ("SHIPPING", "SUCCESS")]


# ---- nothing left to pay, and changing the choice ---------------------------------------------------------------
def test_full_deposit_leaves_only_shipping_or_nothing_and_a_changed_choice_cancels_the_open_payment(
        client, cust, staff, mgr, wcat, robot, tech, store):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store, deposit_pct=100)
    total, deposit = _money(oid)
    assert total == deposit
    fee = _fee("FLAT_BOX_A5")

    _put(client, cust, oid, _delivery())
    r = _final(client, cust, oid).json()
    assert Decimal(r["total_due"]) == fee and [p["type"] for p in r["payments"]] == ["SHIPPING"]       # only the carrier is owed
    only = r["payments"][0]
    assert only["gateway_txn_id"] == only["gateway_txn_id"].split(":")[0]                  # a lone row keeps the plain id

    _put(client, cust, oid, _pickup())                                                       # now the customer collects instead
    assert _sql("select status::text from payments where id=:p", p=only["id"]) == "CANCELLED"
    late = _hook(client, "VNPAY", *_signed(only["gateway_txn_id"], _code(oid), int(fee)))    # the gateway still reports the old one
    assert late.status_code == 200 and late.json()["result"] == "IGNORED" and _ost(oid) == "AWAITING_FINAL_PAYMENT"

    r = _final(client, cust, oid).json()                                                     # 0 (balance) + 0 (no shipping)
    assert r["payment_required"] is False and Decimal(r["total_due"]) == 0 and r["payments"] == []
    assert r["order_status"] == "READY_TO_DELIVER" and _ost(oid) == "READY_TO_DELIVER"
    assert [x["s"] for x in _rows(oid) if x["t"] in ("FINAL", "SHIPPING")] == ["CANCELLED"]  # no payment row was invented
    assert _sql("select count(*) from audit_logs where action='FINAL_PAYMENT_NOT_REQUIRED' and entity_id=:o", o=oid) == 1
    assert _err(_final(client, cust, oid, expect=409)) == "FINAL_ALREADY_PAID"

    r = client.post(f"{W}/orders/{oid}/pickup/confirm", headers=staff[0], json={"phone": "0901234567"})
    assert r.status_code == 200 and r.json()["order_status"] == "COMPLETED"


# ---- concurrency -----------------------------------------------------------------------------------------------
def test_concurrent_final_payment_starts_and_webhooks_settle_exactly_once(client, cust, staff, mgr, wcat, robot, tech, store):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    total, deposit = _money(oid)
    fee = _fee("FLAT_BOX_A5")
    _put(client, cust, oid, _delivery())

    def start(_):
        with TestClient(app) as c:
            return [p["id"] for p in c.post(f"{O}/{oid}/payments/final", headers=cust, json={"gateway": "VNPAY"}).json()["payments"]]

    with ThreadPoolExecutor(3) as ex:
        ids = list(ex.map(start, range(3)))
    assert len({tuple(i) for i in ids}) == 1 and len(ids[0]) == 2                             # one pair, never three
    assert len([x for x in _rows(oid) if x["t"] in ("FINAL", "SHIPPING")]) == 2

    txn = _rows(oid, "FINAL")[0]["x"]
    body, sig = _signed(txn, _code(oid), int(total - deposit + fee))

    def fire(_):
        with TestClient(app) as c:
            return _hook(c, "VNPAY", body, sig).json()["result"]

    with ThreadPoolExecutor(4) as ex:
        results = sorted(ex.map(fire, range(4)))
    assert results == ["ALREADY_PROCESSED"] * 3 + ["PROCESSED"]
    assert _ost(oid) == "READY_TO_DELIVER"
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='READY_TO_DELIVER'", o=oid) == 1
    assert json.loads(body)["amount"] == int(total - deposit + fee)
