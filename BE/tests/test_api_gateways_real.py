"""Phase 4c-2a: payments through the REAL gateway adapters (VNPay, MoMo) in sandbox mode, on the real database.

The adapters are the real classes (signing, IPN checks, request building all run); only the HTTP calls to the gateways go to
httpx.MockTransport, and the "gateway's" signed callbacks are built by the test with the same secrets. So this proves that the
payment flow, the IPN handling, idempotency, concurrency and failure handling are right. It does NOT prove VNPay/MoMo accept
our messages: that needs their sandbox (see the VERIFICATION STATUS notes in integrations/vnpay.py and momo.py).

Orders are staged in MOCK mode (the default) and `real.on()` switches to sandbox mode afterwards.
"""
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.integrations import payment_gateway as gw
from app.integrations.momo import IPN_FIELDS, MomoGateway
from app.integrations.vnpay import VnpayGateway
from app.main import app
from tests.conftest import auth
from tests.test_api_delivery_final import _delivery, _final, _final_stage, _put, _rows
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _approved, _code, _hook, _signed
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import _err, cust, policy, staff, store, wcat  # noqa: F401

VNP_IPN = f"{API}/webhooks/payments/vnpay/ipn"
MOMO_IPN = f"{API}/webhooks/payments/momo/ipn"
PAY_URL = "https://pay.example.test/vpcpay.html"
RETURN_URL = "https://fe.example.test/payment/result"
BASE = "https://api.example.test"


class Real:
    """Switches the server to sandbox mode with the real adapters, talking to a scripted fake of the gateways' HTTP APIs."""

    def __init__(self, monkeypatch):
        self.mp = monkeypatch
        self.sent = {"momo_create": [], "momo_query": [], "vnp_query": []}
        self.state = {"momo_create_code": 0, "momo_query_code": 1000, "momo_amount": 0, "vnp_status": "01", "vnp_amount": 0,
                      "down": False}
        transport = httpx.MockTransport(self._handler)
        self.vn = VnpayGateway(tmn_code="TESTTMN", hash_secret="vn-secret", pay_url=PAY_URL,
                               api_url="https://vnp.example.test/api", mode="SANDBOX", transport=transport)
        self.mo = MomoGateway(partner_code="MOMOTEST", access_key="AK", secret_key="mo-secret",
                              endpoint="https://momo.example.test", mode="SANDBOX", transport=transport)

    def _handler(self, request: httpx.Request) -> httpx.Response:
        import json
        if self.state["down"]:
            return httpx.Response(503, text="maintenance")
        body = json.loads(request.content)
        if request.url.host == "momo.example.test" and request.url.path.endswith("/create"):
            self.sent["momo_create"].append(body)
            return httpx.Response(200, json={"resultCode": self.state["momo_create_code"],
                                             "payUrl": f"https://test-payment.momo.vn/pay/{body['orderId']}", "message": "ok"})
        if request.url.host == "momo.example.test":
            self.sent["momo_query"].append(body)
            return httpx.Response(200, json={"resultCode": self.state["momo_query_code"], "amount": self.state["momo_amount"],
                                             "orderId": body["orderId"]})
        self.sent["vnp_query"].append(body)
        return httpx.Response(200, json={"vnp_ResponseCode": "00", "vnp_TransactionStatus": self.state["vnp_status"],
                                         "vnp_Amount": str(self.state["vnp_amount"] * 100), "vnp_TxnRef": body["vnp_TxnRef"]})

    def on(self):
        s = get_settings()
        self.mp.setattr(s, "payment_mode", "sandbox")
        self.mp.setattr(s, "public_base_url", BASE)
        self.mp.setattr(s, "payment_return_url", RETURN_URL)
        gw.use_adapters({"VNPAY": self.vn, "MOMO": self.mo})
        return self

    def vnp_ipn(self, txn, amount, **over) -> dict:
        p = {"vnp_TmnCode": "TESTTMN", "vnp_Amount": str(int(amount) * 100), "vnp_TxnRef": txn, "vnp_ResponseCode": "00",
             "vnp_TransactionStatus": "00", "vnp_TransactionNo": "14000001", "vnp_BankCode": "NCB",
             "vnp_PayDate": "20261022101500", **over}
        return {**p, "vnp_SecureHash": self.vn.sign(p), "vnp_SecureHashType": "HmacSHA512"}

    def momo_ipn(self, txn, amount, **over) -> dict:
        body = {"partnerCode": "MOMOTEST", "orderId": txn, "requestId": "req-1", "amount": int(amount),
                "orderInfo": "Thanh toan don", "orderType": "momo_wallet", "transId": 2820001, "resultCode": 0,
                "message": "Successful.", "payType": "qr", "responseTime": 1792000000000, "extraData": "", **over}
        raw = "&".join(f"{k}={'AK' if k == 'accessKey' else body.get(k, '')}" for k in IPN_FIELDS)
        return {**body, "signature": self.mo.sign(raw)}


@pytest.fixture
def real(monkeypatch):
    gw.use_adapters(None)
    yield Real(monkeypatch)
    gw.use_adapters(None)


# ---- helpers ------------------------------------------------------------------------------------------
def _start(client, cust, oid, gateway, expect=201):
    r = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": gateway})
    assert r.status_code == expect, r.text
    return r.json()


def _ostat(oid):
    return _sql("select order_status::text from orders where id=:o", o=oid)


def _pstat(pid):
    return _sql("select status::text from payments where id=:p", p=pid)


def _vnp(client, params):
    r = client.get(VNP_IPN, params=params)
    assert r.status_code == 200, r.text                       # VNPay is always answered with HTTP 200
    return r.json()


def _query(url: str) -> dict:
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}


# ---- which gateways the customer may pick -----------------------------------------------------------------
def test_gateways_endpoint_follows_the_mode_and_the_configuration(client, cust, real):
    url = f"{API}/payments/gateways"
    assert client.get(url).status_code == 401
    off = {"gateway": "PAYOS", "mode": "LIVE", "enabled": False}                # payOS needs its keys, whatever the mode
    assert client.get(url, headers=cust).json() == [{"gateway": "VNPAY", "mode": "MOCK", "enabled": True},
                                                    {"gateway": "MOMO", "mode": "MOCK", "enabled": True}, off]
    real.on()
    assert client.get(url, headers=cust).json() == [{"gateway": "VNPAY", "mode": "SANDBOX", "enabled": True},
                                                    {"gateway": "MOMO", "mode": "SANDBOX", "enabled": True}, off]
    gw.use_adapters(None)                                   # sandbox mode without credentials on the server
    assert [g["enabled"] for g in client.get(url, headers=cust).json()] == [False, False, False]
    for role in ("STAFF", "MANAGER", "TECHNICAL_STAFF", "ADMIN"):
        assert client.get(url, headers=auth(client, role)).status_code == 403


# ---- VNPay deposit, end to end ----------------------------------------------------------------------------
def test_vnpay_deposit_from_link_to_confirmed_order(client, cust, staff, wcat, real):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    deposit, code = Decimal(order["deposit_amount"]), _code(oid)
    real.on()

    p = _start(client, cust, oid, "VNPAY")
    assert p["mode"] == "SANDBOX" and p["status"] == "PENDING" and p["checkout_path"] is None
    assert p["gateway_txn_id"].startswith("VHRS") and p["pay_url"].startswith(PAY_URL + "?")
    assert datetime.fromisoformat(p["pay_url_expires_at"]) > datetime.now(timezone.utc)
    link = _query(p["pay_url"])
    assert link["vnp_Amount"] == str(int(deposit) * 100) and link["vnp_TxnRef"] == p["gateway_txn_id"]
    assert link["vnp_ReturnUrl"] == f"{RETURN_URL}?order_id={oid}" and code in link["vnp_OrderInfo"] and real.vn.verify(link)
    assert _start(client, cust, oid, "VNPAY")["id"] == p["id"]                  # same intent while the link lives: reused
    txn = p["gateway_txn_id"]

    # a callback that is not from VNPay, or is about something else, never moves the order
    assert _vnp(client, {**real.vnp_ipn(txn, deposit), "vnp_Amount": "100"})["RspCode"] == "97"
    assert _vnp(client, {"vnp_TxnRef": txn})["RspCode"] == "97"
    assert _vnp(client, real.vnp_ipn("VHRSNOSUCHTXN", deposit))["RspCode"] == "01"
    assert _vnp(client, real.vnp_ipn(txn, deposit + 100))["RspCode"] == "04"
    assert _sql("select count(*) from audit_logs where action='PAYMENT_MISMATCH' and entity_id=:p", p=p["id"]) == 1
    assert _ostat(oid) == "AWAITING_DEPOSIT" and _pstat(p["id"]) == "PENDING"

    # the simulated door is shut in real modes (its key is derived from JWT_SECRET)
    body, sig = _signed(txn, code, int(deposit))
    forged = _hook(client, "VNPAY", body, sig)
    assert forged.status_code == 403 and _err(forged) == "MOCK_WEBHOOK_DISABLED"
    r = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert r.status_code == 409 and _err(r) == "NOT_A_MOCK_PAYMENT" and _ostat(oid) == "AWAITING_DEPOSIT"

    # the customer abandons: VNPay reports a failure, the customer may try again
    assert _vnp(client, real.vnp_ipn(txn, deposit, vnp_ResponseCode="24", vnp_TransactionStatus="02"))["RspCode"] == "00"
    assert _pstat(p["id"]) == "FAILED" and _ostat(oid) == "AWAITING_DEPOSIT"
    p2 = _start(client, cust, oid, "VNPAY")
    assert p2["id"] != p["id"] and p2["gateway_txn_id"] != txn

    ok = real.vnp_ipn(p2["gateway_txn_id"], deposit)
    assert _vnp(client, ok)["RspCode"] == "00"
    assert _ostat(oid) == "CONFIRMED" and _sql("select production_status::text from orders where id=:o", o=oid) == "PENDING_SCHEDULE"
    assert _pstat(p2["id"]) == "SUCCESS"
    assert _sql("select gateway_payload->'webhook'->>'vnp_TransactionNo' from payments where id=:p", p=p2["id"]) == "14000001"
    assert _sql("select count(*) from audit_logs where action='PAYMENT_SUCCESS' and entity_id=:p", p=p2["id"]) == 1
    assert _vnp(client, ok)["RspCode"] == "02"                                     # VNPay retries: nothing happens twice
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='CONFIRMED'", o=oid) == 1
    assert _sql("select count(*) from audit_logs where action='PAYMENT_SUCCESS' and entity_id=:p", p=p2["id"]) == 1
    shown = {x["id"]: x for x in client.get(f"{API}/orders/{oid}/payments", headers=cust).json()}
    assert shown[p2["id"]]["status"] == "SUCCESS" and shown[p2["id"]]["pay_url"] is None
    assert _err(client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "VNPAY"})) in (
        "DEPOSIT_NOT_EXPECTED", "DEPOSIT_ALREADY_PAID")


# ---- MoMo deposit, end to end -----------------------------------------------------------------------------
def test_momo_deposit_from_link_to_confirmed_order(client, cust, staff, wcat, real):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    deposit = Decimal(order["deposit_amount"])
    real.on()

    p = _start(client, cust, oid, "MOMO")
    assert p["mode"] == "SANDBOX" and p["pay_url"] == f"https://test-payment.momo.vn/pay/{p['gateway_txn_id']}"
    sent = real.sent["momo_create"][-1]
    assert sent["amount"] == int(deposit) and sent["orderId"] == p["gateway_txn_id"] and sent["redirectUrl"] == f"{RETURN_URL}?order_id={oid}"
    assert sent["ipnUrl"] == f"{BASE}/api/v1/webhooks/payments/momo/ipn" and sent["partnerCode"] == "MOMOTEST"
    assert _start(client, cust, oid, "MOMO")["id"] == p["id"] and len(real.sent["momo_create"]) == 1     # reused, MoMo not asked again
    txn = p["gateway_txn_id"]

    assert client.post(MOMO_IPN, json={**real.momo_ipn(txn, deposit), "amount": 1}).status_code == 401
    assert client.post(MOMO_IPN, json={"orderId": txn}).status_code == 401
    forged = real.momo_ipn(txn, deposit, partnerCode="OTHERSHOP")
    assert client.post(MOMO_IPN, json=forged).status_code == 401
    r = client.post(MOMO_IPN, json=real.momo_ipn(txn, deposit + 100))
    assert r.status_code == 422 and _err(r) == "PAYMENT_MISMATCH"
    for bad in (None, [1, 2], "x"):
        assert client.post(MOMO_IPN, json=bad).status_code == 422
    assert client.post(MOMO_IPN, content=b"not json", headers={"Content-Type": "application/json"}).status_code == 422
    assert _ostat(oid) == "AWAITING_DEPOSIT" and _pstat(p["id"]) == "PENDING"

    assert client.post(MOMO_IPN, json=real.momo_ipn(txn, deposit, resultCode=9000)).status_code == 204   # not final yet
    assert _pstat(p["id"]) == "PENDING"
    assert client.post(MOMO_IPN, json=real.momo_ipn(txn, deposit, resultCode=1006)).status_code == 204    # customer declined
    assert _pstat(p["id"]) == "FAILED" and _ostat(oid) == "AWAITING_DEPOSIT"

    p2 = _start(client, cust, oid, "MOMO")
    assert p2["id"] != p["id"]
    ok = real.momo_ipn(p2["gateway_txn_id"], deposit)
    assert client.post(MOMO_IPN, json=ok).status_code == 204
    assert _ostat(oid) == "CONFIRMED" and _pstat(p2["id"]) == "SUCCESS"
    assert client.post(MOMO_IPN, json=ok).status_code == 204                                  # duplicate: acknowledged, no effect
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='CONFIRMED'", o=oid) == 1
    assert _sql("select gateway_payload->'webhook'->>'transId' from payments where id=:p", p=p2["id"]) == "2820001"


# ---- when the gateway cannot be reached or is not configured ------------------------------------------------
def test_a_payment_that_cannot_be_opened_leaves_nothing_behind(client, cust, staff, wcat, real, monkeypatch):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    real.on()

    def rows():
        return _sql("select count(*) from payments where order_id=:o", o=oid)

    real.state["momo_create_code"] = 1006
    r = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "MOMO"})
    assert r.status_code == 502 and _err(r) == "GATEWAY_REJECTED" and rows() == 0
    real.state["momo_create_code"] = 0

    real.state["down"] = True
    r = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "MOMO"})
    assert r.status_code == 502 and _err(r) == "GATEWAY_UNAVAILABLE" and rows() == 0
    real.state["down"] = False

    monkeypatch.setattr(get_settings(), "public_base_url", None)             # MoMo needs a public IPN address
    r = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "MOMO"})
    assert r.status_code == 503 and _err(r) == "GATEWAY_NOT_CONFIGURED" and rows() == 0
    monkeypatch.setattr(get_settings(), "public_base_url", BASE)

    gw.use_adapters(None)                                                   # sandbox mode, no credentials on the server
    for g in ("VNPAY", "MOMO"):
        r = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": g})
        assert r.status_code == 503 and _err(r) == "GATEWAY_NOT_CONFIGURED"
    assert rows() == 0 and _ostat(oid) == "AWAITING_DEPOSIT"


# ---- links expire, intents change, late money --------------------------------------------------------------
def test_expired_link_is_replaced_and_switching_gateway_closes_the_old_one(client, cust, staff, wcat, real):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    real.on()
    p = _start(client, cust, oid, "VNPAY")
    old = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    _sql("""update payments set gateway_payload = jsonb_set(gateway_payload, '{pay_url_expires_at}', to_jsonb(cast(:t as text)))
            where id=:p returning 1""", t=old, p=p["id"])
    p2 = _start(client, cust, oid, "VNPAY")
    assert p2["id"] != p["id"] and _pstat(p["id"]) == "CANCELLED" and _pstat(p2["id"]) == "PENDING"
    p3 = _start(client, cust, oid, "MOMO")
    assert p3["gateway"] == "MOMO" and _pstat(p2["id"]) == "CANCELLED"
    assert [x["status"] for x in client.get(f"{API}/orders/{oid}/payments", headers=cust).json()
            if x["status"] == "PENDING"] == ["PENDING"]                               # one open intent at a time


def test_money_that_arrives_on_a_closed_payment_is_kept_for_a_refund(client, cust, staff, wcat, real):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    deposit = Decimal(order["deposit_amount"])
    real.on()
    p1 = _start(client, cust, oid, "VNPAY")
    p2 = _start(client, cust, oid, "MOMO")                                           # p1 is closed by this change of mind
    assert _pstat(p1["id"]) == "CANCELLED"
    late = real.vnp_ipn(p1["gateway_txn_id"], deposit)
    assert _vnp(client, late)["RspCode"] == "00"                                     # VNPay is told "got it" so it stops retrying
    assert _vnp(client, late)["RspCode"] == "00"
    assert _ostat(oid) == "AWAITING_DEPOSIT" and _pstat(p1["id"]) == "CANCELLED"     # the order is not confirmed by it
    assert _sql("select (gateway_payload->>'needs_refund')::bool from payments where id=:p", p=p1["id"]) is True
    assert _sql("select count(*) from audit_logs where action='PAYMENT_ORPHAN' and entity_id=:p", p=p1["id"]) == 1
    shown = {x["id"]: x for x in client.get(f"{API}/orders/{oid}/payments", headers=cust).json()}
    assert shown[p1["id"]]["needs_refund"] is True and shown[p2["id"]]["needs_refund"] is False


# ---- refresh: ask the gateway when the IPN is late -----------------------------------------------------------
def test_refresh_settles_from_the_gateway_answer(client, cust, staff, wcat, real):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    deposit = Decimal(order["deposit_amount"])
    real.on()
    url = lambda pid: f"{API}/payments/{pid}/refresh"
    p = _start(client, cust, oid, "VNPAY")
    real.state.update(vnp_status="01", vnp_amount=int(deposit))                      # VNPay: not completed yet
    r = client.post(url(p["id"]), headers=cust)
    assert r.status_code == 200 and r.json() == {"result": "IGNORED", "status": "PENDING", "order_status": "AWAITING_DEPOSIT",
                                                 "needs_refund": None}
    q_sent = real.sent["vnp_query"][-1]
    assert q_sent["vnp_TxnRef"] == p["gateway_txn_id"] and q_sent["vnp_Command"] == "querydr" and q_sent["vnp_TransactionDate"]

    real.state["down"] = True
    r = client.post(url(p["id"]), headers=cust)
    assert r.status_code == 502 and _err(r) == "GATEWAY_UNAVAILABLE" and _pstat(p["id"]) == "PENDING"
    real.state["down"] = False

    assert client.post(url(p["id"]), headers=auth(client, "CUSTOMER")).status_code == 404       # someone else's payment
    assert client.post(url(999999999), headers=cust).status_code == 404

    real.state["vnp_status"] = "00"
    r = client.post(url(p["id"]), headers=cust)
    assert r.status_code == 200 and r.json()["result"] == "PROCESSED" and r.json()["order_status"] == "CONFIRMED"
    assert _ostat(oid) == "CONFIRMED" and _pstat(p["id"]) == "SUCCESS"
    again = client.post(url(p["id"]), headers=cust).json()
    assert again["result"] == "ALREADY_PROCESSED" and again["status"] == "SUCCESS"
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='CONFIRMED'", o=oid) == 1


def test_refresh_with_momo_and_with_a_simulated_payment(client, cust, staff, wcat, real):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    deposit = Decimal(order["deposit_amount"])
    real.on()
    real.state.update(momo_amount=int(deposit))
    p = _start(client, cust, oid, "MOMO")
    url = f"{API}/payments/{p['id']}/refresh"
    real.state["momo_query_code"] = 7002                                              # waiting for the customer in the app
    assert client.post(url, headers=cust).json()["result"] == "IGNORED"
    real.state["momo_query_code"] = 1006                                              # the customer declined
    r = client.post(url, headers=cust).json()
    assert r["result"] == "PROCESSED" and r["status"] == "FAILED" and _ostat(oid) == "AWAITING_DEPOSIT"
    assert real.sent["momo_query"][-1]["orderId"] == p["gateway_txn_id"]

    p2 = _start(client, cust, oid, "MOMO")
    real.state["momo_query_code"] = 0
    r = client.post(f"{API}/payments/{p2['id']}/refresh", headers=cust).json()
    assert r["result"] == "PROCESSED" and r["order_status"] == "CONFIRMED"

    _sql("update payments set status='PENDING', gateway_payload='{\"mode\": \"MOCK\"}'::jsonb where id=:p returning 1", p=p["id"])
    r = client.post(url, headers=cust)                                                # a simulated payment has no gateway to ask
    assert r.status_code == 409 and _err(r) == "NOT_A_REAL_PAYMENT"


# ---- final payment (FINAL + SHIPPING in one gateway transaction) ----------------------------------------------
def test_final_payment_is_one_vnpay_transaction_that_settles_both_rows(client, cust, staff, mgr, wcat, robot, tech, store, real):
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)          # staged in MOCK mode
    _put(client, cust, oid, _delivery())
    real.on()
    r = _final(client, cust, oid).json()
    total = Decimal(r["total_due"])
    final, ship = r["payments"]
    assert {final["type"], ship["type"]} == {"FINAL", "SHIPPING"} and final["mode"] == "SANDBOX"
    assert final["pay_url"] and final["pay_url"] == ship["pay_url"]                  # one link pays both rows
    link = _query(final["pay_url"])
    assert link["vnp_Amount"] == str(int(total) * 100) and link["vnp_TxnRef"] == final["gateway_txn_id"]
    assert ship["gateway_txn_id"] == final["gateway_txn_id"] + ":SHIP"
    assert _final(client, cust, oid).json()["payments"][0]["id"] == final["id"]      # same intent reused

    txn = final["gateway_txn_id"]
    assert _vnp(client, real.vnp_ipn(txn, total - Decimal(ship["amount"])))["RspCode"] == "04"    # not the group's total
    assert _ostat(oid) == "AWAITING_FINAL_PAYMENT"
    assert _vnp(client, real.vnp_ipn(txn, total))["RspCode"] == "00"
    assert _ostat(oid) == "READY_TO_DELIVER"
    assert [x["s"] for x in _rows(oid) if x["t"] in ("FINAL", "SHIPPING")] == ["SUCCESS", "SUCCESS"]
    assert _vnp(client, real.vnp_ipn(txn, total))["RspCode"] == "02"
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='READY_TO_DELIVER'", o=oid) == 1


# ---- concurrency -------------------------------------------------------------------------------------------------
def test_identical_ipns_arriving_together_settle_exactly_once(client, cust, staff, wcat, real):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    deposit = Decimal(order["deposit_amount"])
    real.on()
    p = _start(client, cust, oid, "VNPAY")
    params = real.vnp_ipn(p["gateway_txn_id"], deposit)

    def hit(_):
        with TestClient(app) as c:
            return c.get(VNP_IPN, params=params).json()["RspCode"]

    with ThreadPoolExecutor(3) as ex:
        codes = sorted(ex.map(hit, range(3)))
    assert codes == ["00", "02", "02"], codes
    assert _ostat(oid) == "CONFIRMED"
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='CONFIRMED'", o=oid) == 1
    assert _sql("select count(*) from audit_logs where action='PAYMENT_SUCCESS' and entity_id=:p", p=p["id"]) == 1


# ---- mock mode: the real doors do not open ---------------------------------------------------------------------------
def test_real_ipn_endpoints_verify_nothing_while_payments_are_simulated(client, cust, staff, wcat, real):
    oid, q, order = _approved(client, cust, staff[0], wcat)
    p = _start(client, cust, oid, "VNPAY")                                           # MOCK mode: a simulated payment
    assert p["mode"] == "MOCK" and p["pay_url"] is None and p["checkout_path"]
    # a message signed with a key we know is still worthless: nothing real is configured to be believed
    assert _vnp(client, real.vnp_ipn(p["gateway_txn_id"], Decimal(order["deposit_amount"])))["RspCode"] == "97"
    assert client.post(MOMO_IPN, json=real.momo_ipn(p["gateway_txn_id"], Decimal(order["deposit_amount"]))).status_code == 401
    assert _ostat(oid) == "AWAITING_DEPOSIT" and _pstat(p["id"]) == "PENDING"
