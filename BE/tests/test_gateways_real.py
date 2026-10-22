"""VNPay and MoMo adapters and the adapter registry. No database, no network: HTTP goes to httpx.MockTransport.

IMPORTANT: these tests prove the adapters are self-consistent (the signature they produce is the one they accept, tampering
breaks it, statuses map as intended, errors become the right API errors) and that the signed strings are built exactly as
written here. They do NOT prove VNPay or MoMo accept them: that needs the gateways' sandbox (see the VERIFICATION STATUS
notes in integrations/vnpay.py and integrations/momo.py).
"""
import hashlib
import hmac
import json
import urllib.parse
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations import payment_gateway as gw
from app.integrations.momo import IPN_FIELDS, MomoGateway
from app.integrations.vnpay import VN_TZ, VnpayGateway, ascii_text, hash_data
from app.models.ops import PaymentGateway

VN_SECRET, MOMO_SECRET = "VNPAY-SECRET", "MOMO-SECRET"


def vnpay(handler=None) -> VnpayGateway:
    return VnpayGateway(tmn_code="TMN1", hash_secret=VN_SECRET, pay_url="https://pay.example/vpcpay.html",
                        api_url="https://api.example/transaction", mode="SANDBOX",
                        transport=httpx.MockTransport(handler) if handler else None)


def momo(handler=None) -> MomoGateway:
    return MomoGateway(partner_code="MOMOP", access_key="AK", secret_key=MOMO_SECRET, endpoint="https://momo.example",
                       mode="SANDBOX", transport=httpx.MockTransport(handler) if handler else None)


def _hmac(secret: str, text: str, algo) -> str:
    return hmac.new(secret.encode(), text.encode(), algo).hexdigest()


# ===================================================================================== VNPay
def test_vnpay_hash_data_is_sorted_encoded_and_skips_empty_and_secure_fields():
    data = hash_data({"vnp_B": "2", "vnp_A": "1 x/y", "vnp_Empty": "", "vnp_None": None,
                      "vnp_SecureHash": "zzz", "vnp_SecureHashType": "SHA512"})
    assert data == "vnp_A=1+x%2Fy&vnp_B=2"


def test_vnpay_signature_is_hmac_sha512_of_the_hash_data():
    g = vnpay()
    params = {"vnp_B": "2", "vnp_A": "1 x"}
    assert g.sign(params) == _hmac(VN_SECRET, "vnp_A=1+x&vnp_B=2", hashlib.sha512)
    assert len(g.sign(params)) == 128


def test_vnpay_ascii_text_removes_accents_and_symbols():
    assert ascii_text("Thanh toán đơn VHRS-001 (cọc) #1") == "Thanh toan don VHRS-001 coc 1"
    assert ascii_text("!!!") == "Thanh toan don hang"
    assert len(ascii_text("a" * 300)) == 100


def test_vnpay_payment_url_carries_a_valid_signature_and_the_amount_times_100():
    g = vnpay()
    now = datetime(2026, 10, 22, 9, 30, 0, tzinfo=VN_TZ)
    link = g.create_payment(txn_ref="VHRSABC", amount=199800, order_info="Thanh toán đơn VHRS-1", client_ip="203.0.113.7",
                            return_url="https://fe.example/payment/result", ipn_url=None, expire_minutes=15, now=now)
    url = urllib.parse.urlsplit(link.url)
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://pay.example/vpcpay.html"
    q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
    assert q["vnp_Amount"] == "19980000" and q["vnp_TxnRef"] == "VHRSABC" and q["vnp_TmnCode"] == "TMN1"
    assert q["vnp_Command"] == "pay" and q["vnp_Version"] == "2.1.0" and q["vnp_CurrCode"] == "VND"
    assert q["vnp_OrderInfo"] == "Thanh toan don VHRS-1" and q["vnp_ReturnUrl"] == "https://fe.example/payment/result"
    assert q["vnp_IpAddr"] == "203.0.113.7"
    assert q["vnp_CreateDate"] == "20261022093000" and q["vnp_ExpireDate"] == "20261022094500"      # GMT+7, +15 min
    assert link.expires_at == now + timedelta(minutes=15)
    assert link.meta["vnp_create_date"] == "20261022093000"
    assert g.verify(q)                                                                              # what we sign we accept
    assert g.verify({**q, "vnp_SecureHash": q["vnp_SecureHash"].upper()})                           # hex case does not matter


def test_vnpay_signature_breaks_on_any_change_and_without_a_hash():
    g = vnpay()
    params = {"vnp_Amount": "100", "vnp_TxnRef": "A"}
    signed = {**params, "vnp_SecureHash": g.sign(params)}
    assert g.verify(signed)
    assert not g.verify({**signed, "vnp_Amount": "200"})
    assert not g.verify({**signed, "vnp_TxnRef": "B"})
    assert not g.verify({**signed, "vnp_Extra": "1"})                  # an added field changes the signed string
    assert not g.verify(params) and not g.verify({**params, "vnp_SecureHash": ""})
    assert not VnpayGateway(tmn_code="TMN1", hash_secret="OTHER", pay_url="", api_url="", mode="SANDBOX").verify(signed)


def test_vnpay_rejects_a_non_positive_amount():
    for amount in (0, -100):
        with pytest.raises(AppError) as exc:
            vnpay().create_payment(txn_ref="A", amount=amount, order_info="x", client_ip=None, return_url="https://r",
                                   ipn_url=None, expire_minutes=15)
        assert exc.value.code == "INVALID_AMOUNT"


def _vn_ipn(g: VnpayGateway, **over) -> dict:
    p = {"vnp_TmnCode": "TMN1", "vnp_Amount": "19980000", "vnp_TxnRef": "VHRSABC", "vnp_ResponseCode": "00",
         "vnp_TransactionStatus": "00", "vnp_TransactionNo": "14000001", "vnp_BankCode": "NCB", **over}
    return {**p, "vnp_SecureHash": g.sign(p), "vnp_SecureHashType": "HmacSHA512"}


def test_vnpay_ipn_parsing():
    g = vnpay()
    ok = g.parse_ipn(_vn_ipn(g))
    assert (ok.txn_ref, ok.amount, ok.success, ok.final) == ("VHRSABC", 199800, True, True)
    for over in ({"vnp_ResponseCode": "24"}, {"vnp_TransactionStatus": "02"}, {"vnp_ResponseCode": "07"}):
        r = g.parse_ipn(_vn_ipn(g, **over))
        assert r.success is False and r.final is True, over           # a failed payment is final: the customer must start again
    with pytest.raises(gw.InvalidSignature):
        g.parse_ipn({**_vn_ipn(g), "vnp_Amount": "1"})
    with pytest.raises(gw.InvalidSignature):
        g.parse_ipn({"vnp_Amount": "100"})
    for bad in ({"vnp_Amount": "19980050"}, {"vnp_Amount": "0"}, {"vnp_Amount": "abc"}, {"vnp_TxnRef": None}):
        p = {k: v for k, v in _vn_ipn(g, **bad).items() if v is not None}
        if bad.get("vnp_TxnRef", 1) is None:
            p.pop("vnp_TxnRef", None)
            p["vnp_SecureHash"] = g.sign(p)
        with pytest.raises(gw.MalformedCallback):
            g.parse_ipn(p)


def test_vnpay_ack_shape():
    assert vnpay().ipn_response("00", "Confirm Success") == {"RspCode": "00", "Message": "Confirm Success"}


def _vn_query(g_status: str, code="00", amount="19980000"):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"vnp_ResponseCode": code, "vnp_TransactionStatus": g_status, "vnp_Amount": amount,
                                         "vnp_TxnRef": "VHRSABC"})
    return seen, handler


def test_vnpay_query_maps_statuses_and_signs_the_request():
    meta = {"vnp_create_date": "20261022093000", "vnp_order_info": "Thanh toan don VHRS-1"}
    for status, expect in (("00", (True, True)), ("01", (False, False)), ("02", (False, True)), ("04", (False, True))):
        seen, handler = _vn_query(status)
        r = vnpay(handler).query(txn_ref="VHRSABC", meta=meta, client_ip="203.0.113.7")
        assert (r.success, r.final) == expect and r.amount == 199800, status
    body = seen[0]
    assert body["vnp_Command"] == "querydr" and body["vnp_TxnRef"] == "VHRSABC" and body["vnp_TmnCode"] == "TMN1"
    assert body["vnp_TransactionDate"] == "20261022093000" and body["vnp_IpAddr"] == "203.0.113.7"
    expected = "|".join(body[k] for k in ("vnp_RequestId", "vnp_Version", "vnp_Command", "vnp_TmnCode", "vnp_TxnRef",
                                          "vnp_TransactionDate", "vnp_CreateDate", "vnp_IpAddr", "vnp_OrderInfo"))
    assert body["vnp_SecureHash"] == _hmac(VN_SECRET, expected, hashlib.sha512)


def test_vnpay_query_edge_cases():
    meta = {"vnp_create_date": "20261022093000"}
    _, not_found = _vn_query("00", code="91")
    assert vnpay(not_found).query(txn_ref="X", meta=meta, client_ip=None) is None             # unknown to VNPay: nothing to settle
    assert vnpay(_vn_query("00")[1]).query(txn_ref="X", meta={}, client_ip=None) is None      # no create date kept: cannot ask
    _, bad_amount = _vn_query("00", amount="x")
    assert vnpay(bad_amount).query(txn_ref="X", meta=meta, client_ip=None) is None
    with pytest.raises(AppError) as exc:
        vnpay(lambda r: httpx.Response(500, text="boom")).query(txn_ref="X", meta=meta, client_ip=None)
    assert exc.value.status == 502 and exc.value.code == "GATEWAY_UNAVAILABLE"

    def down(request):
        raise httpx.ConnectError("no route")
    with pytest.raises(AppError) as exc:
        vnpay(down).query(txn_ref="X", meta=meta, client_ip=None)
    assert exc.value.code == "GATEWAY_UNAVAILABLE"


def test_vnpay_transaction_ids_are_unique_and_url_safe():
    ids = {vnpay().new_txn_id() for _ in range(50)}
    assert len(ids) == 50 and all(i.isalnum() and len(i) <= 34 for i in ids)


# ===================================================================================== MoMo
def _momo_create_handler(result=0, pay_url="https://test-payment.momo.vn/pay/abc", status=200):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        return httpx.Response(status, json={"resultCode": result, "payUrl": pay_url, "message": "msg"})
    return seen, handler


def test_momo_create_request_is_signed_in_the_documented_key_order():
    seen, handler = _momo_create_handler()
    link = momo(handler).create_payment(txn_ref="VHRSABC", amount=199800, order_info="Thanh toan don VHRS-1", client_ip=None,
                                        return_url="https://fe.example/payment/result",
                                        ipn_url="https://api.example/api/v1/webhooks/payments/momo/ipn", expire_minutes=15)
    path, body = seen[0]
    assert path == "/v2/gateway/api/create" and link.url == "https://test-payment.momo.vn/pay/abc"
    assert body["partnerCode"] == "MOMOP" and body["orderId"] == "VHRSABC" and body["amount"] == 199800
    assert body["requestType"] == "captureWallet" and body["ipnUrl"].endswith("/momo/ipn") and body["extraData"] == ""
    raw = (f"accessKey=AK&amount=199800&extraData=&ipnUrl={body['ipnUrl']}&orderId=VHRSABC&orderInfo=Thanh toan don VHRS-1"
           f"&partnerCode=MOMOP&redirectUrl=https://fe.example/payment/result&requestId={body['requestId']}"
           f"&requestType=captureWallet")
    assert body["signature"] == _hmac(MOMO_SECRET, raw, hashlib.sha256)
    assert link.expires_at > datetime.now(timezone.utc)


def test_momo_create_errors():
    args = dict(txn_ref="A", amount=1000, order_info="x", client_ip=None, return_url="https://r",
                ipn_url="https://i", expire_minutes=15)
    _, rejected = _momo_create_handler(result=1006)
    with pytest.raises(AppError) as exc:
        momo(rejected).create_payment(**args)
    assert exc.value.status == 502 and exc.value.code == "GATEWAY_REJECTED" and exc.value.details["resultCode"] == 1006
    _, no_url = _momo_create_handler(pay_url="")
    with pytest.raises(AppError) as exc:
        momo(no_url).create_payment(**args)
    assert exc.value.code == "GATEWAY_REJECTED"
    with pytest.raises(AppError) as exc:
        momo(lambda r: httpx.Response(500, text="<html>")).create_payment(**args)
    assert exc.value.code == "GATEWAY_UNAVAILABLE"
    with pytest.raises(AppError) as exc:
        momo(lambda r: httpx.Response(200, json=[1, 2])).create_payment(**args)
    assert exc.value.code == "GATEWAY_UNAVAILABLE"
    with pytest.raises(AppError) as exc:
        momo().create_payment(**{**args, "ipn_url": None})
    assert exc.value.status == 503 and exc.value.code == "GATEWAY_NOT_CONFIGURED"
    for amount in (0, -1):
        with pytest.raises(AppError) as exc:
            momo().create_payment(**{**args, "amount": amount})
        assert exc.value.code == "INVALID_AMOUNT"


def _momo_ipn(**over) -> dict:
    body = {"partnerCode": "MOMOP", "orderId": "VHRSABC", "requestId": "req1", "amount": 199800,
            "orderInfo": "Thanh toan don VHRS-1", "orderType": "momo_wallet", "transId": 2820001, "resultCode": 0,
            "message": "Successful.", "payType": "qr", "responseTime": 1792000000000, "extraData": "", **over}
    raw = "&".join(f"{k}={'AK' if k == 'accessKey' else ('' if body.get(k) is None else body[k])}" for k in IPN_FIELDS)
    assert IPN_FIELDS == tuple(sorted(IPN_FIELDS))                                           # alphabetical, as documented
    return {**body, "signature": _hmac(MOMO_SECRET, raw, hashlib.sha256)}


def test_momo_ipn_parsing():
    g = momo()
    ok = g.parse_ipn(_momo_ipn())
    assert (ok.txn_ref, ok.amount, ok.success, ok.final) == ("VHRSABC", 199800, True, True)
    failed = g.parse_ipn(_momo_ipn(resultCode=1006))
    assert failed.success is False and failed.final is True
    for code in (1000, 7000, 7002, 9000):
        pending = g.parse_ipn(_momo_ipn(resultCode=code))
        assert pending.final is False and pending.success is False, code


def test_momo_ipn_rejects_tampering_and_foreign_partners():
    g = momo()
    good = _momo_ipn()
    for bad in ({**good, "amount": 1}, {**good, "orderId": "OTHER"}, {**good, "resultCode": 1006}, {**good, "transId": 1}):
        with pytest.raises(gw.InvalidSignature):
            g.parse_ipn(bad)
    with pytest.raises(gw.InvalidSignature):
        g.parse_ipn({k: v for k, v in good.items() if k != "signature"})
    with pytest.raises(gw.InvalidSignature):
        g.parse_ipn({**good, "signature": ""})
    with pytest.raises(gw.InvalidSignature):
        g.parse_ipn(_momo_ipn(partnerCode="SOMEONEELSE"))        # a valid-looking message for another merchant
    with pytest.raises(gw.MalformedCallback):
        g.parse_ipn(_momo_ipn(amount="abc"))
    with pytest.raises(gw.MalformedCallback):
        g.parse_ipn(_momo_ipn(resultCode=None))


def _momo_query_handler(code, amount=199800):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"resultCode": code, "amount": amount, "orderId": "VHRSABC"})
    return seen, handler


def test_momo_query_maps_codes_and_signs_the_request():
    for code, expect in ((0, (True, True)), (1000, (False, False)), (7002, (False, False)), (1006, (False, True)),
                         (1005, (False, True))):
        seen, handler = _momo_query_handler(code)
        r = momo(handler).query(txn_ref="VHRSABC", meta={}, client_ip=None)
        assert (r.success, r.final) == expect and r.amount == 199800, code
    path, body = seen[0]
    assert path == "/v2/gateway/api/query" and body["orderId"] == "VHRSABC"
    raw = f"accessKey=AK&orderId=VHRSABC&partnerCode=MOMOP&requestId={body['requestId']}"
    assert body["signature"] == _hmac(MOMO_SECRET, raw, hashlib.sha256)
    assert momo(_momo_query_handler(42)[1]).query(txn_ref="X", meta={}, client_ip=None) is None      # unknown order
    assert momo(lambda r: httpx.Response(200, json={"message": "?"})).query(txn_ref="X", meta={}, client_ip=None) is None
    with pytest.raises(AppError) as exc:
        momo(lambda r: httpx.Response(503, text="x")).query(txn_ref="X", meta={}, client_ip=None)
    assert exc.value.code == "GATEWAY_UNAVAILABLE"


# ===================================================================================== registry
@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    for k, v in (("payment_mode", "mock"), ("vnpay_tmn_code", None), ("vnpay_hash_secret", None),
                 ("momo_partner_code", None), ("momo_access_key", None), ("momo_secret_key", None),
                 ("public_base_url", None)):
        monkeypatch.setattr(s, k, v)
    gw.use_adapters(None)
    yield s
    gw.use_adapters(None)


def test_mock_mode_has_no_real_adapter(settings):
    assert gw.real_adapter(PaymentGateway.VNPAY) is None and gw.real_adapter("MOMO") is None
    assert gw.mode_label() == "MOCK"
    assert gw.gateway_status() == [{"gateway": "VNPAY", "mode": "MOCK", "enabled": True},
                                   {"gateway": "MOMO", "mode": "MOCK", "enabled": True}]


def test_real_modes_need_credentials(settings, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "sandbox")
    with pytest.raises(AppError) as exc:
        gw.real_adapter(PaymentGateway.VNPAY)
    assert exc.value.status == 503 and exc.value.code == "GATEWAY_NOT_CONFIGURED"
    assert gw.real_adapter("MOMO", strict=False) is None                       # IPN endpoints just cannot verify anything
    assert gw.gateway_status() == [{"gateway": "VNPAY", "mode": "SANDBOX", "enabled": False},
                                   {"gateway": "MOMO", "mode": "SANDBOX", "enabled": False}]

    monkeypatch.setattr(settings, "vnpay_tmn_code", "TMN1")
    monkeypatch.setattr(settings, "vnpay_hash_secret", "s")
    v = gw.real_adapter(PaymentGateway.VNPAY)
    assert isinstance(v, VnpayGateway) and v.mode == "SANDBOX" and v.tmn_code == "TMN1"
    assert gw.real_adapter("MOMO", strict=False) is None
    assert [g["enabled"] for g in gw.gateway_status()] == [True, False]

    for k, val in (("momo_partner_code", "P"), ("momo_access_key", "A")):
        monkeypatch.setattr(settings, k, val)
    assert gw.real_adapter("MOMO", strict=False) is None                       # the secret key is still missing
    monkeypatch.setattr(settings, "momo_secret_key", "S")
    monkeypatch.setattr(settings, "payment_mode", "live")
    m = gw.real_adapter("MOMO")
    assert isinstance(m, MomoGateway) and m.mode == "LIVE" and gw.mode_label() == "LIVE"


def test_test_overrides_and_ipn_urls(settings, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "sandbox")
    stand_in = vnpay()
    gw.use_adapters({"VNPAY": stand_in})
    assert gw.real_adapter("vnpay") is stand_in and gw.real_adapter(PaymentGateway.VNPAY) is stand_in
    gw.use_adapters(None)
    monkeypatch.setattr(settings, "payment_mode", "mock")
    gw.use_adapters({"VNPAY": stand_in})
    assert gw.real_adapter("VNPAY") is None                                    # mock mode ignores real adapters entirely
    assert gw.ipn_url("MOMO") is None
    monkeypatch.setattr(settings, "public_base_url", "https://api.example.com/")
    assert gw.ipn_url("MOMO") == "https://api.example.com/api/v1/webhooks/payments/momo/ipn"
    assert gw.ipn_url("VNPAY") == "https://api.example.com/api/v1/webhooks/payments/vnpay/ipn"


def test_return_url_carries_the_order_id():
    from types import SimpleNamespace
    from app.services.gateway_checkout import return_url
    order = SimpleNamespace(id=42)
    assert return_url("https://app.example/payment/result", order) == "https://app.example/payment/result?order_id=42"
    assert return_url("https://app.example/r?lang=vi", order) == "https://app.example/r?lang=vi&order_id=42"
