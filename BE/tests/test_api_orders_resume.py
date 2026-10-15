"""Phase 1: resuming drafts and the remaining customer cases (type change, cancel, saved styles)."""
import pytest

from app.api.v1.orders import optional_storage
from app.integrations.storage import InMemoryStorage
from app.main import app
from tests.conftest import auth
from tests.test_api_orders import API, _materials, _new, _png, _sql, _upload, catalog  # noqa: F401


@pytest.fixture
def storage():
    mem = InMemoryStorage()
    app.dependency_overrides[optional_storage] = lambda: mem
    yield mem
    app.dependency_overrides.pop(optional_storage, None)


@pytest.fixture
def cust(client):
    return auth(client, "CUSTOMER")


def test_resume_draft_in_new_session_keeps_everything(client, cust, catalog):
    oid = _new(client, cust, "OT3_TEMPLATE", quantity=3)["id"]
    _materials(client, cust, oid, catalog)
    client.put(f"{API}/orders/{oid}/inputs/text", headers=cust,
               json={"text_content": "Lời chúc", "template_id": catalog["tpl"]})
    client.patch(f"{API}/orders/{oid}", headers=cust, json={"customer_note": "viết đẹp nhé"})
    me = client.get(f"{API}/me", headers=cust).json()          # same customer, another device
    relog = client.post(f"{API}/auth/login", json={"email": me["email"], "password": "Passw0rd!x"}).json()
    h2 = {"Authorization": f"Bearer {relog['access_token']}"}
    drafts = client.get(f"{API}/orders", params={"status": "DRAFT"}, headers=h2).json()
    assert [d["id"] for d in drafts["items"]] == [oid]
    d = client.get(f"{API}/orders/{oid}", headers=h2).json()
    assert d["quantity"] == 3 and d["customer_note"] == "viết đẹp nhé"
    assert d["pen_type_id"] == catalog["pen"] and d["inputs"][0]["text_content"] == "Lời chúc"
    r = client.put(f"{API}/orders/{oid}/inputs/text", headers=h2,
                   json={"text_content": "Lời chúc mới", "template_id": catalog["tpl"]})
    assert r.status_code == 200
    d = client.get(f"{API}/orders/{oid}", headers=h2).json()
    assert len(d["inputs"]) == 1 and d["inputs"][0]["text_content"] == "Lời chúc mới"
    assert client.delete(f"{API}/orders/{oid}/inputs/{d['inputs'][0]['id']}", headers=h2).status_code == 204
    assert client.get(f"{API}/orders/{oid}", headers=h2).json()["inputs"] == []


def test_resume_draft_with_uploaded_image_gives_viewing_link(client, cust, storage):
    oid = _new(client, cust, "OT1_COPY_RESTORE")["id"]
    r, iid = _upload(client, cust, oid, storage, _png())
    assert r.status_code == 200
    f = client.get(f"{API}/orders/{oid}/inputs/{iid}/file", headers=cust)
    assert f.status_code == 200 and f.json()["url"] and f.json()["expires_in"] == 600
    other = auth(client, "CUSTOMER")
    assert client.get(f"{API}/orders/{oid}/inputs/{iid}/file", headers=other).status_code == 404
    assert storage.objects
    assert client.delete(f"{API}/orders/{oid}", headers=cust).status_code == 204
    assert not storage.objects            # deleting the draft removes the stored file as well


def test_change_order_type_while_draft(client, cust, catalog):
    oid = _new(client, cust, "OT3_TEMPLATE")["id"]
    client.put(f"{API}/orders/{oid}/inputs/text", headers=cust,
               json={"text_content": "abc", "template_id": catalog["tpl"]})
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json={"order_type": "OT2_LEARNED_STYLE"})
    assert r.status_code == 200 and r.json()["order_type"] == "OT2_LEARNED_STYLE"
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json={"order_type": "OT1_COPY_RESTORE"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ORDER_TYPE_HAS_INPUTS"
    iid = client.get(f"{API}/orders/{oid}", headers=cust).json()["inputs"][0]["id"]
    client.delete(f"{API}/orders/{oid}/inputs/{iid}", headers=cust)
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json={"order_type": "OT1_COPY_RESTORE"})
    assert r.status_code == 200 and r.json()["order_type"] == "OT1_COPY_RESTORE"


def _submitted(client, h, catalog) -> int:
    oid = _new(client, h)["id"]
    client.patch(f"{API}/orders/{oid}", headers=h, json={"workshop_suggest_materials": True})
    client.put(f"{API}/orders/{oid}/inputs/text", headers=h,
               json={"text_content": "abc", "template_id": catalog["tpl"]})
    assert client.post(f"{API}/orders/{oid}/submit", headers=h, json={"terms_accepted": True}).status_code == 200
    return oid


def test_order_type_locked_after_submit(client, cust, catalog):
    oid = _submitted(client, cust, catalog)
    r = client.patch(f"{API}/orders/{oid}", headers=cust, json={"order_type": "OT2_LEARNED_STYLE"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ORDER_NOT_EDITABLE"


def test_cancel_submitted_order(client, cust, catalog):
    oid = _submitted(client, cust, catalog)
    other = auth(client, "CUSTOMER")
    assert client.post(f"{API}/orders/{oid}/cancel", headers=other, json={"reason": "x"}).status_code == 404
    r = client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "Đổi ý"})
    assert r.status_code == 200 and r.json()["order_status"] == "CANCELLED"
    assert client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "again"}).status_code == 409
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={"quantity": 2}).status_code == 409
    assert _sql("select count(*) from status_histories where order_id=:o and to_status='CANCELLED' "
                "and reason='Đổi ý'", o=oid) == 1


def test_cancel_rules(client, cust, catalog):
    draft = _new(client, cust)["id"]
    assert client.post(f"{API}/orders/{draft}/cancel", headers=cust,
                       json={"reason": "x"}).json()["error"]["code"] == "ORDER_IS_DRAFT"
    assert client.post(f"{API}/orders/{draft}/cancel", headers=cust, json={}).status_code == 422
    oid = _submitted(client, cust, catalog)
    _sql("update orders set order_status='ACCEPTED', "
         "assigned_staff_id=(select id from accounts where role_id=2 limit 1) where id=:o returning 1", o=oid)
    r = client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ORDER_CANCEL_UNSUPPORTED"


def _style(owner_id: int, name: str, status: str) -> int:
    return _sql("insert into handwriting_styles (owner_id, name, status, right_to_use_confirmed) "
                "values (:o, :n, :s, true) returning id", o=owner_id, n=name, s=status)


def test_my_styles_lists_only_own_approved(client, cust):
    me = client.get(f"{API}/me", headers=cust).json()["id"]
    other = client.get(f"{API}/me", headers=auth(client, "CUSTOMER")).json()["id"]
    ids = [_style(me, "Mine", "APPROVED"), _style(me, "Pending", "PENDING_REVIEW"), _style(other, "Theirs", "APPROVED")]
    try:
        assert [s["name"] for s in client.get(f"{API}/catalog/my-styles", headers=cust).json()] == ["Mine"]
    finally:
        for i in ids:
            _sql("delete from handwriting_styles where id=:i returning 1", i=i)


def test_ot2_can_use_saved_style_instead_of_sample(client, cust, catalog):
    me = client.get(f"{API}/me", headers=cust).json()["id"]
    style_id = _style(me, "Ba", "APPROVED")
    other = auth(client, "CUSTOMER")
    try:
        oid = _new(client, cust, "OT2_LEARNED_STYLE")["id"]
        _materials(client, cust, oid, catalog)
        r = client.put(f"{API}/orders/{oid}/inputs/text", headers=cust,
                       json={"text_content": "Con nhớ ba", "handwriting_style_id": style_id})
        assert r.status_code == 200, r.text
        r = client.post(f"{API}/orders/{oid}/submit", headers=cust,
                        json={"terms_accepted": True, "confirm_right_to_use": True})
        assert r.status_code == 200, r.text
        oid2 = _new(client, other, "OT2_LEARNED_STYLE")["id"]      # another customer cannot use it
        r = client.put(f"{API}/orders/{oid2}/inputs/text", headers=other,
                       json={"text_content": "x", "handwriting_style_id": style_id})
        assert r.json()["error"]["code"] == "INVALID_STYLE"
    finally:
        _sql("delete from orders where customer_id=:c returning 1", c=me)   # releases the style FK
        _sql("delete from handwriting_styles where id=:i returning 1", i=style_id)


def test_validation_errors_use_standard_envelope(client, cust):
    r = client.post(f"{API}/orders", headers=cust, json={"order_type": "NOPE", "quantity": 0})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    oid = _new(client, cust)["id"]
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={"quantity": 0}).status_code == 422
    assert client.get(f"{API}/orders/999999999", headers=cust).status_code == 404
    assert client.get(f"{API}/orders", params={"page_size": 1000}, headers=cust).status_code == 422
