"""Upgrade U8: the agent refuses a signed OT-1 package whose trajectory does not carry the declared watermark line."""
import httpx
import pytest

from app.core import production_signing as ps
from app.services.stroke_ai import physical_mark as pm
from app.services.stroke_ai import trajectory as tj
from app.services.stroke_ai.trajectory import Page, Stroke
from vhrs_agent.bridge import BackendBridge, BridgeError

KEY = ps.generate_private_key()
RING = {"k1": ps.public_key_of(KEY)}


def _raw(with_mark: bool, code: str = "ABCD-EFGH"):
    page = Page("A5", [Stroke([(20, 20), (60, 40)])])
    info = pm.apply([page], code) if with_mark else None
    return tj.dumps(tj.to_dict([page], {"name": "test"})), info


def _snapshot(raw: bytes, order_type: str, watermark, schema: str = ps.SCHEMA):
    text = ps.canonical({"schema": schema, "order": {"id": 5, "type": order_type},
                         "sketch": {"id": 6, "trajectory_sha256": tj.content_hash(raw)}, "materials": {},
                         "watermark": watermark})
    return {"snapshot_id": 1, "package_id": "x", "schema": schema, "payload": text, "payload_sha256": ps.sha256_hex(text),
            "signature": ps.sign(text, KEY), "key_id": "k1"}


def _fetch(raw: bytes, snapshot):
    def handler(request):
        return httpx.Response(200, json={"trajectory_url": "https://storage.example/t.json",
                                         "package_hash": tj.content_hash(raw), "snapshot": snapshot})
    bridge = BackendBridge("https://be.example", "tok", transport=httpx.MockTransport(handler),
                           downloader=lambda url: raw, public_keys=RING)
    return bridge.fetch_job(9)


def test_an_ot1_package_with_its_line_loads():
    raw, info = _raw(True)
    job = _fetch(raw, _snapshot(raw, "OT1_COPY_RESTORE", {"required": True, **info}))
    assert sum(s.kind == pm.KIND for s in job["pages"][0].strokes) == info["pages"][0]["strokes"]


@pytest.mark.parametrize("case", ["missing", "other_code"])
def test_an_ot1_package_without_its_line_is_refused(case):
    raw, info = _raw(case == "other_code", code="ZZZZ-ZZZZ")
    declared = None if case == "missing" else {"required": True, **info, "code": "ABCD-EFGH"}
    with pytest.raises(BridgeError) as e:
        _fetch(raw, _snapshot(raw, "OT1_COPY_RESTORE", declared))
    assert e.value.code == "PRODUCTION_PACKAGE_INVALID"
    assert ("WATERMARK_REQUIRED" if case == "missing" else "WATERMARK_MISMATCH") in str(e.value)


def test_legacy_and_ot3_packages_still_load():
    raw, _ = _raw(False)
    _fetch(raw, _snapshot(raw, "OT1_COPY_RESTORE", None, schema=ps.SCHEMA_V1))     # issued before U8
    _fetch(raw, _snapshot(raw, "OT3_TEMPLATE", None))                               # OT-3 without the option
