"""Phase 4c-2d: the payOS adapter (VietQR bank transfer). No database: the HTTP calls go to httpx.MockTransport and the
"payOS" callbacks are signed by the test with the same checksum key, so this proves self-consistency (signing recipes as read
from payOS's official SDK, request shape, parsing, failures), NOT that payOS accepts our messages. See the VERIFICATION STATUS
note in app/integrations/payos.py."""
import hashlib
import hmac
import json

import httpx
import pytest

from app.core.errors import AppError
from app.integrations import payment_gateway as gw
from app.integrations.payos import DESCRIPTION_MAX, PayosGateway, _query_string

KEY = "checksum-key-for-tests"
RETURN = "https://fe.example.test/payment/result?order_id=7"


class Fake:
    def __init__(self):
        self.calls, self.reply, self.down = [], {}, False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(503, text="maintenance")
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, dict(request.headers), body))
        key = (request.method, request.url.path.rsplit("/", 1)[-1] if "/payment-requests/" in request.url.path else request.url.path)
        return httpx.Response(200, json=self.reply.get(key, self.reply.get("default", {})))


@pytest.fixture
def fake():
    return Fake()


@pytest.fixture
def payos(fake):
    return PayosGateway(client_id="cid", api_key="akey", checksum_key=KEY, base_url="https://payos.example.test/",
                        transport=httpx.MockTransport(fake))


def _created(**over):
    data = {"bin": "970422", "accountNumber": "0123456789", "accountName": "HOANG ANH KHOA", "amount": 100000,
            "description": "VHRS-6645185F", "orderCode": 1, "currency": "VND", "paymentLinkId": "plid-1", "status": "PENDING",
            "checkoutUrl": "https://pay.payos.vn/web/plid-1", "qrCode": "00020101021238...6304ABCD", **over}
    return {"code": "00", "desc": "success", "data": data, "signature": "x"}


def _webhook(payos, *, amount=100000, order_code=123456, code="00", data_code="00", **over):
    data = {"orderCode": order_code, "amount": amount, "description": "VHRS-6645185F", "accountNumber": "0123456789",
            "reference": "FT26295", "transactionDateTime": "2026-10-22 14:20:00", "currency": "VND", "paymentLinkId": "plid-1",
            "code": data_code, "desc": "success", "counterAccountBankId": "", "counterAccountName": None, **over}
    return {"code": code, "desc": "success", "success": code == "00", "data": data, "signature": payos.sign_data(data)}


# ---- signing -------------------------------------------------------------------------------------------------
def test_request_signature_follows_the_documented_recipe(payos):
    raw = "amount=100000&cancelUrl=https://c&description=VHRS-1&orderCode=5&returnUrl=https://r"
    want = hmac.new(KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()
    assert payos.sign_request(amount=100000, cancel_url="https://c", description="VHRS-1", order_code=5,
                              return_url="https://r") == want


def test_data_signature_sorts_keys_and_blanks_none():
    assert _query_string({"b": 2, "a": None, "c": True, "d": "x y"}) == "a=&b=2&c=true&d=x y"


def test_txn_ids_are_integers_in_the_safe_range_and_distinct(payos):
    ids = {payos.new_txn_id() for _ in range(200)}
    assert len(ids) == 200 and all(i.isdigit() and int(i) < 2 ** 53 for i in ids)


# ---- creating the link -------------------------------------------------------------------------------------------
def test_create_payment_sends_a_signed_request_and_returns_the_link(payos, fake):
    fake.reply[("POST", "/v2/payment-requests")] = _created()
    link = payos.create_payment(txn_ref="555", amount=100000, order_info="Thanh toan don VHRS-6645185F", client_ip=None,
                                return_url=RETURN, ipn_url=None, expire_minutes=15)
    method, path, headers, body = fake.calls[0]
    assert (method, path) == ("POST", "/v2/payment-requests")
    assert headers["x-client-id"] == "cid" and headers["x-api-key"] == "akey"
    assert body["orderCode"] == 555 and body["amount"] == 100000 and body["description"] == "VHRS-6645185F"
    assert body["returnUrl"] == RETURN and body["cancelUrl"] == RETURN + "&cancelled=1"
    assert body["signature"] == payos.sign_request(amount=100000, cancel_url=body["cancelUrl"], description="VHRS-6645185F",
                                                   order_code=555, return_url=RETURN)
    assert body["items"] == [{"name": "VHRS-6645185F", "quantity": 1, "price": 100000}]
    assert link.url == "https://pay.payos.vn/web/plid-1" and link.expires_at.timestamp() == pytest.approx(body["expiredAt"], abs=1)
    assert link.meta["qr_code"].startswith("0002") and link.meta["account_number"] == "0123456789"
    assert link.meta["description"] == "VHRS-6645185F"


def test_description_is_cut_to_the_limit(payos, fake):
    fake.reply[("POST", "/v2/payment-requests")] = _created()
    payos.create_payment(txn_ref="1", amount=5000, order_info="Thanh toan don " + "X" * 40, client_ip=None, return_url=RETURN,
                         ipn_url=None, expire_minutes=15)
    assert len(fake.calls[0][3]["description"]) == DESCRIPTION_MAX


def test_create_payment_failures(payos, fake):
    kw = dict(txn_ref="1", amount=5000, order_info="Thanh toan don A", client_ip=None, return_url=RETURN, ipn_url=None,
              expire_minutes=15)
    with pytest.raises(AppError) as e:
        payos.create_payment(**{**kw, "amount": 0})
    assert e.value.code == "INVALID_AMOUNT"
    fake.reply[("POST", "/v2/payment-requests")] = {"code": "20", "desc": "Thông tin không hợp lệ", "data": None}
    with pytest.raises(AppError) as e:
        payos.create_payment(**kw)
    assert (e.value.status, e.value.code) == (502, "GATEWAY_REJECTED")
    fake.reply[("POST", "/v2/payment-requests")] = {"code": "00", "desc": "ok", "data": {"checkoutUrl": ""}}
    with pytest.raises(AppError) as e:
        payos.create_payment(**kw)
    assert e.value.code == "GATEWAY_REJECTED"
    fake.down = True
    with pytest.raises(AppError) as e:
        payos.create_payment(**kw)
    assert (e.value.status, e.value.code) == (502, "GATEWAY_UNAVAILABLE")


# ---- the webhook ---------------------------------------------------------------------------------------------------
def test_a_valid_webhook_is_parsed(payos):
    r = payos.parse_webhook(_webhook(payos, amount=250000, order_code=987))
    assert (r.txn_ref, r.amount, r.success, r.final) == ("987", 250000, True, True)


def test_a_tampered_or_unsigned_webhook_is_refused(payos):
    body = _webhook(payos)
    for bad in ({**body, "data": {**body["data"], "amount": 1}}, {**body, "signature": ""}, {**body, "signature": "0" * 64},
                {"code": "00", "desc": "x", "data": body["data"]}, {**body, "data": "not a dict"}):
        with pytest.raises(gw.InvalidSignature):
            payos.parse_webhook(bad)
    other = PayosGateway(client_id="c", api_key="k", checksum_key="another-key", base_url="https://x")
    with pytest.raises(gw.InvalidSignature):
        other.parse_webhook(body)


def test_a_non_success_code_is_not_a_payment(payos):
    assert payos.parse_webhook(_webhook(payos, code="01")).success is False
    assert payos.parse_webhook(_webhook(payos, data_code="02")).success is False


def test_a_signed_but_unreadable_webhook_is_malformed(payos):
    data = {"orderCode": "abc", "amount": 5, "code": "00"}
    with pytest.raises(gw.MalformedCallback):
        payos.parse_webhook({"code": "00", "desc": "", "data": data, "signature": payos.sign_data(data)})


# ---- query / cancel / register ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("status,ok,final", [("PAID", True, True), ("CANCELLED", False, True), ("EXPIRED", False, True),
                                             ("FAILED", False, True), ("PENDING", False, False), ("PROCESSING", False, False),
                                             ("UNDERPAID", False, False)])
def test_query_maps_the_link_status(payos, fake, status, ok, final):
    fake.reply[("GET", "777")] = {"code": "00", "desc": "ok", "data": {"id": "p", "orderCode": 777, "amount": 90000,
                                                                       "amountPaid": 90000 if status == "PAID" else 0,
                                                                       "status": status}}
    r = payos.query(txn_ref="777", meta={}, client_ip=None)
    assert (r.success, r.final, r.amount) == (ok, final, 90000)
    assert fake.calls[0][:2] == ("GET", "/v2/payment-requests/777")


def test_query_of_an_unknown_link_says_nothing(payos, fake):
    fake.reply["default"] = {"code": "101", "desc": "not found", "data": None}
    assert payos.query(txn_ref="1", meta={}, client_ip=None) is None


def test_cancel_is_best_effort_and_confirm_webhook_posts_the_address(payos, fake):
    payos.cancel("42")
    assert fake.calls[0][:2] == ("POST", "/v2/payment-requests/42/cancel") and fake.calls[0][3]["cancellationReason"]
    fake.down = True
    payos.cancel("42")                                                   # a dead payOS must not break the caller
    fake.down = False
    fake.reply["default"] = {"code": "00", "desc": "ok"}
    assert payos.confirm_webhook("https://api.example.test/hook")["code"] == "00"
    assert fake.calls[-1][1] == "/confirm-webhook" and fake.calls[-1][3] == {"webhookUrl": "https://api.example.test/hook"}
