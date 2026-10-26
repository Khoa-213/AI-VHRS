"""Phase 4c-2b/c: the customer chooses a carrier service, the Staff create the waybill, the carrier's callbacks complete the order.

Real database and triggers; storage is the in-memory double. The default carriers are the simulated ones (CARRIER_MODE=mock);
one test switches to the real GHN adapter, whose HTTP calls go to httpx.MockTransport (proves the flow, not GHN itself).
"""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.integrations import carrier as cx
from app.integrations import locations as loc
from app.main import app
from tests.conftest import auth
from tests.test_api_delivery_final import ADDRESS, O, W, _final, _final_stage, _pickup, _put
from tests.test_api_orders import API, _sql
from tests.test_api_photos_acceptance import _ost
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import _err, cust, policy, staff, store, wcat  # noqa: F401
from tests.test_carriers_real import SECRET, _ghn_api
from tests.test_carriers_real import ghn as make_ghn

HOOK = f"{API}/webhooks/shipments"


@pytest.fixture
def carriers_on():
    cx.use_flags({"GHN": True})                          # the carrier's API counts as enabled (the DB flags stay untouched)
    yield
    cx.use_flags(None)
    cx.use_adapters(None)


def _choose(carrier="GHN", service="EXPRESS", **over):
    return {"method": "DELIVERY", "address": {**ADDRESS, **over}, "carrier": carrier, "service_code": service}


def _ready(client, cust, staff, mgr, wcat, robot, tech, store, body=None):
    """A paid DELIVERY order with the carrier service chosen: READY_TO_DELIVER. Returns (order id, final-payment response)."""
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    _put(client, cust, oid, body or _choose())
    r = _final(client, cust, oid).json()
    ok = client.post(f"{API}/payments/{r['payments'][0]['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert ok.status_code == 200 and ok.json()["order_status"] == "READY_TO_DELIVER", ok.text
    return oid, r


def _create(client, staff, oid, expect=201, **body):
    r = client.post(f"{W}/orders/{oid}/shipment", headers=staff[0], json=body)
    assert r.status_code == expect, r.text
    return r.json()


def _create_raw(client, staff, oid, **body):
    return client.post(f"{W}/orders/{oid}/shipment", headers=staff[0], json=body)


def _event(client, staff, sid, status, expect=200, reason=None):
    r = client.post(f"{W}/shipments/{sid}/mock-event", headers=staff[0], json={"status": status, "reason": reason})
    assert r.status_code == expect, r.text
    return r.json()


def _sstat(sid):
    return _sql("select status::text from shipments where id=:s", s=sid)


# ---- 4c-2b: what the customer can choose -----------------------------------------------------------------------
def test_customer_sees_each_carriers_services_and_the_choice_is_kept(client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    fee = Decimal(_sql("select value->>'FLAT_BOX_A5' from system_settings where key='fallback_shipping_fees'"))
    r = client.post(f"{O}/{oid}/delivery-quote", headers=cust, json={"address": ADDRESS})
    assert r.status_code == 200, r.text
    q = r.json()
    got = {(s["carrier"], s["service_code"]): s for s in q["services"]}
    assert set(got) == {("GHN", "STANDARD"), ("GHN", "EXPRESS")}                              # GHTK is no longer offered
    assert Decimal(got[("GHN", "STANDARD")]["fee"]) == fee and Decimal(got[("GHN", "EXPRESS")]["fee"]) == fee + fee * Decimal("0.4")
    assert all(s["mode"] == "MOCK" and s["is_fallback_fee"] is False and s["eta"] for s in q["services"])
    balance = Decimal(q["balance"])
    assert all(Decimal(s["total_due"]) == balance + Decimal(s["fee"]) for s in q["services"])
    assert q["chosen_service"] is None and q["package_type"] == "FLAT_BOX_A5"
    assert _sql("select delivery_method is null from orders where id=:o", o=oid)           # a quote saves nothing

    cheapest = min(q["services"], key=lambda s: Decimal(s["fee"]))
    r = _put(client, cust, oid, {"method": "DELIVERY", "address": ADDRESS})                  # no choice: the cheapest is taken
    assert (r.json()["shipping_carrier"], r.json()["shipping_service_code"]) == (cheapest["carrier"], cheapest["service_code"])

    r = _put(client, cust, oid, _choose("GHN", "EXPRESS")).json()
    assert (r["shipping_carrier"], r["shipping_service_code"]) == ("GHN", "EXPRESS") and r["shipping_eta"]
    assert _sql("select shipping_carrier::text || '/' || shipping_service_code from orders where id=:o", o=oid) == "GHN/EXPRESS"
    after = client.get(f"{O}/{oid}/delivery-quote", headers=cust).json()
    assert after["chosen_service"]["service_code"] == "EXPRESS"
    assert Decimal(after["options"]["DELIVERY"]["fee"]) == Decimal(got[("GHN", "EXPRESS")]["fee"])      # the fee of the chosen one

    r = client.put(f"{O}/{oid}/delivery", headers=cust, json=_choose("GHN", "ROAD"))
    assert r.status_code == 422 and _err(r) == "SERVICE_NOT_AVAILABLE"
    for half in ({"carrier": "GHN"}, {"service_code": "EXPRESS"}, {"carrier": "DHL", "service_code": "X"},
                 {"carrier": "GHTK", "service_code": "ROAD"}):
        assert client.put(f"{O}/{oid}/delivery", headers=cust, json={"method": "DELIVERY", "address": ADDRESS, **half}).status_code == 422
    assert _sql("select shipping_service_code from orders where id=:o", o=oid) == "EXPRESS"             # refused choices change nothing

    r = _put(client, cust, oid, _pickup()).json()                                            # collecting instead: no carrier
    assert r["shipping_carrier"] is None and r["shipping_service_code"] is None and r["shipping_eta"] is None
    assert _sql("select shipping_carrier is null and shipping_eta is null from orders where id=:o", o=oid)
    assert client.post(f"{O}/{oid}/delivery-quote", headers=auth(client, "CUSTOMER"), json={"address": ADDRESS}).status_code == 404


def test_carriers_whose_api_is_off_are_offered_at_the_fallback_fee(client, cust, staff, mgr, wcat, robot, tech, store):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)                   # flags stay as in the database: off
    fee = Decimal(_sql("select value->>'FLAT_BOX_A5' from system_settings where key='fallback_shipping_fees'"))
    q = client.post(f"{O}/{oid}/delivery-quote", headers=cust, json={"address": ADDRESS}).json()
    assert [(s["carrier"], s["service_code"], Decimal(s["fee"]), s["is_fallback_fee"], s["mode"], s["eta"]) for s in q["services"]] == [
        ("GHN", "STANDARD", fee, True, "FALLBACK", None)]
    assert q["is_fallback_fee"] is True and Decimal(q["options"]["DELIVERY"]["fee"]) == fee
    r = _put(client, cust, oid, _choose("GHN", "STANDARD")).json()
    assert (r["shipping_carrier"], r["shipping_service_code"]) == ("GHN", "STANDARD")
    bad = client.post(f"{O}/{oid}/delivery-quote", headers=cust, json={"address": {**ADDRESS, "ward_code": "999"}})
    assert bad.status_code == 422 and _err(bad) == "INVALID_ADDRESS"                       # a made-up ward is refused, not priced
    refused = client.put(f"{O}/{oid}/delivery", headers=cust, json=_choose("GHN", "STANDARD", province_code="1000000"))
    assert refused.status_code == 422 and _err(refused) == "INVALID_ADDRESS"


def test_the_customer_is_not_charged_a_fee_other_than_the_one_they_saw(client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    _put(client, cust, oid, _choose("GHN", "EXPRESS"))
    quoted = client.get(f"{O}/{oid}/delivery-quote", headers=cust).json()["chosen_service"]
    seen = Decimal(quoted["total_due"])
    r = client.post(f"{O}/{oid}/payments/final", headers=cust, json={"gateway": "VNPAY", "expected_total": str(seen - 100)})
    assert r.status_code == 409 and _err(r) == "FEE_CHANGED"
    details = r.json()["error"]["details"]
    assert Decimal(details["expected_total"]) == seen - 100 and Decimal(details["current_total"]) == seen
    assert _sql("select count(*) from payments where order_id=:o and type in ('FINAL','SHIPPING')", o=oid) == 0    # nothing was opened
    ok = client.post(f"{O}/{oid}/payments/final", headers=cust, json={"gateway": "VNPAY", "expected_total": str(seen)})
    assert ok.status_code == 201 and Decimal(ok.json()["total_due"]) == seen
    # the service the customer chose stops being offered: the payment is refused rather than priced differently
    _sql("update orders set shipping_service_code='GONE' where id=:o returning 1", o=oid)
    r = client.post(f"{O}/{oid}/payments/final", headers=cust, json={"gateway": "MOMO"})
    assert r.status_code == 409 and _err(r) == "SERVICE_NOT_AVAILABLE"


# ---- 4c-2c: waybill, callbacks, completion -----------------------------------------------------------------------
def test_staff_create_the_waybill_and_the_carrier_completes_the_order(client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    oid, final = _ready(client, cust, staff, mgr, wcat, robot, tech, store)
    paid_ship = Decimal(next(p["amount"] for p in final["payments"] if p["type"] == "SHIPPING"))

    s = _create(client, staff, oid, note="Giao giờ hành chính")
    assert s["carrier"] == "GHN" and s["service_code"] == "EXPRESS" and s["status"] == "CREATED" and s["mode"] == "MOCK"
    assert s["waybill_code"].startswith("MOCK-GHN-") and Decimal(s["fee"]) == paid_ship and s["tracking_url"] is None
    assert s["package_type"] == "FLAT_BOX_A5" and s["weight_g"] > 60 and s["is_fallback_fee"] is False
    assert s["to_address"]["street"] == ADDRESS["street"] and s["to_address"]["ward_code"] == ADDRESS["ward_code"]
    assert (s["to_address"]["province_name"], s["to_address"]["ward_name"]) == ("Hồ Chí Minh", "Phường Sài Gòn")
    assert "district_code" not in s["to_address"]
    assert s["label_link"].endswith("/label.pdf") and store.objects[s["label_link"].removeprefix("memory://")][:5] == b"%PDF-"
    assert _ost(oid) == "READY_TO_DELIVER"                                                      # nothing moves until the carrier does
    assert _err(_create_raw(client, staff, oid)) == "SHIPMENT_ALREADY_EXISTS"

    mine = client.get(f"{O}/{oid}/shipment", headers=cust).json()
    assert [x["id"] for x in mine] == [s["id"]] and mine[0]["waybill_code"] == s["waybill_code"] and "to_address" not in mine[0]
    assert client.get(f"{O}/{oid}/shipment", headers=auth(client, "CUSTOMER")).status_code == 404
    assert client.get(f"{W}/orders/{oid}/shipment", headers=mgr).json()[0]["id"] == s["id"]            # the Manager may look

    r = _event(client, staff, s["id"], "PICKED_UP")
    assert r["result"] == "PROCESSED" and r["order_status"] == "DELIVERING" and _ost(oid) == "DELIVERING"
    assert _sql("select picked_up_at is not null from shipments where id=:s", s=s["id"])
    assert _sql("""select count(*) from status_histories where order_id=:o and state_type='ORDER'
                   and from_status='READY_TO_DELIVER' and to_status='DELIVERING'""", o=oid) == 1
    assert _event(client, staff, s["id"], "PICKED_UP")["result"] == "ALREADY_PROCESSED"                # a repeat changes nothing
    assert _event(client, staff, s["id"], "CREATED")["result"] == "ALREADY_PROCESSED"                  # an older state is ignored
    assert _event(client, staff, s["id"], "DELIVERING")["result"] == "PROCESSED" and _ost(oid) == "DELIVERING"

    done = _event(client, staff, s["id"], "DELIVERED")
    assert done["result"] == "PROCESSED" and done["order_status"] == "COMPLETED" and _ost(oid) == "COMPLETED"
    assert _sql("select completed_at is not null from orders where id=:o", o=oid)
    assert _sql("select delivered_at is not null from shipments where id=:s", s=s["id"])
    assert _event(client, staff, s["id"], "FAILED")["result"] == "ALREADY_PROCESSED" and _ost(oid) == "COMPLETED"
    assert _sql("select count(*) from audit_logs where action='SHIPMENT_STATUS' and entity_id=:s", s=s["id"]) == 3
    assert client.post(f"{O}/{oid}/receipt", headers=cust).status_code == 200                           # the customer can confirm


def test_a_signed_callback_works_without_the_staff_button_and_bad_ones_are_refused(client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    oid, _ = _ready(client, cust, staff, mgr, wcat, robot, tech, store)
    s = _create(client, staff, oid)
    m = cx.MockCarrier("GHN", None)
    from app.models.ops import ShipmentStatus as S
    body = m.webhook_body(s["waybill_code"], S.PICKED_UP)
    sig = {cx.SIGNATURE_HEADER: m.sign(body)}
    assert client.post(f"{HOOK}/GHN", content=body).status_code == 401
    assert client.post(f"{HOOK}/GHN", content=body, headers={cx.SIGNATURE_HEADER: "00" * 32}).status_code == 401
    assert client.post(f"{HOOK}/GHN", content=body + b" ", headers=sig).status_code == 401                # altered after signing
    assert _ost(oid) == "READY_TO_DELIVER" and _sstat(s["id"]) == "CREATED"
    r = client.post(f"{HOOK}/GHN", content=body, headers=sig)
    assert r.status_code == 200 and r.json()["result"] == "PROCESSED" and _ost(oid) == "DELIVERING"
    other = m.webhook_body("MOCK-GHN-NOSUCHWAYBILL", S.DELIVERED)
    r = client.post(f"{HOOK}/GHN", content=other, headers={cx.SIGNATURE_HEADER: m.sign(other)})
    assert r.status_code == 404 and _err(r) == "SHIPMENT_NOT_FOUND"
    r = client.post(f"{HOOK}/GHTK", content=body, headers=sig)                                           # the right code, the wrong carrier
    assert r.status_code == 404 and _err(r) == "SHIPMENT_NOT_FOUND"
    junk = b'{"waybill_code": "x", "status": "BOGUS"}'
    r = client.post(f"{HOOK}/GHN", content=junk, headers={cx.SIGNATURE_HEADER: m.sign(junk)})
    assert r.status_code == 422 and _err(r) == "INVALID_WEBHOOK"
    assert client.post(f"{HOOK}/DHL", content=body, headers=sig).status_code == 422                       # not a carrier we know


def test_a_failed_delivery_keeps_the_order_and_a_new_waybill_can_be_made(client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    oid, _ = _ready(client, cust, staff, mgr, wcat, robot, tech, store)
    first = _create(client, staff, oid)
    _event(client, staff, first["id"], "PICKED_UP")
    assert _event(client, staff, first["id"], "FAILED", reason="Khách không nghe máy")["result"] == "PROCESSED"
    assert _sstat(first["id"]) == "FAILED" and _ost(oid) == "DELIVERING"                                  # the order stays DELIVERING
    assert _sql("select count(*) from audit_logs where action='SHIPMENT_STATUS' and entity_id=:s", s=first["id"]) == 2

    r = client.post(f"{W}/shipments/{first['id']}/cancel", headers=staff[0], json={"reason": "x"})       # only CREATED can be cancelled
    assert r.status_code == 409 and _err(r) == "SHIPMENT_NOT_CANCELLABLE"
    second = _create(client, staff, oid)                                                                  # ship again
    assert second["id"] != first["id"] and second["waybill_code"] != first["waybill_code"] and _ost(oid) == "DELIVERING"
    assert [x["id"] for x in client.get(f"{O}/{oid}/shipment", headers=cust).json()] == [second["id"], first["id"]]   # newest first

    late = _event(client, staff, first["id"], "DELIVERING")                                               # the old one reports late
    assert late["result"] == "PROCESSED" and _sstat(first["id"]) == "DELIVERING" and _ost(oid) == "DELIVERING"
    stale = _event(client, staff, first["id"], "DELIVERED")                                               # but it no longer drives the order
    assert stale["result"] == "PROCESSED" and _sstat(first["id"]) == "DELIVERED" and _ost(oid) == "DELIVERING"

    _event(client, staff, second["id"], "DELIVERING")
    assert _event(client, staff, second["id"], "DELIVERED")["order_status"] == "COMPLETED" and _ost(oid) == "COMPLETED"


def test_a_waybill_nobody_picked_up_can_be_cancelled_and_remade(client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    oid, _ = _ready(client, cust, staff, mgr, wcat, robot, tech, store)
    s = _create(client, staff, oid)
    assert client.post(f"{W}/shipments/{s['id']}/cancel", headers=staff[0], json={}).status_code == 422          # a reason is needed
    r = client.post(f"{W}/shipments/{s['id']}/cancel", headers=staff[0], json={"reason": "Sai địa chỉ"})
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED" and _sstat(s["id"]) == "CANCELLED"
    assert _sql("select count(*) from audit_logs where action='SHIPMENT_CANCEL' and entity_id=:s", s=s["id"]) == 1
    assert _err(client.post(f"{W}/shipments/{s['id']}/cancel", headers=staff[0], json={"reason": "again"})) == "SHIPMENT_NOT_CANCELLABLE"
    assert _event(client, staff, s["id"], "DELIVERED")["result"] == "ALREADY_PROCESSED" and _ost(oid) == "READY_TO_DELIVER"
    again = _create(client, staff, oid)
    assert again["id"] != s["id"] and again["status"] == "CREATED"
    _event(client, staff, again["id"], "PICKED_UP")
    assert _err(client.post(f"{W}/shipments/{again['id']}/cancel", headers=staff[0], json={"reason": "late"})) == "SHIPMENT_NOT_CANCELLABLE"


def test_a_delivery_can_complete_from_a_first_report_that_says_delivered(client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    oid, _ = _ready(client, cust, staff, mgr, wcat, robot, tech, store, body=_choose("GHN", "STANDARD"))
    s = _create(client, staff, oid)
    assert s["carrier"] == "GHN" and s["waybill_code"].startswith("MOCK-GHN-")
    r = _event(client, staff, s["id"], "DELIVERED")                                                       # nothing came before it
    assert r["order_status"] == "COMPLETED" and _ost(oid) == "COMPLETED"
    chain = _sql("""select string_agg(from_status || '>' || to_status, ',' order by id) from status_histories
                    where order_id=:o and state_type='ORDER' and to_status in ('DELIVERING','COMPLETED')""", o=oid)
    assert chain == "READY_TO_DELIVER>DELIVERING,DELIVERING>COMPLETED"


# ---- preconditions and who may do what ----------------------------------------------------------------------------------
def test_waybill_preconditions_and_permissions(client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    waiting = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)                           # still AWAITING_FINAL_PAYMENT
    assert _err(_create_raw(client, staff, waiting)) == "SHIPMENT_NOT_EXPECTED"
    oid, _ = _ready(client, cust, staff, mgr, wcat, robot, tech, store)

    for role in ("CUSTOMER", "TECHNICAL_STAFF", "MANAGER", "ADMIN"):                                    # only Staff write
        h = auth(client, role)
        assert client.post(f"{W}/orders/{oid}/shipment", headers=h, json={}).status_code == 403, role
        assert client.post(f"{W}/shipments/1/cancel", headers=h, json={"reason": "x"}).status_code == 403, role
        assert client.post(f"{W}/shipments/1/mock-event", headers=h, json={"status": "DELIVERED"}).status_code == 403, role
    assert client.post(f"{W}/orders/{oid}/shipment", json={}).status_code == 401
    other_staff = auth(client, "STAFF")                                                                  # not the assigned Staff
    assert client.post(f"{W}/orders/{oid}/shipment", headers=other_staff, json={}).status_code == 404

    _sql("update orders set shipping_carrier=null, shipping_service_code=null where id=:o returning 1", o=oid)
    assert _err(_create_raw(client, staff, oid)) == "SHIPPING_SERVICE_NOT_CHOSEN"
    _sql("update orders set shipping_carrier='GHN', shipping_service_code='EXPRESS' where id=:o returning 1", o=oid)

    s = _create(client, staff, oid)
    _sql("update shipments set waybill_code='REAL-123' where id=:s returning 1", s=s["id"])
    assert _err(client.post(f"{W}/shipments/{s['id']}/mock-event", headers=staff[0], json={"status": "DELIVERED"})) == "NOT_A_MOCK_SHIPMENT"
    assert client.post(f"{W}/shipments/999999999/mock-event", headers=staff[0], json={"status": "DELIVERED"}).status_code == 404
    assert client.post(f"{W}/shipments/999999999/cancel", headers=staff[0], json={"reason": "x"}).status_code == 404

    pick_oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)                           # a pickup order has no waybill
    _put(client, cust, pick_oid, _pickup())
    assert client.post(f"{O}/{pick_oid}/payments/final", headers=cust, json={"gateway": "VNPAY"}).status_code == 201
    assert _err(_create_raw(client, staff, pick_oid)) == "SHIPMENT_NOT_EXPECTED"


def test_the_fallback_flag_is_recorded_on_the_waybill(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, _ = _ready(client, cust, staff, mgr, wcat, robot, tech, store, body=_choose("GHN", "STANDARD"))      # flags off: fallback
    s = _create(client, staff, oid)
    assert s["is_fallback_fee"] is True and s["service_code"] == "STANDARD" and s["waybill_code"].startswith("MOCK-GHN-")


# ---- concurrency ------------------------------------------------------------------------------------------------------------
def test_two_staff_clicks_and_two_identical_callbacks_change_things_once(client, cust, staff, mgr, wcat, robot, tech, store, carriers_on):
    oid, _ = _ready(client, cust, staff, mgr, wcat, robot, tech, store)

    def create(_):
        with TestClient(app) as c:
            return c.post(f"{W}/orders/{oid}/shipment", headers=staff[0], json={}).status_code

    with ThreadPoolExecutor(2) as ex:
        codes = sorted(ex.map(create, range(2)))
    assert codes == [201, 409], codes
    assert _sql("select count(*) from shipments where order_id=:o", o=oid) == 1
    sid, waybill = _sql("select id from shipments where order_id=:o", o=oid), _sql("select waybill_code from shipments where order_id=:o", o=oid)

    from app.models.ops import ShipmentStatus as S
    m = cx.MockCarrier("GHN", None)
    body = m.webhook_body(waybill, S.DELIVERED)
    headers = {cx.SIGNATURE_HEADER: m.sign(body)}

    def hit(_):
        with TestClient(app) as c:
            return c.post(f"{HOOK}/GHN", content=body, headers=headers).json()["result"]

    with ThreadPoolExecutor(3) as ex:
        results = sorted(ex.map(hit, range(3)))
    assert results == ["ALREADY_PROCESSED", "ALREADY_PROCESSED", "PROCESSED"], results
    assert _ost(oid) == "COMPLETED" and _sstat(sid) == "DELIVERED"
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='COMPLETED'", o=oid) == 1
    assert _sql("select count(*) from audit_logs where action='SHIPMENT_STATUS' and entity_id=:s", s=sid) == 1


# ---- the real GHN adapter inside the whole flow (HTTP to a scripted fake) ------------------------------------------------------
@pytest.fixture
def real_ghn(monkeypatch):
    """CARRIER_MODE=sandbox with the GHN adapter and the address catalogue both replaced by test doubles."""
    s = get_settings()
    monkeypatch.setattr(s, "carrier_mode", "sandbox")
    monkeypatch.setattr(s, "carrier_webhook_secret", SECRET)
    loc.use_source(loc.MockLocations())
    cx.use_flags({"GHN": True})
    yield
    loc.use_source(None)
    cx.use_adapters(None)
    cx.use_flags(None)


def test_real_ghn_adapter_quotes_creates_and_completes(client, cust, staff, mgr, wcat, robot, tech, store, real_ghn):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    calls: list = []
    code = "GHN" + uuid.uuid4().hex[:10].upper()                                                # unique per run: waybill codes are unique
    cx.use_adapters({"GHN": make_ghn(_ghn_api(calls, order_code=code))})
    q = client.post(f"{O}/{oid}/delivery-quote", headers=cust, json={"address": ADDRESS}).json()
    assert [(x["carrier"], x["service_code"], x["mode"], x["is_fallback_fee"]) for x in q["services"]] == [("GHN", "2", "SANDBOX", False)]
    assert Decimal(q["services"][0]["fee"]) == 21300 and q["services"][0]["eta"]
    preview = next(c[3] for c in calls if c[1].endswith("/preview"))                              # priced on the address as named in the catalogue
    assert (preview["to_province_name"], preview["to_ward_name"], preview["is_new_to_address"]) == ("Hồ Chí Minh", "Phường Sài Gòn", True)

    _put(client, cust, oid, _choose("GHN", "2"))
    total = Decimal(client.get(f"{O}/{oid}/delivery-quote", headers=cust).json()["chosen_service"]["total_due"])
    r = client.post(f"{O}/{oid}/payments/final", headers=cust, json={"gateway": "VNPAY", "expected_total": str(total)}).json()
    assert Decimal(r["total_due"]) == total
    ok = client.post(f"{API}/payments/{r['payments'][0]['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert ok.json()["order_status"] == "READY_TO_DELIVER"

    ship = _create(client, staff, oid)
    assert ship["waybill_code"] == code and ship["service_code"] == "2" and ship["mode"] == "SANDBOX"
    assert ship["tracking_url"] == f"https://donhang.ghn.vn/?order_code={code}"
    assert Decimal(ship["fee"]) == Decimal(next(p["amount"] for p in r["payments"] if p["type"] == "SHIPPING"))
    created = next(c[3] for c in calls if c[1].endswith("/create"))
    order_code = _sql("select code from orders where id=:o", o=oid)
    assert created["service_type_id"] == 2 and created["cod_amount"] == 0 and created["client_order_code"] == f"{order_code}-1"
    assert ship["label_link"] == "https://ghn.example/a5/public-api/printA5?token=PRINTTOKEN"      # GHN's own print page, not a stored file
    assert _sql("select label_url is null from shipments where id=:s", s=ship["id"]) is True

    def hook(status, key=SECRET, **headers):
        body = json.dumps({"Type": "switch_status", "OrderCode": code, "Status": status, "Time": "2026-10-23T10:00:00Z"})
        return client.post(f"{HOOK}/GHN", params={"key": key} if key else {}, content=body, headers=headers)

    assert hook("picked", key="wrong").status_code == 401 and hook("picked", key=None).status_code == 401
    assert _ost(oid) == "READY_TO_DELIVER"
    assert hook("picked", key=None, **{"X-Webhook-Secret": SECRET}).json()["order_status"] == "DELIVERING"   # the secret in a header works too
    assert hook("some_unknown_status").json()["result"] == "IGNORED"
    assert hook("delivered").json()["order_status"] == "COMPLETED" and _ost(oid) == "COMPLETED"
    assert hook("delivered").json()["result"] == "ALREADY_PROCESSED"
    # the simulated carrier's own callbacks are not accepted while the real adapter is in charge
    from app.models.ops import ShipmentStatus as S
    m = cx.MockCarrier("GHN", None)
    body = m.webhook_body(code, S.DELIVERED)
    assert client.post(f"{HOOK}/GHN", content=body, headers={cx.SIGNATURE_HEADER: m.sign(body)}).status_code == 401
    assert client.post(f"{HOOK}/GHTK", params={"key": SECRET}, content="{}").status_code == 422        # GHTK is not supported any more


def test_ghn_refusing_a_cancel_keeps_the_waybill_and_a_remake_gets_a_new_reference(client, cust, staff, mgr, wcat, robot, tech, store, real_ghn):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    calls: list = []
    first, second = "GHN" + uuid.uuid4().hex[:10].upper(), "GHN" + uuid.uuid4().hex[:10].upper()
    state = {"code": first, "cancel": False}
    healthy = {}

    def handler(request):
        api = healthy.setdefault(state["code"], _ghn_api(calls, order_code=state["code"], cancel_result=state["cancel"]))
        return api(request)

    cx.use_adapters({"GHN": make_ghn(handler)})
    _put(client, cust, oid, _choose("GHN", "2"))
    r = _final(client, cust, oid).json()
    client.post(f"{API}/payments/{r['payments'][0]['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    ship = _create(client, staff, oid)
    assert ship["waybill_code"] == first

    refused = client.post(f"{W}/shipments/{ship['id']}/cancel", headers=staff[0], json={"reason": "Sai địa chỉ"})
    assert refused.status_code == 409 and _err(refused) == "CARRIER_CANCEL_REFUSED"            # GHN already has the parcel
    assert _sstat(ship["id"]) == "CREATED"                                                      # so nothing changed here
    assert _sql("select count(*) from audit_logs where action='SHIPMENT_CANCEL' and entity_id=:s", s=ship["id"]) == 0
    assert _err(_create_raw(client, staff, oid)) == "SHIPMENT_ALREADY_EXISTS"                  # and no second waybill is possible

    state["cancel"] = True
    healthy.pop(first)                                                                          # GHN now agrees to cancel
    done = client.post(f"{W}/shipments/{ship['id']}/cancel", headers=staff[0], json={"reason": "Sai địa chỉ"})
    assert done.status_code == 200 and _sstat(ship["id"]) == "CANCELLED"
    cancel = next(c[3] for c in calls if c[1].endswith("/cancel") and c[3].get("reason") == "Sai địa chỉ")
    assert cancel["reason_code"] == "GHN-CANCEL-OTHER" and cancel["order_codes"] == [first]

    state["code"] = second
    again = _create(client, staff, oid)
    order_code = _sql("select code from orders where id=:o", o=oid)
    refs = [c[3]["client_order_code"] for c in calls if c[1].endswith("/create")]
    assert again["waybill_code"] == second and refs == [f"{order_code}-1", f"{order_code}-2"]   # a new reference per attempt


def test_a_choice_made_while_the_carrier_api_was_down_gets_a_real_service_at_creation(client, cust, staff, mgr, wcat, robot, tech, store, real_ghn):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    calls: list = []
    code = "GHN" + uuid.uuid4().hex[:10].upper()
    healthy = _ghn_api(calls, order_code=code)
    state = {"down": True}

    def handler(request):
        import httpx
        return httpx.Response(503, text="down") if state["down"] else healthy(request)

    cx.use_adapters({"GHN": make_ghn(handler)})
    q = client.post(f"{O}/{oid}/delivery-quote", headers=cust, json={"address": ADDRESS}).json()
    assert [(x["carrier"], x["service_code"], x["is_fallback_fee"]) for x in q["services"]] == [("GHN", "STANDARD", True)]   # GHN failed
    _put(client, cust, oid, _choose("GHN", "STANDARD"))
    r = _final(client, cust, oid).json()
    client.post(f"{API}/payments/{r['payments'][0]['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    state["down"] = False                                                                 # GHN is back by the time the Staff ship
    ship = _create(client, staff, oid)
    assert ship["service_code"] == "2" and ship["waybill_code"] == code                   # the real service
