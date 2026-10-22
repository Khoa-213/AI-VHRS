"""Phase 4c-2d: payments through the payOS adapter (VietQR bank transfer), end to end on the real database.

The adapter is the real class; only its HTTP calls go to httpx.MockTransport, and the "payOS" webhooks are signed by the test
with the same checksum key. payOS needs no PAYMENT_MODE switch (it only exists as a real transfer), so these run in the default
mock mode, which also proves the card gateways' mode does not leak into it.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.integrations import payment_gateway as gw
from app.integrations.payos import PayosGateway
from app.main import app
from tests.conftest import auth
from tests.test_api_delivery_final import _delivery, _final, _final_stage, _put, _rows
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _approved, _code, _hook, _signed
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import _err, cust, policy, staff, store, wcat  # noqa: F401

HOOK = f"{API}/webhooks/payments/payos"
RETURN_URL = "https://fe.example.test/payment/result"
KEY = "payos-checksum-test"


class FakePayos:
    """A scripted payOS: remembers the links it was asked for and what it was told to cancel."""

    def __init__(self):
        self.links, self.cancelled = {}, []
        self.status = {}                         # orderCode -> payOS link status for GET
        self.down = False
        self.gw = PayosGateway(client_id="cid", api_key="akey", checksum_key=KEY, base_url="https://payos.example.test",
                               transport=httpx.MockTransport(self._handler))

    def _handler(self, request: httpx.Request) -> httpx.Response:
        import json
        if self.down:
            return httpx.Response(503, text="maintenance")
        path = request.url.path
        if request.method == "POST" and path == "/v2/payment-requests":
            body = json.loads(request.content)
            self.links[body["orderCode"]] = body
            return httpx.Response(200, json={"code": "00", "desc": "success", "data": {
                "bin": "970422", "accountNumber": "0123456789", "accountName": "XUONG NET VIET", "amount": body["amount"],
                "description": body["description"], "orderCode": body["orderCode"], "currency": "VND",
                "paymentLinkId": f"plid-{body['orderCode']}", "status": "PENDING",
                "checkoutUrl": f"https://pay.payos.vn/web/{body['orderCode']}", "qrCode": f"0002010212...{body['orderCode']}"}})
        if request.method == "POST" and path.endswith("/cancel"):
            self.cancelled.append(int(path.split("/")[-2]))
            return httpx.Response(200, json={"code": "00", "desc": "ok", "data": {}})
        if request.method == "GET":
            code = int(path.rsplit("/", 1)[-1])
            amount = self.links[code]["amount"]
            st = self.status.get(code, "PENDING")
            return httpx.Response(200, json={"code": "00", "desc": "ok", "data": {
                "id": f"plid-{code}", "orderCode": code, "amount": amount, "amountPaid": amount if st == "PAID" else 0,
                "status": st}})
        return httpx.Response(404, json={})

    def webhook(self, txn, amount, **over) -> dict:
        data = {"orderCode": int(txn), "amount": int(amount), "description": "VHRS", "accountNumber": "0123456789",
                "reference": "FT26295", "transactionDateTime": "2026-10-22 14:20:00", "currency": "VND",
                "paymentLinkId": f"plid-{txn}", "code": "00", "desc": "success", **over}
        return {"code": "00", "desc": "success", "success": True, "data": data, "signature": self.gw.sign_data(data)}


@pytest.fixture
def payos(monkeypatch):
    gw.use_adapters(None)
    fake = FakePayos()
    s = get_settings()
    monkeypatch.setattr(s, "payment_return_url", RETURN_URL)
    gw.use_adapters({"PAYOS": fake.gw})
    yield fake
    gw.use_adapters(None)


def _start(client, cust, oid, gateway="PAYOS", expect=201):
    r = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": gateway})
    assert r.status_code == expect, r.text
    return r.json()


def _ostat(oid):
    return _sql("select order_status::text from orders where id=:o", o=oid)


def _pstat(pid):
    return _sql("select status::text from payments where id=:p", p=pid)


def _hit(client, body, expect=200):
    r = client.post(HOOK, json=body)
    assert r.status_code == expect, r.text
    return r.json()


# ---- which gateways the customer may pick ----------------------------------------------------------------------------
def test_gateways_endpoint_lists_payos_as_a_live_transfer_only_when_its_keys_exist(client, cust, payos):
    got = {g["gateway"]: g for g in client.get(f"{API}/payments/gateways", headers=cust).json()}
    assert got["PAYOS"] == {"gateway": "PAYOS", "mode": "LIVE", "enabled": True}
    assert got["VNPAY"]["mode"] == "MOCK"                                       # PAYMENT_MODE still governs the card gateways
    gw.use_adapters(None)
    got = {g["gateway"]: g for g in client.get(f"{API}/payments/gateways", headers=cust).json()}
    assert got["PAYOS"] == {"gateway": "PAYOS", "mode": "LIVE", "enabled": False}


def test_starting_a_payos_payment_without_keys_is_a_503(client, cust, staff, wcat):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    gw.use_adapters(None)
    r = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "PAYOS"})
    assert r.status_code == 503 and _err(r) == "GATEWAY_NOT_CONFIGURED"
    assert _sql("select count(*) from payments where order_id=:o", o=oid) == 0     # nothing half-created


# ---- deposit, end to end -----------------------------------------------------------------------------------------------
def test_payos_deposit_from_qr_to_confirmed_order(client, cust, staff, wcat, payos):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    deposit, code = Decimal(order["deposit_amount"]), _code(oid)

    p = _start(client, cust, oid)
    assert p["mode"] == "LIVE" and p["status"] == "PENDING" and p["checkout_path"] is None
    assert p["gateway_txn_id"].isdigit() and p["pay_url"] == f"https://pay.payos.vn/web/{p['gateway_txn_id']}"
    assert p["qr_code"].startswith("0002") and p["bank"]["account_number"] == "0123456789"
    assert p["bank"]["amount"] == int(deposit) and p["bank"]["content"] == code[:25]
    sent = payos.links[int(p["gateway_txn_id"])]
    assert sent["amount"] == int(deposit) and sent["description"] == code[:25]
    assert sent["returnUrl"] == f"{RETURN_URL}?order_id={oid}" and "cancelled=1" in sent["cancelUrl"]
    assert _start(client, cust, oid)["id"] == p["id"]                           # same intent while the link lives: reused
    txn = p["gateway_txn_id"]

    # not from payOS, or about something else: the order never moves
    bad = payos.webhook(txn, deposit)
    assert client.post(HOOK, json={**bad, "signature": "0" * 64}).status_code == 401
    assert client.post(HOOK, json={**bad, "data": {**bad["data"], "amount": 1}}).status_code == 401
    assert client.post(HOOK, content="not json", headers={"content-type": "application/json"}).status_code == 422
    assert _hit(client, payos.webhook("123456789", deposit))["result"] == "UNKNOWN_TRANSACTION"     # also payOS's own test message
    assert _ostat(oid) == "AWAITING_DEPOSIT" and _pstat(p["id"]) == "PENDING"

    # the simulated doors stay shut for a real transfer
    body, sig = _signed(txn, code, int(deposit))
    forged = _hook(client, "PAYOS", body, sig)
    assert forged.status_code == 404
    r = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert r.status_code == 409 and _err(r) == "NOT_A_MOCK_PAYMENT" and _ostat(oid) == "AWAITING_DEPOSIT"

    assert _hit(client, payos.webhook(txn, deposit))["result"] == "PROCESSED"
    assert _pstat(p["id"]) == "SUCCESS" and _ostat(oid) == "CONFIRMED"
    assert _hit(client, payos.webhook(txn, deposit))["result"] == "ALREADY_PROCESSED"            # payOS retries: idempotent
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='CONFIRMED'", o=oid) == 1


def test_a_transfer_of_the_wrong_amount_is_kept_for_refund_and_confirms_nothing(client, cust, staff, wcat, payos):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    deposit = Decimal(order["deposit_amount"])
    p = _start(client, cust, oid)
    txn = p["gateway_txn_id"]
    for wrong in (deposit - 1000, deposit + 1000):
        out = _hit(client, payos.webhook(txn, wrong))                           # payOS must still get a 200: no retry storm
        assert out["result"] == "AMOUNT_MISMATCH" and out["needs_refund"] is True
        assert _pstat(p["id"]) == "PENDING" and _ostat(oid) == "AWAITING_DEPOSIT"
    assert _sql("select count(*) from audit_logs where action='PAYMENT_ORPHAN' and entity_id=:p", p=p["id"]) == 1
    assert [x["needs_refund"] for x in client.get(f"{API}/orders/{oid}/payments", headers=cust).json()] == [True]
    # the customer then pays the right amount through the same QR and the order moves
    assert _hit(client, payos.webhook(txn, deposit))["result"] == "PROCESSED" and _ostat(oid) == "CONFIRMED"


def test_changing_the_gateway_closes_the_old_link_and_a_late_transfer_to_it_is_flagged(client, cust, staff, wcat, payos):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    deposit = Decimal(order["deposit_amount"])
    first = _start(client, cust, oid)
    second = _start(client, cust, oid, "VNPAY")                                 # the customer switches to a card gateway
    assert payos.cancelled == [int(first["gateway_txn_id"])]                    # the QR is dead at payOS too
    assert _pstat(first["id"]) == "CANCELLED" and second["gateway"] == "VNPAY"
    out = _hit(client, payos.webhook(first["gateway_txn_id"], deposit))         # money still arrives through the old QR
    assert out["result"] == "IGNORED" and _ostat(oid) == "AWAITING_DEPOSIT"
    assert [p["needs_refund"] for p in client.get(f"{API}/orders/{oid}/payments", headers=cust).json()
            if p["id"] == first["id"]] == [True]


def test_refresh_asks_payos_when_the_webhook_is_late(client, cust, staff, wcat, payos):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _start(client, cust, oid)
    url = f"{API}/payments/{p['id']}/refresh"
    r = client.post(url, headers=cust)
    assert r.status_code == 200 and r.json()["result"] == "IGNORED" and _ostat(oid) == "AWAITING_DEPOSIT"
    payos.status[int(p["gateway_txn_id"])] = "PAID"
    r = client.post(url, headers=cust)
    assert r.json()["result"] == "PROCESSED" and r.json()["order_status"] == "CONFIRMED"
    assert client.post(url, headers=cust).json()["result"] == "ALREADY_PROCESSED"


def test_refresh_marks_an_expired_link_failed_and_a_dead_payos_is_a_502(client, cust, staff, wcat, payos):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _start(client, cust, oid)
    payos.status[int(p["gateway_txn_id"])] = "EXPIRED"
    assert client.post(f"{API}/payments/{p['id']}/refresh", headers=cust).json()["status"] == "FAILED"
    assert _ostat(oid) == "AWAITING_DEPOSIT"
    p2 = _start(client, cust, oid)
    assert p2["id"] != p["id"]
    payos.down = True
    r = client.post(f"{API}/payments/{p2['id']}/refresh", headers=cust)
    assert r.status_code == 502 and _err(r) == "GATEWAY_UNAVAILABLE" and _pstat(p2["id"]) == "PENDING"
    r = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "VNPAY"})
    assert r.status_code in (201, 503)                                          # the card gateway is unaffected by payOS being down


# ---- final payment: one transfer settles FINAL + SHIPPING -------------------------------------------------------------------
def test_final_payment_is_one_payos_transfer_for_the_whole_group(client, cust, staff, mgr, wcat, robot, tech, store, payos):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    _put(client, cust, oid, _delivery())
    r = _final(client, cust, oid, gateway="PAYOS").json()
    total = Decimal(r["total_due"])
    final, ship = r["payments"]
    assert final["mode"] == "LIVE" and final["pay_url"] == ship["pay_url"] and final["qr_code"] == ship["qr_code"]
    assert final["bank"]["amount"] == int(total)                                # the QR asks for the whole amount at once
    assert payos.links[int(final["gateway_txn_id"])]["amount"] == int(total)
    assert _final(client, cust, oid, gateway="PAYOS").json()["payments"][0]["id"] == final["id"]      # reused

    txn = final["gateway_txn_id"]
    wrong = _hit(client, payos.webhook(txn, total - Decimal(ship["amount"])))   # only the FINAL part: not the group's total
    assert wrong["result"] == "AMOUNT_MISMATCH" and _ostat(oid) == "AWAITING_FINAL_PAYMENT"
    assert _hit(client, payos.webhook(txn, total))["result"] == "PROCESSED"
    assert _ostat(oid) == "READY_TO_DELIVER"
    assert [x["s"] for x in _rows(oid) if x["t"] in ("FINAL", "SHIPPING")] == ["SUCCESS", "SUCCESS"]


# ---- concurrency ---------------------------------------------------------------------------------------------------------
def test_identical_webhooks_arriving_together_settle_exactly_once(client, cust, staff, wcat, payos):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _start(client, cust, oid)
    body = payos.webhook(p["gateway_txn_id"], Decimal(order["deposit_amount"]))
    def hit(_):
        with TestClient(app) as c:                                              # one client per thread: TestClient is not shared
            return c.post(HOOK, json=body).json()["result"]

    with ThreadPoolExecutor(3) as pool:
        results = sorted(pool.map(hit, range(3)))
    assert results == ["ALREADY_PROCESSED", "ALREADY_PROCESSED", "PROCESSED"]
    assert _ostat(oid) == "CONFIRMED"
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='CONFIRMED'", o=oid) == 1
