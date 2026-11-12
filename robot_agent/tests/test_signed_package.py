"""Upgrade U1: the agent verifies the signed production snapshot with its OWN public keys before it loads a job."""
import json

import httpx
import pytest

from app.core import production_signing as ps
from app.services.stroke_ai import trajectory as tj
from app.services.stroke_ai.trajectory import Page, Stroke
from vhrs_agent.bridge import BackendBridge, BridgeError

RAW = tj.dumps(tj.to_dict([Page("A4", [Stroke([(20, 20), (40, 20)])])], {"name": "test"}))
TRAJ = tj.content_hash(RAW)
KEY = ps.generate_private_key()
RING = {"k1": ps.public_key_of(KEY)}
PEN = {"name": "Gel", "category": "GEL", "stroke_width_mm": 0.5, "f_target_n": 0.6, "f_min_n": 0.3, "f_max_n": 1.0,
       "f_hard_n": 3.0, "v_max_mm_s": 30.0}


def _snapshot(key=KEY, key_id="k1", traj=TRAJ, v_max="30"):
    text = ps.canonical({"schema": ps.SCHEMA, "order": {"id": 5}, "sketch": {"id": 6, "trajectory_sha256": traj},
                         "materials": {"pen": {"f_target_n": "0.60", "f_min_n": "0.30", "f_max_n": "1.00", "f_hard_n": "3",
                                               "v_max_mm_s": v_max}}})
    return {"snapshot_id": 1, "package_id": "x", "schema": ps.SCHEMA, "payload": text, "payload_sha256": ps.sha256_hex(text),
            "signature": ps.sign(text, key), "key_id": key_id}


def _bridge(snapshot, **kw):
    def handler(request):
        return httpx.Response(200, json={"trajectory_url": "https://storage.example/t.json", "package_hash": TRAJ,
                                         "pen": PEN, "snapshot": snapshot})
    return BackendBridge("https://be.example", "tok", transport=httpx.MockTransport(handler),
                         downloader=lambda url: RAW, **kw)


def _code(snapshot, **kw):
    with pytest.raises(BridgeError) as e:
        _bridge(snapshot, **kw).fetch_job(9)
    return e.value.code


def test_a_valid_signed_package_loads():
    job = _bridge(_snapshot(), public_keys=RING).fetch_job(9)
    assert job["signed"]["sketch"]["trajectory_sha256"] == TRAJ and job["hash"] == TRAJ


def test_tampered_or_unverifiable_packages_never_load():
    assert _code(_snapshot(key=ps.generate_private_key()), public_keys=RING) == "PRODUCTION_PACKAGE_INVALID"   # forged
    assert _code(_snapshot(traj="0" * 64), public_keys=RING) == "PRODUCTION_PACKAGE_INVALID"   # signed for another file
    assert _code(_snapshot(v_max="55"), public_keys=RING) == "PRODUCTION_PACKAGE_INVALID"      # pen served != pen signed
    assert _code(_snapshot(key_id="old"), public_keys=RING) == "PRODUCTION_PACKAGE_INVALID"    # key not in this station's ring
    assert _code(_snapshot()) == "PRODUCTION_KEY_MISSING"                                       # station has no public key


def test_legacy_packages_load_unless_the_station_requires_signatures():
    assert _bridge(None, public_keys=RING).fetch_job(9)["signed"] is None
    assert _code(None, public_keys=RING, require_signed=True) == "PACKAGE_NOT_SIGNED"


def test_keys_can_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("VHRS_PRODUCTION_PUBLIC_KEYS", json.dumps(RING))
    assert _bridge(_snapshot()).fetch_job(9)["signed"]["order"] == {"id": 5}
