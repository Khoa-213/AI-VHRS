"""Upgrade U6 (docs/UPGRADE_AI_ROBOT_PLAN.md VII): extended material specs with their source, measured paper + pen + ink
profiles, and the preview tier (VISUAL / CALIBRATED / PRODUCTION_READY) that tells the customer how close the image is
to the real ink.
"""
import json

import pytest

from app.domain import material_specs
from app.services.stroke_ai import render_image
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _paid, _quoted
from tests.test_api_workshop import W, _err, cust, manager, policy, staff, store, wcat  # noqa: F401

M = f"{API}/manager"


@pytest.fixture(autouse=True)
def _no_profiles(wcat):
    """`wcat` is shared by the module: every test starts with no profile on its materials."""
    pens = (wcat["gel"], wcat["fountain"])
    _sql("update sketches set render_profile_id = null where render_profile_id in "
         "(select id from material_profiles where pen_type_id in (:a, :b)) returning 1", a=pens[0], b=pens[1])
    _sql("delete from material_profiles where pen_type_id in (:a, :b) returning 1", a=pens[0], b=pens[1])


def _profile(client, manager, wcat,pen="gel", paper="paper", **values):
    body = {"paper_type_id": wcat[paper], "pen_type_id": wcat[pen], "ink_color_id": wcat[pen + "_ink"], **values}
    return client.post(f"{M}/material-profiles", headers=manager[0], json=body)


# ---- specs ---------------------------------------------------------------------------------------------
def test_specs_need_a_known_key_a_valid_value_and_a_source():
    ok = material_specs.validate("pen", {"tip_mm": {"value": 0.5, "source": "SUPPLIER"},
                                         "needs_priming": {"value": True, "source": "ASSUMED", "note": "chưa thử"}})
    assert ok["tip_mm"] == {"value": 0.5, "source": "SUPPLIER", "unit": "mm"}
    assert ok["needs_priming"]["note"] == "chưa thử"
    for bad in ({"tip_mm": {"value": 0.5}},                                   # no source
                {"tip": {"value": 0.5, "source": "SUPPLIER"}},                # unknown key
                {"tip_mm": {"value": 99, "source": "SUPPLIER"}},              # out of range
                {"tip_mm": {"value": True, "source": "SUPPLIER"}},            # bool is not a number
                {"tip_mm": {"value": 0.5, "source": "GUESS"}},
                {"tip_mm": {"value": 0.5, "source": "SUPPLIER", "unit": "cm"}}):
        with pytest.raises(material_specs.SpecError):
            material_specs.validate("pen", bad)
    assert material_specs.validate("paper", {"tone_hex": {"value": "#f5f0e6", "source": "MEASURED"}})["tone_hex"]["value"] == "#F5F0E6"


def test_manager_writes_specs_and_every_change_is_audited(client, manager, wcat):
    fields = client.get(f"{M}/material-specs/fields", headers=manager[0]).json()
    assert fields["sources"] == ["SUPPLIER", "MEASURED", "ASSUMED"] and {f["key"] for f in fields["fields"]["ink"]} >= {"drying_s"}
    body = {"specs": {"thickness_mm": {"value": 0.12, "source": "MEASURED", "note": "thước kẹp"},
                      "absorbency": {"value": "MEDIUM", "source": "SUPPLIER"}}}
    r = client.put(f"{M}/papers/{wcat['paper']}/specs", headers=manager[0], json=body)
    assert r.status_code == 200, r.text
    assert r.json()["specs"]["thickness_mm"] == {"value": 0.12, "source": "MEASURED", "unit": "mm", "note": "thước kẹp"}
    assert _sql("select count(*) from audit_logs where action='CATALOG_PAPER_SPECS' and entity_id=:i", i=wcat["paper"]) == 1
    r = client.put(f"{M}/pens/{wcat['gel']}/specs", headers=manager[0], json={"specs": {"tip_mm": {"value": 0.5}}})
    assert r.status_code == 422 and _err(r) == "INVALID_SPECS" and r.json()["error"]["details"]["key"] == "tip_mm"
    r = client.put(f"{M}/inks/{wcat['gel_ink']}/specs", headers=manager[0],
                   json={"specs": {"waterproof": {"value": False, "source": "SUPPLIER"}}})
    assert r.status_code == 200 and r.json()["specs"]["waterproof"]["value"] is False
    assert any(p["id"] == wcat["paper"] and p["specs"]["absorbency"]["value"] == "MEDIUM"
               for p in client.get(f"{M}/papers", headers=manager[0]).json())


def test_specs_are_manager_only(client, staff, wcat):
    r = client.put(f"{M}/papers/{wcat['paper']}/specs", headers=staff[0], json={"specs": {}})
    assert r.status_code == 403


# ---- profiles ------------------------------------------------------------------------------------------
def test_a_profile_needs_a_consistent_compatible_combination(client, manager, wcat):
    bad_ink = {"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["fountain_ink"]}
    r = client.post(f"{M}/material-profiles", headers=manager[0], json=bad_ink)
    assert r.status_code == 422 and _err(r) == "INK_NOT_FOR_PEN"
    r = _profile(client, manager, wcat, pen="fountain", paper="gloss", line_width_mm="0.4")
    assert r.status_code == 422 and _err(r) == "PEN_INCOMPATIBLE"
    r = _profile(client, manager, wcat)
    assert r.status_code == 201 and r.json()["status"] == "UNCALIBRATED", r.text
    assert _err(_profile(client, manager, wcat)) == "PROFILE_EXISTS"
    r = client.post(f"{M}/material-profiles/{r.json()['id']}/verify", headers=manager[0], json={})
    assert r.status_code == 409 and _err(r) == "PROFILE_NOT_MEASURED"


def test_new_numbers_are_a_new_measurement_and_void_the_verification(client, manager, wcat):
    p = _profile(client, manager, wcat, line_width_mm="0.62", darkness="0.85", method="Kẻ 10 nét 50 mm, đo kính lúp").json()
    assert p["status"] == "MEASURED" and p["measured_by"] == manager[1] and p["measured_at"]
    v = client.post(f"{M}/material-profiles/{p['id']}/verify", headers=manager[0], json={"note": "đã soát"}).json()
    assert v["status"] == "VERIFIED" and v["verified_at"]
    r = client.patch(f"{M}/material-profiles/{p['id']}", headers=manager[0], json={"note": "chỉ sửa ghi chú"})
    assert r.json()["status"] == "VERIFIED"                                     # text only: still verified
    r = client.patch(f"{M}/material-profiles/{p['id']}", headers=manager[0], json={"line_width_mm": "0.7"})
    assert r.json()["status"] == "MEASURED" and r.json()["verified_at"] is None
    assert _sql("select count(*) from audit_logs where entity_type='material_profile' and entity_id=:i", i=p["id"]) == 4
    listed = client.get(f"{M}/material-profiles", headers=manager[0], params={"pen_id": wcat["gel"]}).json()
    assert [x["id"] for x in listed] == [p["id"]]


# ---- preview tier --------------------------------------------------------------------------------------
def test_without_a_profile_the_image_is_visual_and_the_package_says_so(client, cust, staff, wcat, store):
    oid, q, _ = _paid(client, cust, staff[0], wcat)
    sketches = client.get(f"{W}/orders/{oid}/sketches", headers=staff[0]).json()
    assert sketches[-1]["preview_tier"] == "VISUAL" and sketches[-1]["render_profile_id"] is None
    payload = json.loads(_sql("select payload from production_snapshots where order_id=:o and revoked_at is null", o=oid))
    assert payload["materials"]["profile"] is None


def test_a_measured_profile_draws_the_image_and_a_verified_locked_one_is_production_ready(
        client, cust, staff, manager, wcat, store, monkeypatch):
    widths = []
    real = render_image.render_jpeg
    monkeypatch.setattr(render_image, "render_jpeg", lambda page, **kw: widths.append(kw["stroke_width_mm"]) or real(page, **kw))
    p = _profile(client, manager, wcat, line_width_mm="0.8").json()
    oid, q = _quoted(client, cust, staff[0], wcat)
    assert widths and set(widths) == {0.8}                                      # the measured width, not the pen's 0.5
    view = client.get(f"{API}/orders/{oid}/quotation", headers=cust).json()["sketch"]
    assert view["preview_tier"] == "CALIBRATED" and "hiệu chuẩn" in view["preview_note"]
    assert _sql("select render_profile_id from sketches where id=:s", s=q["sketch_id"]) == p["id"]

    client.post(f"{M}/material-profiles/{p['id']}/verify", headers=manager[0], json={})
    client.patch(f"{M}/material-profiles/{p['id']}", headers=manager[0], json={"note": "chỉ sửa ghi chú"})
    assert client.get(f"{API}/orders/{oid}/quotation", headers=cust).json()["sketch"]["preview_tier"] == "CALIBRATED"
    client.patch(f"{M}/material-profiles/{p['id']}", headers=manager[0], json={"line_width_mm": "0.9"})   # re-measured
    assert client.get(f"{API}/orders/{oid}/quotation", headers=cust).json()["sketch"]["preview_tier"] == "VISUAL"


def test_production_ready_needs_a_verified_profile_and_the_locked_package(client, cust, staff, manager, wcat, store):
    p = _profile(client, manager, wcat, line_width_mm="0.55", darkness="0.9", v_max_mm_s="25").json()
    client.post(f"{M}/material-profiles/{p['id']}/verify", headers=manager[0], json={})
    oid, q = _quoted(client, cust, staff[0], wcat)
    assert client.get(f"{API}/orders/{oid}/quotation", headers=cust).json()["sketch"]["preview_tier"] == "CALIBRATED"
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={})
    assert r.status_code == 200, r.text
    pay = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "VNPAY"}).json()
    r = client.post(f"{API}/payments/{pay['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert r.status_code == 200, r.text
    tiers = {s["id"]: s["preview_tier"] for s in client.get(f"{W}/orders/{oid}/sketches", headers=staff[0]).json()}
    assert tiers[q["sketch_id"]] == "PRODUCTION_READY"
    payload = json.loads(_sql("select payload from production_snapshots where order_id=:o and revoked_at is null", o=oid))
    assert payload["materials"]["profile"] == {"id": p["id"], "status": "VERIFIED", "line_width_mm": "0.55",
                                               "darkness": "0.9", "bleed_mm": None, "v_max_mm_s": "25",
                                               "measured_at": payload["materials"]["profile"]["measured_at"]}
