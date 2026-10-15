"""Real Supabase Storage round trip through the API. Skipped when storage is not configured."""
import httpx
import pytest

from app.core.config import get_settings
from tests.conftest import auth
from tests.test_api_orders import API, _new, _png

pytestmark = pytest.mark.skipif(not get_settings().supabase_service_key, reason="storage not configured")


def test_signed_upload_confirm_view_and_delete_roundtrip(client):
    h = auth(client, "CUSTOMER")
    oid = _new(client, h, "OT1_COPY_RESTORE")["id"]
    data = _png()
    up = client.post(f"{API}/orders/{oid}/inputs/upload-url", headers=h,
                     json={"kind": "ORIGINAL_IMAGE", "mime_type": "image/png", "size_bytes": len(data)})
    assert up.status_code == 201, up.text
    body = up.json()
    put = httpx.put(body["upload_url"], content=data, headers={"Content-Type": "image/png"}, timeout=30)
    assert put.status_code == 200, put.text
    ok = client.post(f"{API}/orders/{oid}/inputs/{body['input_id']}/confirm", headers=h)
    assert ok.status_code == 200 and ok.json()["quality_result"]["chars_estimate"] > 0
    link = client.get(f"{API}/orders/{oid}/inputs/{body['input_id']}/file", headers=h).json()["url"]
    assert httpx.get(link, timeout=30).content == data
    assert client.delete(f"{API}/orders/{oid}", headers=h).status_code == 204   # removes the object too
