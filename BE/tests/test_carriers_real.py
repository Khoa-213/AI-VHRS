"""Carrier rules, the MOCK carrier, the GHN and GHTK adapters and the registry. No database, no network (httpx.MockTransport).

Like the payment adapters, GHN and GHTK are proven here only to be SELF-CONSISTENT: the requests are built and the answers read
the way the code says. They are not yet proven against the carriers' own sandboxes (see VERIFICATION STATUS in ghn.py/ghtk.py).
"""
import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.domain import carrier_rules as cr
from app.domain.carrier_rules import ServiceQuote
from app.integrations import carrier as cx
from app.integrations.ghn import GhnCarrier
from app.integrations.ghtk import GhtkCarrier
from app.integrations.payment_gateway import InvalidSignature, MalformedCallback
from app.models.ops import ShipmentStatus as S

SECRET = "carrier-secret"
GHN_TO = {"receiver": "Nguyễn An", "phone": "0901234567", "street": "1 Lê Lợi", "district_code": "1442", "ward_code": "20308"}
GHTK_TO = {**GHN_TO, "province_name": "Hồ Chí Minh", "district_name": "Quận 1", "ward_name": "Bến Nghé"}
PARCEL = cr.parcel_for("FLAT_BOX_A5", "A5", 120, 1, 400000)


# ===================================================================================== state machine and vocabularies
ALL = list(S)
EXPECTED_MOVES = {
    S.CREATED: {S.PICKED_UP, S.DELIVERING, S.DELIVERED, S.FAILED, S.RETURNED, S.CANCELLED},
    S.PICKED_UP: {S.DELIVERING, S.DELIVERED, S.FAILED, S.RETURNED},
    S.DELIVERING: {S.DELIVERED, S.FAILED, S.RETURNED},
    S.FAILED: {S.DELIVERING, S.DELIVERED, S.RETURNED},
    S.DELIVERED: set(), S.RETURNED: set(), S.CANCELLED: set(),
}


def test_every_waybill_move_is_decided():
    for old in ALL:
        for new in ALL:
            assert cr.can_move(old, new) == (new in EXPECTED_MOVES[old]), (old, new)
    for terminal in cr.TERMINAL:
        assert not any(cr.can_move(terminal, n) for n in ALL)


def test_what_a_waybill_status_means_for_the_order():
    assert cr.order_effect(S.PICKED_UP) == "DELIVERING" and cr.order_effect(S.DELIVERING) == "DELIVERING"
    assert cr.order_effect(S.DELIVERED) == "COMPLETED"
    for quiet in (S.CREATED, S.FAILED, S.RETURNED, S.CANCELLED):
        assert cr.order_effect(quiet) is None, quiet


def test_ghn_statuses():
    assert {k: cr.map_ghn_status(k) for k in ("ready_to_pick", "picking", "picked", "storing", "transporting", "delivering",
                                              "delivered", "delivery_fail", "waiting_to_return", "returned", "cancel",
                                              "lost", "damage")} == {
        "ready_to_pick": S.CREATED, "picking": S.CREATED, "picked": S.PICKED_UP, "storing": S.DELIVERING,
        "transporting": S.DELIVERING, "delivering": S.DELIVERING, "delivered": S.DELIVERED, "delivery_fail": S.FAILED,
        "waiting_to_return": S.FAILED, "returned": S.RETURNED, "cancel": S.CANCELLED, "lost": S.FAILED, "damage": S.FAILED}
    assert cr.map_ghn_status("  DELIVERED ") == S.DELIVERED and cr.map_ghn_status("nonsense") is None
    assert cr.map_ghn_status(None) is None and cr.map_ghn_status("") is None
    assert set(cr.GHN_STATUS.values()) <= set(S)


def test_ghtk_statuses():
    for sid, expected in ((-1, S.CANCELLED), (1, S.CREATED), (2, S.CREATED), (3, S.PICKED_UP), (4, S.DELIVERING),
                          (5, S.DELIVERED), (6, S.DELIVERED), (7, S.FAILED), (9, S.FAILED), (20, S.FAILED), (21, S.RETURNED)):
        assert cr.map_ghtk_status(sid) == expected and cr.map_ghtk_status(str(sid)) == expected, sid
    for informational in (123, 127, 128, 45, 49, 410, 999, "x", None):                  # shipper-reported ids: not applied
        assert cr.map_ghtk_status(informational) is None, informational


# ===================================================================================== the parcel and the services
def test_parcel_weight_and_box():
    p = cr.parcel_for("FLAT_BOX_A5", "A5", 120, 1, 400000)
    assert (p.length_cm, p.width_cm, p.height_cm) == (23, 17, 3) and p.weight_g == 4 + 60 and p.value == 400000
    assert cr.parcel_for("FLAT_BOX_A4", "A4", 80, 10, 1).weight_g == 50 + 90               # 0.06237 m2 x 80 g x 10 sheets
    assert cr.parcel_for("FLAT_BOX_A5", "A6", 80, 0, 0).weight_g >= 60                      # at least the box
    assert cr.parcel_for("FLAT_BOX_A5", "A5", 120, 1, 99_000_000).value == cr.DECLARED_VALUE_CAP
    for args in (("TUBE", "A5", 120, 1, 1), ("FLAT_BOX_A5", "A3", 120, 1, 1)):
        with pytest.raises(cr.CarrierRuleError) as exc:
            cr.parcel_for(*args)
        assert exc.value.code == "PACKAGE_UNKNOWN"


def test_round_up_to_100():
    assert [cr.round_up_100(x) for x in (0, 1, 100, 101, 22500, 22501, Decimal("34999.9"))] == [0, 100, 100, 200, 22500, 22600, 35000]


def test_mock_service_catalogue_is_priced_from_the_fallback_table():
    now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
    ghn = {q.service_code: q for q in cr.mock_services("GHN", 25000, now)}
    ghtk = {q.service_code: q for q in cr.mock_services("GHTK", 25000, now)}
    assert (ghn["STANDARD"].fee, ghn["EXPRESS"].fee, ghtk["ROAD"].fee, ghtk["FAST"].fee) == (25000, 35000, 22500, 37500)
    assert ghn["EXPRESS"].eta == now + timedelta(days=1) and ghtk["ROAD"].eta == now + timedelta(days=4)
    assert all(q.mode == "MOCK" and not q.is_fallback for q in [*ghn.values(), *ghtk.values()])
    assert all(q.fee % 100 == 0 for q in [*ghn.values(), *ghtk.values()])
    fb = cr.fallback_quote("GHN", Decimal(25000))
    assert (fb.service_code, fb.fee, fb.eta, fb.is_fallback, fb.mode) == ("STANDARD", 25000, None, True, "FALLBACK")


def _q(carrier, code, fee, days=None):
    return ServiceQuote(carrier, code, code, fee, datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=days) if days else None)


def test_choosing_a_service():
    quotes = [_q("GHN", "A", 30000, 1), _q("GHTK", "B", 22000, 4), _q("GHN", "C", 22000, 2)]
    assert cr.pick_service(quotes, "GHN", "A").fee == 30000
    assert cr.pick_service(quotes, None, None).service_code == "C"              # cheapest, then the faster one
    assert cr.pick_service([_q("GHN", "Z", 1000), _q("GHN", "Y", 1000)], None, None).service_code == "Y"   # then by name
    assert cr.pick_service([_q("GHN", "STANDARD", 1000), _q("GHTK", "STANDARD", 1000)], None, None).carrier == "GHN"
    for args in (("GHN", "B"), ("GHTK", "A"), ("GHN", "NOPE"), ("GHN", None), (None, "A")):
        with pytest.raises(cr.CarrierRuleError) as exc:
            cr.pick_service(quotes, *args)
        assert exc.value.code == "SERVICE_NOT_AVAILABLE", args
    with pytest.raises(cr.CarrierRuleError):
        cr.pick_service([], None, None)


# ===================================================================================== the MOCK carrier
def test_mock_carrier():
    m = cx.MockCarrier("GHN", {"FLAT_BOX_A5": 25000})
    assert [q.service_code for q in m.quote(parcel=PARCEL, to={}, order_code="X")] == ["STANDARD", "EXPRESS"]
    with pytest.raises(AppError) as exc:
        cx.MockCarrier("GHN", {}).quote(parcel=PARCEL, to={}, order_code="X")
    assert exc.value.status == 503 and exc.value.code == "SHIPPING_FEE_UNAVAILABLE"
    wb = m.create(parcel=PARCEL, to={}, order_code="X", service_code="EXPRESS", note=None)
    assert wb.code.startswith("MOCK-GHN-") and len(wb.code) == len("MOCK-GHN-") + 12
    assert m.create(parcel=PARCEL, to={}, order_code="X", service_code="STANDARD", note=None).code != wb.code
    with pytest.raises(AppError) as exc:
        m.create(parcel=PARCEL, to={}, order_code="X", service_code="ROAD", note=None)       # a GHTK service
    assert exc.value.code == "SERVICE_NOT_AVAILABLE"
    pdf = m.label(waybill_code=wb.code, context={"service_name": "Giao nhanh", "order_code": "VHRS-1", "receiver": "Nguyễn An",
                                                 "phone": "0901234567", "address_line": "1 Lê Lợi", "weight_g": 64})
    assert pdf[:5] == b"%PDF-"


def test_mock_carrier_callbacks_are_signed():
    m = cx.MockCarrier("GHN", None)
    body = m.webhook_body("MOCK-GHN-ABC", S.DELIVERED, "ok")
    sig = {cx.SIGNATURE_HEADER: m.sign(body)}
    ev = m.parse_webhook(body=body, query={}, headers=sig)
    assert (ev.waybill_code, ev.status, ev.reason) == ("MOCK-GHN-ABC", S.DELIVERED, "ok")
    assert m.parse_webhook(body=body, query={}, headers={cx.SIGNATURE_HEADER.lower(): m.sign(body)}).status == S.DELIVERED
    for headers in ({}, {cx.SIGNATURE_HEADER: "00" * 32}, {cx.SIGNATURE_HEADER: ""}):
        with pytest.raises(InvalidSignature):
            m.parse_webhook(body=body, query={}, headers=headers)
    with pytest.raises(InvalidSignature):
        m.parse_webhook(body=body + b" ", query={}, headers=sig)                                   # body changed after signing
    for junk in (b"not json", json.dumps({"waybill_code": "A", "status": "BOGUS"}).encode(), json.dumps({"status": "FAILED"}).encode()):
        with pytest.raises(MalformedCallback):
            m.parse_webhook(body=junk, query={}, headers={cx.SIGNATURE_HEADER: m.sign(junk)})


# ===================================================================================== registry
@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    for k, v in (("carrier_mode", "mock"), ("ghn_token", None), ("ghn_shop_id", None), ("ghn_from_district_id", None),
                 ("ghn_from_ward_code", None), ("ghtk_token", None), ("ghtk_client_source", None), ("carrier_webhook_secret", SECRET)):
        monkeypatch.setattr(s, k, v)
    cx.use_adapters(None)
    cx.use_flags(None)
    yield s
    cx.use_adapters(None)
    cx.use_flags(None)


def test_registry_modes_and_credentials(settings, monkeypatch):
    assert isinstance(cx.get_adapter("GHN", fee_table={}), cx.MockCarrier) and cx.mode_label() == "MOCK"
    monkeypatch.setattr(settings, "carrier_mode", "sandbox")
    with pytest.raises(AppError) as exc:
        cx.get_adapter("GHN")
    assert exc.value.status == 503 and exc.value.code == "CARRIER_NOT_CONFIGURED"
    assert cx.get_adapter("GHTK", strict=False) is None and cx.mode_label() == "SANDBOX"
    for k, v in (("ghn_token", "t"), ("ghn_shop_id", "9"), ("ghn_from_district_id", 1442)):
        monkeypatch.setattr(settings, k, v)
    assert cx.get_adapter("GHN", strict=False) is None                                             # the ward code is missing
    monkeypatch.setattr(settings, "ghn_from_ward_code", "20308")
    ghn = cx.get_adapter("GHN")
    assert isinstance(ghn, GhnCarrier) and ghn.mode == "SANDBOX" and ghn.shop_id == 9
    monkeypatch.setattr(settings, "ghtk_token", "t")
    assert cx.get_adapter("GHTK", strict=False) is None                                            # no client source
    monkeypatch.setattr(settings, "ghtk_client_source", "S123")
    monkeypatch.setattr(settings, "carrier_mode", "live")
    assert isinstance(cx.get_adapter("ghtk"), GhtkCarrier) and cx.mode_label() == "LIVE"


def test_flags_and_overrides(settings, monkeypatch):
    assert cx.api_enabled("GHN", {"GHN": True, "GHTK": False}) is True and cx.api_enabled("GHTK", {"GHN": True, "GHTK": False}) is False
    assert cx.api_enabled("GHN", None) is False and cx.api_enabled("GHN", {}) is False
    cx.use_flags({"GHN": True})
    assert cx.api_enabled("GHN", {}) is True and cx.api_enabled("GHTK", {"GHTK": True}) is False   # the override wins
    cx.use_flags(None)
    monkeypatch.setattr(settings, "carrier_mode", "sandbox")
    stand_in = object()
    cx.use_adapters({"GHN": stand_in})
    assert cx.get_adapter("GHN") is stand_in
    monkeypatch.setattr(settings, "carrier_mode", "mock")
    assert isinstance(cx.get_adapter("GHN", fee_table={}), cx.MockCarrier)                        # mock mode ignores real adapters


# ===================================================================================== GHN
def ghn(handler) -> GhnCarrier:
    return GhnCarrier(token="TOK", shop_id="777", base_url="https://ghn.example/shiip/public-api", from_district_id=1442,
                      from_ward_code="20308", mode="SANDBOX", webhook_secret=SECRET, transport=httpx.MockTransport(handler))


def _ghn_api(calls, *, fee=None, services=None, fee_code=200, lead=None, order_code="GHNABC123"):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, dict(request.headers), body))
        path = request.url.path
        if path.endswith("/available-services"):
            return httpx.Response(200, json={"code": 200, "data": services if services is not None else [
                {"service_id": 53320, "short_name": "Chuẩn", "service_type_id": 2},
                {"service_id": 53321, "short_name": "Nhanh", "service_type_id": 2}]})
        if path.endswith("/shipping-order/fee"):
            if fee_code != 200 and body["service_id"] == 53321:
                return httpx.Response(400, json={"code": fee_code, "message": "service not supported"})
            return httpx.Response(200, json={"code": 200, "data": {"total": (fee or {53320: 21250, 53321: 35100})[body["service_id"]]}})
        if path.endswith("/leadtime"):
            return httpx.Response(200, json={"code": 200, "data": {"leadtime": lead or 1792000000}})
        if path.endswith("/shipping-order/create"):
            return httpx.Response(200, json={"code": 200, "data": {"order_code": order_code, "total_fee": 21250,
                                                                   "expected_delivery_time": "2026-10-25T16:59:59Z"}})
        if path.endswith("/switch-status/cancel"):
            return httpx.Response(200, json={"code": 200, "data": [{"order_code": "GHNABC123", "result": True}]})
        if path.endswith("/a5/gen-token"):
            return httpx.Response(200, json={"code": 200, "data": {"token": "PRINTTOKEN"}})
        if path.endswith("/printA5"):
            return httpx.Response(200, content=b"%PDF-1.4 label", headers={"content-type": "application/pdf"})
        return httpx.Response(404, json={"code": 404})
    return handler


def test_ghn_quote_asks_services_fee_and_leadtime():
    calls: list = []
    quotes = ghn(_ghn_api(calls)).quote(parcel=PARCEL, to=GHN_TO, order_code="VHRS-1")
    assert [(q.carrier, q.service_code, q.service_name, q.fee, q.mode) for q in quotes] == [
        ("GHN", "53320", "Chuẩn", 21300, "SANDBOX"), ("GHN", "53321", "Nhanh", 35100, "SANDBOX")]      # fee rounded up to 100
    assert quotes[0].eta == datetime.fromtimestamp(1792000000, tz=timezone.utc)
    method, path, headers, body = calls[0]
    assert path == "/shiip/public-api/v2/shipping-order/available-services" and headers["token"] == "TOK" and headers["shopid"] == "777"
    assert body == {"shop_id": 777, "from_district": 1442, "to_district": 1442}
    fee_body = next(c[3] for c in calls if c[1].endswith("/fee"))
    assert fee_body == {"from_district_id": 1442, "from_ward_code": "20308", "to_district_id": 1442, "to_ward_code": "20308",
                        "service_id": 53320, "weight": PARCEL.weight_g, "length": 23, "width": 17, "height": 3,
                        "insurance_value": 400000}


def test_ghn_quote_leaves_out_a_service_that_cannot_carry_the_parcel_and_survives_a_missing_estimate():
    assert [q.service_code for q in ghn(_ghn_api([], fee_code=400)).quote(parcel=PARCEL, to=GHN_TO, order_code="X")] == ["53320"]

    def no_leadtime(request):
        if request.url.path.endswith("/leadtime"):
            return httpx.Response(500, text="x")
        return _ghn_api([])(request)
    quotes = ghn(no_leadtime).quote(parcel=PARCEL, to=GHN_TO, order_code="X")
    assert len(quotes) == 2 and all(q.eta is None for q in quotes)
    assert ghn(_ghn_api([], services=[])).quote(parcel=PARCEL, to=GHN_TO, order_code="X") == []


def test_ghn_errors():
    with pytest.raises(AppError) as exc:
        ghn(lambda r: httpx.Response(200, json={"code": 400, "message": "shop not found"})).quote(parcel=PARCEL, to=GHN_TO, order_code="X")
    assert exc.value.status == 502 and exc.value.code == "CARRIER_REJECTED" and "shop not found" in exc.value.details["message"]
    for response in (httpx.Response(503, text="down"), httpx.Response(200, text="<html>")):
        with pytest.raises(AppError) as exc:
            ghn(lambda r, resp=response: resp).quote(parcel=PARCEL, to=GHN_TO, order_code="X")
        assert exc.value.code == "CARRIER_UNAVAILABLE"
    with pytest.raises(AppError) as exc:
        ghn(_ghn_api([])).quote(parcel=PARCEL, to={**GHN_TO, "district_code": "x"}, order_code="X")
    assert exc.value.status == 422 and exc.value.code == "INVALID_ADDRESS"


def test_ghn_create_cancel_label():
    calls: list = []
    g = ghn(_ghn_api(calls))
    wb = g.create(parcel=PARCEL, to=GHN_TO, order_code="VHRS-1", service_code="53320", note="Giao giờ hành chính")
    assert wb.code == "GHNABC123" and wb.fee == 21250 and wb.eta == datetime(2026, 10, 25, 16, 59, 59, tzinfo=timezone.utc)
    body = next(c[3] for c in calls if c[1].endswith("/create"))
    assert body["payment_type_id"] == 1 and body["cod_amount"] == 0 and body["service_id"] == 53320            # shop pays, no COD
    assert body["to_district_id"] == 1442 and body["to_ward_code"] == "20308" and body["client_order_code"] == "VHRS-1"
    assert body["weight"] == PARCEL.weight_g and body["insurance_value"] == 400000 and body["to_name"] == "Nguyễn An"
    for bad in ("STANDARD", ""):
        with pytest.raises(AppError) as exc:
            g.create(parcel=PARCEL, to=GHN_TO, order_code="X", service_code=bad, note=None)
        assert exc.value.code == "SERVICE_NOT_AVAILABLE"
    with pytest.raises(AppError) as exc:
        ghn(lambda r: httpx.Response(200, json={"code": 200, "data": {}})).create(parcel=PARCEL, to=GHN_TO, order_code="X",
                                                                                 service_code="1", note=None)
    assert exc.value.code == "CARRIER_REJECTED"
    g.cancel("GHNABC123")
    assert next(c[3] for c in calls if c[1].endswith("/cancel")) == {"order_codes": ["GHNABC123"]}
    assert g.label(waybill_code="GHNABC123", context={}) == b"%PDF-1.4 label"
    printed = next(c for c in calls if c[1].endswith("/printA5"))
    assert printed[0] == "GET" and printed[1] == "/a5/public-api/printA5"


def _ghn_hook(g, status="delivered", key=SECRET, **over):
    body = json.dumps({"Type": "switch_status", "OrderCode": "GHNABC123", "Status": status, "Time": "2026-10-23T10:00:00Z",
                       "Reason": "Giao thành công", **over}).encode()
    return g.parse_webhook(body=body, query={"key": key} if key is not None else {}, headers={})


def test_ghn_callbacks():
    g = ghn(lambda r: httpx.Response(200))
    ev = _ghn_hook(g)
    assert (ev.waybill_code, ev.status, ev.reason) == ("GHNABC123", S.DELIVERED, "Giao thành công")
    assert ev.occurred_at == datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc)
    assert _ghn_hook(g, "picked").status == S.PICKED_UP and _ghn_hook(g, "delivery_fail").status == S.FAILED
    assert _ghn_hook(g, "some_new_status").status is None                               # unknown to us: not applied
    assert _ghn_hook(g, Type="update_weight").status is None                            # other event types: informational
    for key in ("wrong", None, ""):
        with pytest.raises(InvalidSignature):
            _ghn_hook(g, key=key)
    unsecured = GhnCarrier(token="T", shop_id=1, base_url="https://x", from_district_id=1, from_ward_code="1", mode="SANDBOX",
                           webhook_secret=None)
    with pytest.raises(InvalidSignature):
        unsecured.parse_webhook(body=b"{}", query={"key": ""}, headers={})                # no secret configured: nothing is trusted
    for junk in (b"nope", b"[]", json.dumps({"Status": "delivered"}).encode()):
        with pytest.raises(MalformedCallback):
            g.parse_webhook(body=junk, query={"key": SECRET}, headers={})


# ===================================================================================== GHTK
def ghtk(handler) -> GhtkCarrier:
    return GhtkCarrier(token="GTOK", client_source="S123", base_url="https://ghtk.example", mode="SANDBOX",
                       webhook_secret=SECRET, transport=httpx.MockTransport(handler))


@pytest.fixture
def pickup(monkeypatch):
    s = get_settings()
    for k, v in (("workshop_name", "Xuong Net Viet"), ("workshop_phone", "0280000000"), ("workshop_address", "10 Nguyen Hue"),
                 ("workshop_province", "Hồ Chí Minh"), ("workshop_district", "Quận 1"), ("workshop_ward", "Bến Nghé")):
        monkeypatch.setattr(s, k, v)


def _ghtk_api(calls, *, road=22000, fly=None):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, dict(request.headers), dict(request.url.params), body))
        path = request.url.path
        if path == "/services/shipment/fee":
            transport = request.url.params["transport"]
            if transport == "road":
                return httpx.Response(200, json={"success": True, "fee": {"fee": road, "delivery": True}})
            if fly is None:
                return httpx.Response(200, json={"success": False, "message": "Không hỗ trợ đường bay"})
            return httpx.Response(200, json={"success": True, "fee": {"fee": fly, "delivery": True}})
        if path == "/services/shipment/order":
            return httpx.Response(200, json={"success": True, "order": {"label": "S1.A1.B2", "fee": 22000,
                                                                        "estimated_deliver_time": "2026-10-26T12:00:00+07:00"}})
        if path.startswith("/services/shipment/cancel/"):
            return httpx.Response(200, json={"success": True, "message": "ok"})
        if path.startswith("/services/label/"):
            return httpx.Response(200, content=b"%PDF-1.4 ghtk", headers={"content-type": "application/pdf"})
        return httpx.Response(404, json={"success": False})
    return handler


def test_ghtk_quote(pickup):
    calls: list = []
    quotes = ghtk(_ghtk_api(calls, road=21250)).quote(parcel=PARCEL, to=GHTK_TO, order_code="VHRS-1")
    assert [(q.carrier, q.service_code, q.fee, q.eta, q.mode) for q in quotes] == [("GHTK", "ROAD", 21300, None, "SANDBOX")]  # no air route
    method, path, headers, params, _ = calls[0]
    assert method == "GET" and path == "/services/shipment/fee" and headers["token"] == "GTOK" and headers["x-client-source"] == "S123"
    assert params["province"] == "Hồ Chí Minh" and params["district"] == "Quận 1" and params["weight"] == str(PARCEL.weight_g)
    assert params["pick_province"] == "Hồ Chí Minh" and params["transport"] == "road" and params["value"] == "400000"
    both = ghtk(_ghtk_api([], road=22000, fly=48000)).quote(parcel=PARCEL, to=GHTK_TO, order_code="X")
    assert [(q.service_code, q.fee) for q in both] == [("ROAD", 22000), ("FLY", 48000)]


def test_ghtk_needs_names_and_a_pickup_address(pickup, monkeypatch):
    for to in (GHN_TO, {**GHTK_TO, "district_name": ""}, {**GHTK_TO, "province_name": None}):
        with pytest.raises(AppError) as exc:
            ghtk(_ghtk_api([])).quote(parcel=PARCEL, to=to, order_code="X")
        assert exc.value.status == 422 and exc.value.code == "ADDRESS_NAMES_REQUIRED"
    monkeypatch.setattr(get_settings(), "workshop_address", None)
    with pytest.raises(AppError) as exc:
        ghtk(_ghtk_api([])).quote(parcel=PARCEL, to=GHTK_TO, order_code="X")
    assert exc.value.status == 503 and exc.value.code == "CARRIER_NOT_CONFIGURED"


def test_ghtk_errors(pickup):
    with pytest.raises(AppError) as exc:
        ghtk(lambda r: httpx.Response(200, json={"success": False, "message": "token"})).create(
            parcel=PARCEL, to=GHTK_TO, order_code="X", service_code="ROAD", note=None)
    assert exc.value.code == "CARRIER_REJECTED"
    with pytest.raises(AppError) as exc:
        ghtk(lambda r: httpx.Response(502, text="bad gateway")).quote(parcel=PARCEL, to=GHTK_TO, order_code="X")
    assert exc.value.code == "CARRIER_UNAVAILABLE"
    with pytest.raises(AppError) as exc:
        ghtk(_ghtk_api([])).create(parcel=PARCEL, to=GHTK_TO, order_code="X", service_code="STANDARD", note=None)
    assert exc.value.code == "SERVICE_NOT_AVAILABLE"
    with pytest.raises(AppError) as exc:
        ghtk(lambda r: httpx.Response(200, json={"success": True, "order": {}})).create(
            parcel=PARCEL, to=GHTK_TO, order_code="X", service_code="ROAD", note=None)
    assert exc.value.code == "CARRIER_REJECTED"


def test_ghtk_create_cancel_label(pickup):
    calls: list = []
    g = ghtk(_ghtk_api(calls))
    wb = g.create(parcel=PARCEL, to=GHTK_TO, order_code="VHRS-1", service_code="ROAD", note="Gọi trước khi giao")
    assert wb.code == "S1.A1.B2" and wb.fee == 22000 and wb.eta == datetime(2026, 10, 26, 5, 0, tzinfo=timezone.utc)
    body = next(c[4] for c in calls if c[1] == "/services/shipment/order")
    assert body["products"] == [{"name": "Sản phẩm viết tay", "weight": round(PARCEL.weight_g / 1000, 3), "quantity": 1}]
    order = body["order"]
    assert order["id"] == "VHRS-1" and order["is_freeship"] == 1 and order["pick_money"] == 0 and order["transport"] == "road"
    assert order["name"] == "Nguyễn An" and order["tel"] == "0901234567" and order["province"] == "Hồ Chí Minh"
    assert order["pick_province"] == "Hồ Chí Minh" and order["pick_tel"] == "0280000000" and order["value"] == 400000
    g.cancel("S1.A1.B2")
    assert next(c[1] for c in calls if "/cancel/" in c[1]) == "/services/shipment/cancel/S1.A1.B2"
    assert g.label(waybill_code="S1.A1.B2", context={}) == b"%PDF-1.4 ghtk"


def _ghtk_hook(g, status_id=5, *, form=False, key=SECRET, **over):
    data = {"label_id": "S1.A1.B2", "partner_id": "VHRS-1", "status_id": status_id, "action_time": "2026-10-23T10:00:00+07:00",
            "reason": "ok", **over}
    body = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
    return g.parse_webhook(body=body, query={"hash": key} if key is not None else {}, headers={})


def test_ghtk_callbacks():
    g = ghtk(lambda r: httpx.Response(200))
    for form in (False, True):                                              # GHTK sends form data or JSON
        ev = _ghtk_hook(g, form=form)
        assert (ev.waybill_code, ev.status, ev.reason) == ("S1.A1.B2", S.DELIVERED, "ok")
    assert _ghtk_hook(g, 3).status == S.PICKED_UP and _ghtk_hook(g, 9).status == S.FAILED and _ghtk_hook(g, -1).status == S.CANCELLED
    assert _ghtk_hook(g, 123).status is None and _ghtk_hook(g, 4, form=True).status == S.DELIVERING     # informational / form ints
    assert _ghtk_hook(g).occurred_at == datetime(2026, 10, 23, 3, 0, tzinfo=timezone.utc)
    for key in ("wrong", None, ""):
        with pytest.raises(InvalidSignature):
            _ghtk_hook(g, key=key)
    for junk in (b"zzz", json.dumps({"status_id": 5}).encode(), b"label_id=A"):
        with pytest.raises(MalformedCallback):
            g.parse_webhook(body=junk, query={"hash": SECRET}, headers={})
