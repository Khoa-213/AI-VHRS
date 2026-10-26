"""Carrier rules, the MOCK carrier, the GHN adapter, the location catalogue and the registry. No database, no network
(httpx.MockTransport).

The GHN requests and answers used here are the shapes GHN's staging API returned on 2026-10-26 (preview, create, cancel, label
token, master data), but this file proves only that the code is SELF-CONSISTENT with them; see VERIFICATION in ghn.py.
"""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.domain import carrier_rules as cr
from app.domain.carrier_rules import ServiceQuote
from app.integrations import carrier as cx
from app.integrations import locations as loc
from app.integrations.ghn import GhnCarrier
from app.integrations.payment_gateway import InvalidSignature, MalformedCallback
from app.models.ops import ShipmentStatus as S

SECRET = "carrier-secret"
GHN_TO = {"receiver": "Nguyễn An", "phone": "0901234567", "street": "1 Lê Lợi", "province_code": "1000001",
          "province_name": "Hồ Chí Minh", "ward_code": "1003506", "ward_name": "Phường Sài Gòn"}
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
                                              "lost", "damage", "scrap")} == {
        "ready_to_pick": S.CREATED, "picking": S.CREATED, "picked": S.PICKED_UP, "storing": S.DELIVERING,
        "transporting": S.DELIVERING, "delivering": S.DELIVERING, "delivered": S.DELIVERED, "delivery_fail": S.FAILED,
        "waiting_to_return": S.FAILED, "returned": S.RETURNED, "cancel": S.CANCELLED, "lost": S.FAILED, "damage": S.FAILED,
        "scrap": S.FAILED}
    assert cr.map_ghn_status("  DELIVERED ") == S.DELIVERED and cr.map_ghn_status("nonsense") is None
    assert cr.map_ghn_status(None) is None and cr.map_ghn_status("") is None
    assert set(cr.GHN_STATUS.values()) <= set(S)


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
    assert set(ghn) == {"STANDARD", "EXPRESS"} and set(cr.MOCK_SERVICES) == {"GHN"}              # GHTK is no longer offered
    assert (ghn["STANDARD"].fee, ghn["EXPRESS"].fee) == (25000, 35000) and ghn["EXPRESS"].eta == now + timedelta(days=1)
    assert all(q.mode == "MOCK" and not q.is_fallback for q in ghn.values())
    assert all(q.fee % 100 == 0 for q in ghn.values())
    fb = cr.fallback_quote("GHN", Decimal(25000))
    assert (fb.service_code, fb.fee, fb.eta, fb.is_fallback, fb.mode) == ("STANDARD", 25000, None, True, "FALLBACK")


def _q(carrier, code, fee, days=None):
    return ServiceQuote(carrier, code, code, fee, datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=days) if days else None)


def test_choosing_a_service():
    quotes = [_q("GHN", "A", 30000, 1), _q("GHN", "B", 22000, 4), _q("GHN", "C", 22000, 2)]
    assert cr.pick_service(quotes, "GHN", "A").fee == 30000
    assert cr.pick_service(quotes, None, None).service_code == "C"              # cheapest, then the faster one
    assert cr.pick_service([_q("GHN", "Z", 1000), _q("GHN", "Y", 1000)], None, None).service_code == "Y"   # then by name
    for args in (("GHTK", "A"), ("GHN", "NOPE"), ("GHN", None), (None, "A")):                  # GHTK is not among the quotes
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
        m.create(parcel=PARCEL, to={}, order_code="X", service_code="ROAD", note=None)       # not one of its services
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
    for k, v in (("carrier_mode", "mock"), ("ghn_token", None), ("ghn_shop_id", None), ("carrier_webhook_secret", SECRET)):
        monkeypatch.setattr(s, k, v)
    cx.use_adapters(None)
    cx.use_flags(None)
    yield s
    cx.use_adapters(None)
    cx.use_flags(None)


def test_registry_modes_and_credentials(settings, monkeypatch):
    assert isinstance(cx.get_adapter("GHN", fee_table={}), cx.MockCarrier) and cx.mode_label() == "MOCK"
    assert cx.CARRIERS == ("GHN",)
    monkeypatch.setattr(settings, "carrier_mode", "sandbox")
    with pytest.raises(AppError) as exc:
        cx.get_adapter("GHN")
    assert exc.value.status == 503 and exc.value.code == "CARRIER_NOT_CONFIGURED"
    assert cx.get_adapter("GHN", strict=False) is None and cx.mode_label() == "SANDBOX"
    monkeypatch.setattr(settings, "ghn_token", "t")
    assert cx.get_adapter("GHN", strict=False) is None                                             # the shop id is missing
    monkeypatch.setattr(settings, "ghn_shop_id", "9")
    adapter = cx.get_adapter("GHN")
    assert isinstance(adapter, GhnCarrier) and adapter.mode == "SANDBOX" and adapter.shop_id == 9
    monkeypatch.setattr(settings, "carrier_mode", "live")
    assert cx.get_adapter("ghn").mode == "LIVE" and cx.mode_label() == "LIVE"
    for strict in (True, False):                                                                    # GHTK was dropped from the flow
        with pytest.raises(AppError) as exc:
            cx.get_adapter("GHTK", strict=strict)
        assert exc.value.status == 422 and exc.value.code == "CARRIER_NOT_SUPPORTED"


def test_flags_and_overrides(settings, monkeypatch):
    assert cx.api_enabled("GHN", {"GHN": True}) is True and cx.api_enabled("GHN", {"GHN": False}) is False
    assert cx.api_enabled("GHN", None) is False and cx.api_enabled("GHN", {}) is False
    cx.use_flags({"GHN": True})
    assert cx.api_enabled("GHN", {}) is True and cx.api_enabled("GHN", {"GHN": False}) is True    # the override wins
    cx.use_flags(None)
    monkeypatch.setattr(settings, "carrier_mode", "sandbox")
    stand_in = object()
    cx.use_adapters({"GHN": stand_in})
    assert cx.get_adapter("GHN") is stand_in
    monkeypatch.setattr(settings, "carrier_mode", "mock")
    assert isinstance(cx.get_adapter("GHN", fee_table={}), cx.MockCarrier)                        # mock mode ignores real adapters


# ===================================================================================== GHN
def ghn(handler, secret=SECRET) -> GhnCarrier:
    return GhnCarrier(token="TOK", shop_id="777", base_url="https://ghn.example/shiip/public-api", mode="SANDBOX",
                      webhook_secret=secret, transport=httpx.MockTransport(handler))


def _ghn_api(calls, *, fee=21250, order_code="GHNABC123", cancel_result=True):
    """GHN as its staging API answered on 2026-10-26: preview / create / cancel / label token."""
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, dict(request.headers), body))
        path = request.url.path
        if path.endswith("/shipping-order/preview"):
            return httpx.Response(200, json={"code": 200, "message": "Success", "data": {
                "order_code": "", "total_fee": fee, "expected_delivery_time": "2026-10-27T16:59:59Z"}})
        if path.endswith("/shipping-order/create"):
            return httpx.Response(200, json={"code": 200, "message": "Success", "data": {
                "order_code": order_code, "total_fee": fee, "expected_delivery_time": "2026-10-27T16:59:59Z"}})
        if path.endswith("/switch-status/cancel"):
            return httpx.Response(200, json={"code": 200, "data": [{"order_code": order_code, "result": cancel_result,
                                                                    "message": "OK" if cancel_result else "Đơn đã lấy hàng"}]})
        if path.endswith("/a5/gen-token"):
            return httpx.Response(200, json={"code": 200, "data": {"token": "PRINTTOKEN"}})
        return httpx.Response(404, json={"code": 404})
    return handler


def test_ghn_quote_is_one_preview_call_in_the_two_level_model():
    calls: list = []
    quotes = ghn(_ghn_api(calls)).quote(parcel=PARCEL, to=GHN_TO, order_code="VHRS-1")
    assert [(q.carrier, q.service_code, q.fee, q.mode) for q in quotes] == [("GHN", "2", 21300, "SANDBOX")]     # rounded up to 100
    assert quotes[0].eta == datetime(2026, 10, 27, 16, 59, 59, tzinfo=timezone.utc) and "nhẹ" in quotes[0].service_name
    assert len(calls) == 1
    method, path, headers, body = calls[0]
    assert method == "POST" and path == "/shiip/public-api/v2/shipping-order/preview"
    assert headers["token"] == "TOK" and headers["shopid"] == "777"
    assert body["is_new_to_address"] is True and "to_district_name" not in body and "to_district_id" not in body
    assert (body["to_province_name"], body["to_ward_name"]) == ("Hồ Chí Minh", "Phường Sài Gòn")
    assert body["to_address"] == "1 Lê Lợi, Phường Sài Gòn, Hồ Chí Minh" and body["to_name"] == "Nguyễn An"
    assert body["service_type_id"] == 2 and body["payment_type_id"] == 1 and body["cod_amount"] == 0
    assert (body["weight"], body["length"], body["width"], body["height"]) == (PARCEL.weight_g, 23, 17, 3)
    assert body["insurance_value"] == 400000 and "client_order_code" not in body            # a preview creates nothing


def test_ghn_heavy_parcels_use_the_heavy_service():
    heavy = cr.Parcel("FLAT_BOX_A4", 20_000, 32, 23, 3, 1)
    calls: list = []
    q = ghn(_ghn_api(calls)).quote(parcel=heavy, to=GHN_TO, order_code="X")[0]
    assert q.service_code == "5" and "nặng" in q.service_name and calls[0][3]["service_type_id"] == 5
    assert calls[0][3]["items"][0]["weight"] == 20_000 and calls[0][3]["items"][0]["length"] == 32


def test_ghn_errors():
    def failing(body, status=200):
        return lambda r: httpx.Response(status, json=body)
    with pytest.raises(AppError) as exc:
        ghn(failing({"code": 400, "message": "calculate fee error: route not found service"})).quote(
            parcel=PARCEL, to=GHN_TO, order_code="X")
    assert exc.value.status == 502 and exc.value.code == "CARRIER_REJECTED" and "route not found" in exc.value.details["message"]
    # an address GHN does not know is the customer's to fix: 422, not a bad gateway
    for body in ({"code": 400, "message": "Fail when get place name of from ward code: ward not found: Phường X in province Y"},
                 {"code": 400, "message": "x", "code_message": "PHONE_INVALID"}):
        with pytest.raises(AppError) as exc:
            ghn(failing(body, 400)).quote(parcel=PARCEL, to=GHN_TO, order_code="X")
        assert exc.value.status == 422 and exc.value.code == "INVALID_ADDRESS"
    for response, code in ((httpx.Response(503, text="down"), "CARRIER_UNAVAILABLE"), (httpx.Response(200, text="<html>"), "CARRIER_UNAVAILABLE"),
                           (httpx.Response(401, json={"code": 401}), "CARRIER_NOT_CONFIGURED"),
                           (httpx.Response(403, json={"code": 403}), "CARRIER_NOT_CONFIGURED")):
        with pytest.raises(AppError) as exc:
            ghn(lambda r, resp=response: resp).quote(parcel=PARCEL, to=GHN_TO, order_code="X")
        assert exc.value.code == code
    with pytest.raises(AppError) as exc:                                       # no total_fee in an otherwise good answer
        ghn(failing({"code": 200, "data": {}})).quote(parcel=PARCEL, to=GHN_TO, order_code="X")
    assert exc.value.code == "CARRIER_REJECTED"
    for to in ({**GHN_TO, "ward_name": ""}, {**GHN_TO, "province_name": None}, {"receiver": "A", "phone": "0901234567"}):
        with pytest.raises(AppError) as exc:                                   # an old-style address without names
            ghn(_ghn_api([])).quote(parcel=PARCEL, to=to, order_code="X")
        assert exc.value.status == 422 and exc.value.code == "INVALID_ADDRESS"


def test_ghn_create():
    calls: list = []
    g = ghn(_ghn_api(calls))
    wb = g.create(parcel=PARCEL, to=GHN_TO, order_code="VHRS-1", service_code="2", note="Giao giờ hành chính",
                  reference="VHRS-1-2")
    assert wb.code == "GHNABC123" and wb.fee == 21250 and wb.eta == datetime(2026, 10, 27, 16, 59, 59, tzinfo=timezone.utc)
    body = next(c[3] for c in calls if c[1].endswith("/create"))
    assert body["payment_type_id"] == 1 and body["cod_amount"] == 0 and body["service_type_id"] == 2 and "service_id" not in body
    assert body["client_order_code"] == "VHRS-1-2"                                  # the attempt's reference, not the bare order code
    assert body["is_new_to_address"] is True and body["to_ward_name"] == "Phường Sài Gòn" and "to_ward_code" not in body
    assert body["weight"] == PARCEL.weight_g and body["insurance_value"] == 400000 and body["note"] == "Giao giờ hành chính"
    assert g.create(parcel=PARCEL, to=GHN_TO, order_code="VHRS-9", service_code="2", note=None).code == "GHNABC123"
    assert [c[3]["client_order_code"] for c in calls if c[1].endswith("/create")] == ["VHRS-1-2", "VHRS-9"]   # defaults to the order code
    for bad in ("STANDARD", "", "3", "53320"):
        with pytest.raises(AppError) as exc:
            g.create(parcel=PARCEL, to=GHN_TO, order_code="X", service_code=bad, note=None)
        assert exc.value.code == "SERVICE_NOT_AVAILABLE", bad
    with pytest.raises(AppError) as exc:
        ghn(lambda r: httpx.Response(200, json={"code": 200, "data": {}})).create(parcel=PARCEL, to=GHN_TO, order_code="X",
                                                                                 service_code="2", note=None)
    assert exc.value.code == "CARRIER_REJECTED"


def test_ghn_cancel_reports_a_refusal():
    calls: list = []
    ghn(_ghn_api(calls)).cancel("GHNABC123", "Khách đổi địa chỉ")
    assert calls[0][3] == {"order_codes": ["GHNABC123"], "reason_code": "GHN-CANCEL-OTHER", "reason": "Khách đổi địa chỉ"}
    ghn(_ghn_api([])).cancel("GHNABC123")                                          # the reason is optional
    with pytest.raises(AppError) as exc:                                            # GHN answers 200 with result=false when it is too late
        ghn(_ghn_api([], cancel_result=False)).cancel("GHNABC123", "x")
    assert exc.value.status == 409 and exc.value.code == "CARRIER_CANCEL_REFUSED" and "lấy hàng" in exc.value.details["message"]
    with pytest.raises(AppError) as exc:                                            # an answer that does not mention the order at all
        ghn(lambda r: httpx.Response(200, json={"code": 200, "data": []})).cancel("GHNABC123")
    assert exc.value.code == "CARRIER_CANCEL_REFUSED"
    with pytest.raises(AppError) as exc:                                            # an unknown order aborts GHN's whole batch
        ghn(lambda r: httpx.Response(400, json={"code": 400, "message": "Đơn hàng không tồn tại", "data": None})).cancel("ZZZ")
    assert exc.value.code == "CARRIER_REJECTED"


def test_ghn_label_is_a_link_to_its_print_page():
    calls: list = []
    g = ghn(_ghn_api(calls))
    assert g.label(waybill_code="GHNABC123", context={}) is None                  # GHN's label is a web page, not a file
    assert g.label_link("GHNABC123") == "https://ghn.example/a5/public-api/printA5?token=PRINTTOKEN"
    assert calls[0][3] == {"order_codes": ["GHNABC123"]}
    assert ghn(lambda r: httpx.Response(200, json={"code": 200, "data": {}})).label_link("X") is None


def _ghn_hook(g, status="delivered", key=SECRET, headers=None, **over):
    body = json.dumps({"Type": "switch_status", "OrderCode": "GHNABC123", "Status": status, "Time": "2026-10-23T10:00:00Z",
                       "Reason": "Giao thành công", **over}).encode()
    return g.parse_webhook(body=body, query={"key": key} if key is not None else {}, headers=headers or {})


def test_ghn_callbacks():
    g = ghn(lambda r: httpx.Response(200))
    ev = _ghn_hook(g)
    assert (ev.waybill_code, ev.status, ev.reason) == ("GHNABC123", S.DELIVERED, "Giao thành công")
    assert ev.occurred_at == datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc)
    assert _ghn_hook(g, "picked").status == S.PICKED_UP and _ghn_hook(g, "delivery_fail").status == S.FAILED
    assert _ghn_hook(g, "scrap").status == S.FAILED
    assert _ghn_hook(g, "some_new_status").status is None                               # unknown to us: not applied
    for kind in ("update_weight", "create", "cod", "update_fee"):
        assert _ghn_hook(g, Type=kind).status is None, kind                             # other event types: informational
    for key in ("wrong", None, ""):
        with pytest.raises(InvalidSignature):
            _ghn_hook(g, key=key)
    # the secret may travel in a custom header instead of the address (Developer Portal > Webhook configuration)
    assert _ghn_hook(g, key=None, headers={"X-Webhook-Secret": SECRET}).status == S.DELIVERED
    assert _ghn_hook(g, key=None, headers={"x-webhook-secret": SECRET}).status == S.DELIVERED
    with pytest.raises(InvalidSignature):
        _ghn_hook(g, key=None, headers={"X-Webhook-Secret": "wrong"})
    unsecured = ghn(lambda r: httpx.Response(200), secret=None)
    with pytest.raises(InvalidSignature):
        unsecured.parse_webhook(body=b"{}", query={"key": ""}, headers={"x-webhook-secret": ""})   # no secret configured: nothing is trusted
    for junk in (b"nope", b"[]", json.dumps({"Status": "delivered"}).encode()):
        with pytest.raises(MalformedCallback):
            g.parse_webhook(body=junk, query={"key": SECRET}, headers={})


# ===================================================================================== the location catalogue
def _province_row(pid, name, status=1):
    return {"_id": pid, "name": name, "status": status, "type": "province", "parent_id": 1}


def _ward_row(wid, name, parent, status=1):
    return {"_id": wid, "name": name, "status": status, "type": "ward", "parent_id": parent}


def _ghn_master(calls, *, fail=False):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, dict(request.url.params), dict(request.headers)))
        if fail:
            return httpx.Response(503, text="down")
        if request.url.path.endswith("/province/all"):
            return httpx.Response(200, json={"code": 200, "data": [_province_row(1000001, "Hồ Chí Minh"), _province_row(1000000, "Hà Nội"),
                                                                   _province_row(1, "Đã xoá", status=10)]})
        if request.url.path.endswith("/ward/all-by-province-id"):
            if request.url.params["province_id"] == "1000001":
                return httpx.Response(200, json={"code": 200, "data": [_ward_row(2, "Phường B", 1000001), _ward_row(1, "Phường A", 1000001),
                                                                       _ward_row(3, "Phường cũ", 1000001, status=2)]})
            return httpx.Response(200, json={"code": 200, "message": "Success", "data": None})        # GHN: unknown province = 200 + null
        return httpx.Response(404)
    return handler


def _ghn_locations(handler) -> loc.GhnLocations:
    return loc.GhnLocations(token="TOK", shop_id=777, base_url="https://ghn.example/shiip/public-api",
                            transport=httpx.MockTransport(handler))


def test_ghn_locations_read_the_v3_master_data():
    calls: list = []
    src = _ghn_locations(_ghn_master(calls))
    assert [(u.code, u.name) for u in src.provinces()] == [("1000000", "Hà Nội"), ("1000001", "Hồ Chí Minh")]   # active only, by name
    assert [(u.code, u.name) for u in src.wards("1000001")] == [("1", "Phường A"), ("2", "Phường B")]
    assert src.wards("999") is None and src.wards("abc") is None
    path, params, headers = calls[0]
    assert path == "/shiip/public-api/v3/master-data/province/all" and params["limit"] == "200"
    assert headers["token"] == "TOK" and headers["shopid"] == "777"
    assert calls[1][1]["province_id"] == "1000001"
    with pytest.raises(AppError) as exc:
        _ghn_locations(_ghn_master([], fail=True)).provinces()
    assert exc.value.status == 503 and exc.value.code == "LOCATIONS_UNAVAILABLE"


def test_the_catalogue_caches_and_survives_a_carrier_outage():
    calls: list = []
    clock = [0.0]
    cat = loc.LocationCatalog(_ghn_locations(_ghn_master(calls)), clock=lambda: clock[0])
    cat.provinces(), cat.provinces(), cat.wards("1000001"), cat.wards("1000001")
    assert len(calls) == 2                                                          # one province call, one ward call
    assert cat.wards("999") is None and cat.wards("999") is None and len(calls) == 4   # an unknown province is not remembered
    clock[0] += loc.CACHE_TTL_SECONDS + 1                                           # expired -> asked again
    cat.provinces()
    assert len(calls) == 5
    # GHN down: the older answer is served; with nothing cached it is an error
    flaky = {"down": False}

    def handler(request):
        return httpx.Response(503, text="x") if flaky["down"] else _ghn_master([])(request)
    cat2 = loc.LocationCatalog(_ghn_locations(handler), clock=lambda: clock[0])
    first = cat2.provinces()
    flaky["down"] = True
    clock[0] += loc.CACHE_TTL_SECONDS + 1
    assert cat2.provinces() == first
    clock[0] += 8 * 24 * 3600                                                       # too old even for a stand-in
    with pytest.raises(AppError):
        cat2.provinces()
    with pytest.raises(AppError):
        loc.LocationCatalog(_ghn_locations(handler), clock=lambda: clock[0]).provinces()


def test_resolving_an_address_checks_the_ward_belongs_to_the_province():
    cat = loc.LocationCatalog(_ghn_locations(_ghn_master([])))
    province, ward = cat.resolve("1000001", "1")
    assert (province.name, ward.name) == ("Hồ Chí Minh", "Phường A")
    for args in (("1000000", "1"), ("1000001", "3"), ("1000001", "999"), ("nope", "1"), ("", "")):   # wrong province / disabled / unknown
        with pytest.raises(AppError) as exc:
            cat.resolve(*args)
        assert exc.value.status == 422 and exc.value.code == "INVALID_ADDRESS", args


def test_the_mock_catalogue_and_address_normalisation(settings):
    cat = loc.get_catalog()
    assert {u.name for u in cat.provinces()} >= {"Hà Nội", "Hồ Chí Minh", "Đà Nẵng"}
    assert cat.wards("0") is None and "Phường Sài Gòn" in [w.name for w in cat.wards("1000001")]
    out = loc.normalize_address({**GHN_TO, "ward_name": "tên do khách tự gõ", "province_name": "sai", "district_code": "760",
                                 "district_name": "Quận 1"})
    assert out["province_name"] == "Hồ Chí Minh" and out["ward_name"] == "Phường Sài Gòn"          # names come from the catalogue
    assert "district_code" not in out and "district_name" not in out and out["street"] == "1 Lê Lợi"
    with pytest.raises(AppError):
        loc.normalize_address({**GHN_TO, "province_code": "1000000"})              # the ward does not belong to that province


def test_a_real_mode_without_credentials_has_no_catalogue(settings, monkeypatch):
    monkeypatch.setattr(settings, "carrier_mode", "sandbox")
    with pytest.raises(AppError) as exc:
        loc.get_catalog()
    assert exc.value.status == 503 and exc.value.code == "LOCATIONS_UNAVAILABLE"
    monkeypatch.setattr(settings, "ghn_token", "t")
    monkeypatch.setattr(settings, "ghn_shop_id", "9")
    assert isinstance(loc.get_catalog(), loc.LocationCatalog)
