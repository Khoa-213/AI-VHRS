"""Upgrade U1: signed, immutable production snapshot (docs/UPGRADE_AI_ROBOT_PLAN.md 3.4).

The snapshot is issued when the gateway confirms the deposit and, mandatorily, when the Manager schedules the job. The
package the technician / Robot Agent downloads carries it; it is verified offline with the PUBLIC key only. Every way of
tampering must end in 409 PRODUCTION_PACKAGE_INVALID with the evidence kept (job event, audit row, incident).
"""
import hashlib
import json

import pytest
from sqlalchemy.exc import DBAPIError

from app.core import production_signing as ps
from app.core.config import get_settings
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _paid
from tests.test_api_scheduling import _at, _sched, mgr, robot, tech  # noqa: F401
from tests.test_api_technician import CAL, _event_types, _job, _post, _ready
from tests.test_api_workshop import _err, cust, policy, staff, store, wcat  # noqa: F401

T = f"{API}/technician"


def _snap(jid):
    return _sql("select snapshot_id from production_jobs where id=:j", j=jid)


def _package(client, tech, jid):
    r = client.get(f"{T}/jobs/{jid}/package", headers=tech[0])
    return r


# ---- the signing module itself ----------------------------------------------------------------------
def test_canonical_text_is_stable_and_refuses_floats():
    a = ps.canonical({"b": 1, "a": {"y": "x", "x": [1, 2]}, "c": "Chữ"})
    assert a == ps.canonical({"c": "Chữ", "a": {"x": [1, 2], "y": "x"}, "b": 1}) == '{"a":{"x":[1,2],"y":"x"},"b":1,"c":"Chữ"}'
    from decimal import Decimal
    assert ps.canonical({"v": Decimal("30.0"), "w": Decimal("0.50")}) == '{"v":"30","w":"0.50"}'
    with pytest.raises(TypeError):
        ps.canonical({"v": 0.5})


def test_signature_detects_every_change_and_rotation_keeps_old_keys():
    old, new = ps.generate_private_key(), ps.generate_private_key()
    text = ps.canonical({"schema": ps.SCHEMA, "order": {"id": 1}, "sketch": {"id": 2, "trajectory_sha256": "a" * 64}})
    sig = ps.sign(text, old)
    ring = {"k1": ps.public_key_of(old), "k2": ps.public_key_of(new)}
    block = {"payload": text, "payload_sha256": ps.sha256_hex(text), "signature": sig, "key_id": "k1"}
    assert ps.verify_package(block, ring, trajectory_sha256="a" * 64, job_order_id=1, job_sketch_id=2)["order"] == {"id": 1}

    def reason(**change):
        with pytest.raises(ps.SignatureError) as e:
            ps.verify_package({**block, **change}, ring, trajectory_sha256="a" * 64, job_order_id=1, job_sketch_id=2)
        return e.value.code

    assert reason(payload=text.replace('"id":1', '"id":9')) == "SIGNATURE_INVALID"          # one byte of the payload
    assert reason(key_id="k2") == "SIGNATURE_INVALID"                                        # signed by another key
    assert reason(key_id="gone") == "SIGNING_KEY_UNKNOWN"                                    # key removed from the ring
    assert reason(payload_sha256="0" * 64) == "SNAPSHOT_HASH_MISMATCH"
    with pytest.raises(ps.SignatureError) as e:
        ps.verify_package(block, ring, trajectory_sha256="b" * 64)
    assert e.value.code == "TRAJECTORY_MISMATCH"
    with pytest.raises(ps.SignatureError) as e:
        ps.verify_package(block, ring, job_order_id=7)
    assert e.value.code == "SNAPSHOT_WRONG_JOB"


# ---- issue: deposit and scheduling ------------------------------------------------------------------
def test_the_deposit_locks_a_signed_snapshot_that_scheduling_reuses(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, q, p = _paid(client, cust, staff[0], wcat)
    rows = _sql("select count(*) from production_snapshots where order_id=:o and revoked_at is null", o=oid)
    assert rows == 1                                                              # issued by the deposit webhook
    first = _sql("select id from production_snapshots where order_id=:o", o=oid)
    r = _sched(client, mgr, oid, robot, tech[1], _at(1, 9))
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    assert _snap(jid) == first                                                    # scheduling reused it

    pkg = _package(client, tech, jid).json()
    snap = pkg["snapshot"]
    assert snap["snapshot_id"] == first and snap["signature_algorithm"] == "Ed25519" and snap["schema"] == ps.SCHEMA
    uri = _sql("select package_uri from production_jobs where id=:j", j=jid)
    payload = ps.verify_package(snap, get_settings().production_key_ring,
                                trajectory_sha256=hashlib.sha256(store.objects[uri]).hexdigest(),
                                job_order_id=oid, job_sketch_id=_sql("select sketch_id from production_jobs where id=:j", j=jid))
    assert payload["materials"]["pen"]["v_max_mm_s"] == "30" and payload["materials"]["pen"]["f_hard_n"] == "3"
    assert payload["materials"]["paper"]["size"] == "A5" and payload["materials"]["ink"]["hex_code"] == "#000000"
    assert payload["quotation"]["id"] == q["id"] and payload["deposit"]["payment_id"] == p["id"]
    assert payload["deposit"]["gateway"] == _sql("select gateway::text from payments where id=:p", p=p["id"])
    assert payload["watermark"] is None
    assert pkg["material_drift"] == []
    assert _sql("select count(*) from audit_logs where action='PRODUCTION_SNAPSHOT_ISSUE' and entity_id=:s", s=first) == 1


def test_a_locked_job_keeps_the_pen_values_it_was_paid_with(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    pen_id = _sql("select pen_type_id from orders where id=:o", o=oid)
    before = _sql("select v_max_mm_s from pen_types where id=:p", p=pen_id)
    try:
        _sql("update pen_types set v_max_mm_s = 55 where id=:p returning 1", p=pen_id)      # a Manager edits the catalog
        pkg = _package(client, tech, jid).json()
        assert pkg["pen"]["v_max_mm_s"] == 30.0                                            # the locked value, not 55
        assert pkg["material_drift"] == ["pen.v_max_mm_s: đã khoá '30', danh mục hiện tại '55'"]
    finally:
        _sql("update pen_types set v_max_mm_s = :v where id=:p returning 1", v=before, p=pen_id)


def test_scheduling_refuses_without_a_signing_key_but_the_payment_still_succeeds(client, cust, staff, mgr, wcat, robot, tech,
                                                                                 monkeypatch):
    monkeypatch.setattr(get_settings(), "production_signing_key", None)
    oid, _, _ = _paid(client, cust, staff[0], wcat)                                  # the webhook never fails because of U1
    assert _sql("select count(*) from production_snapshots where order_id=:o", o=oid) == 0
    r = _sched(client, mgr, oid, robot, tech[1], _at(1, 9))
    assert r.status_code == 503 and _err(r) == "PRODUCTION_SIGNING_NOT_CONFIGURED"
    assert _sql("select count(*) from production_jobs where order_id=:o", o=oid) == 0
    monkeypatch.undo()
    r = _sched(client, mgr, oid, robot, tech[1], _at(1, 9))                          # key back: scheduling issues it now
    assert r.status_code == 201, r.text
    assert _snap(r.json()["id"]) is not None


# ---- tampering ---------------------------------------------------------------------------------------
def test_a_snapshot_cannot_be_edited_in_the_database(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    sid = _snap(jid)
    for change in ("payload = '{}'", "signature = 'x'", "key_id = 'k9'", "payload_sha256 = repeat('0', 64)",
                   "quotation_id = null", "created_at = now() - interval '1 day'"):
        with pytest.raises(DBAPIError, match="immutable"):
            _sql(f"update production_snapshots set {change} where id=:s returning 1", s=sid)
    _sql("update production_snapshots set revoked_at=now(), revoked_reason='test' where id=:s returning 1", s=sid)
    with pytest.raises(DBAPIError, match="already revoked"):
        _sql("update production_snapshots set revoked_at=null, revoked_reason=null where id=:s returning 1", s=sid)


def _forge(oid, jid, key: str, key_id: str = "pytest", **payload_change):
    """Revoke the real snapshot and plant a look-alike signed with `key`, as an attacker with database access would."""
    sid = _snap(jid)
    real = json.loads(_sql("select payload from production_snapshots where id=:s", s=sid))
    real.update(payload_change)
    text_ = ps.canonical(real)
    _sql("update production_snapshots set revoked_at=now(), revoked_reason='pytest forge' where id=:s returning 1", s=sid)
    new = _sql("""insert into production_snapshots (package_id, order_id, sketch_id, schema_version, payload, payload_sha256,
                  signature, key_id) select gen_random_uuid(), order_id, sketch_id, schema_version, :p, :h, :g, :k
                  from production_snapshots where id=:s returning id""",
               p=text_, h=ps.sha256_hex(text_), g=ps.sign(text_, key), k=key_id, s=sid)
    _sql("update production_jobs set snapshot_id=:n where id=:j returning 1", n=new, j=jid)


def _refused(client, tech, jid, reason):
    r = _package(client, tech, jid)
    assert r.status_code == 409 and _err(r) == "PRODUCTION_PACKAGE_INVALID", r.text
    assert r.json()["error"]["details"]["reason"] == reason
    return r


def test_a_package_signed_with_another_key_is_refused_and_recorded(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    _forge(oid, jid, ps.generate_private_key(), quotation={"id": 1, "final_total": "1"})
    _refused(client, tech, jid, "SIGNATURE_INVALID")
    assert _event_types(client, tech[0], jid) == ["HASH_MISMATCH"]                    # kept although the request failed
    assert _sql("select count(*) from audit_logs where action='JOB_SIGNATURE_INVALID' and entity_id=:j", j=jid) == 1
    assert _sql("select count(*) from incidents where job_id=:j and description like '%SIGNATURE_INVALID%'", j=jid) == 1
    assert _sql("select downloaded_at is null from production_jobs where id=:j", j=jid)


def test_a_revoked_or_foreign_snapshot_is_refused(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    other_oid, _, _ = _paid(client, cust, staff[0], wcat)                    # another order, another slot of the robot
    r = _sched(client, mgr, other_oid, robot, tech[1], _at(2, 9))
    assert r.status_code == 201, r.text
    other_jid = r.json()["id"]
    own = _snap(jid)
    _sql("update production_jobs set snapshot_id=:s where id=:j returning 1", s=_snap(other_jid), j=jid)   # replay
    _refused(client, tech, jid, "SNAPSHOT_WRONG_JOB")
    _sql("update production_jobs set snapshot_id=:s where id=:j returning 1", s=own, j=jid)
    assert _package(client, tech, jid).status_code == 200
    _sql("update production_snapshots set revoked_at=now(), revoked_reason='pytest' where id=:s returning 1", s=own)
    _refused(client, tech, jid, "SNAPSHOT_REVOKED")


def test_writing_is_refused_when_the_snapshot_changed_after_the_download(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _ready(client, cust, staff, mgr, wcat, robot, tech)
    _sql("update production_snapshots set revoked_at=now(), revoked_reason='pytest' where id=:s returning 1", s=_snap(jid))
    r = _post(client, tech, jid, "start")
    assert r.status_code == 409 and _err(r) == "PRODUCTION_PACKAGE_INVALID"
    assert _sql("select status::text from production_jobs where id=:j", j=jid) == "PREPARING"


def test_a_job_from_before_the_upgrade_keeps_the_hash_check_only(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    _sql("update production_jobs set snapshot_id=null where id=:j returning 1", j=jid)
    pkg = _package(client, tech, jid).json()
    assert pkg["snapshot"] is None and pkg["material_drift"] == [] and pkg["pen"]["v_max_mm_s"] == 30.0
    _post(client, tech, jid, "prepare", status=200)
    _post(client, tech, jid, "calibration", CAL, status=201)


def test_cancelling_after_the_deposit_revokes_the_snapshot(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    sid = _snap(jid)
    r = client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "Khách đổi ý"})
    assert r.status_code == 200, r.text
    assert _sql("select revoked_reason from production_snapshots where id=:s", s=sid).startswith("Đơn bị huỷ")
    assert _sql("select count(*) from audit_logs where action='PRODUCTION_SNAPSHOT_REVOKE' and entity_id=:s", s=sid) == 1
