"""Upgrade U5 (rest): the assistant's progress as Server-Sent Events, and editing restoration regions in the studio (carried
over to the Staff's official sketch with source CUSTOMER)."""
import json

from app.services.ai.llm import ProviderError, Reply
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import W, _err, cust, staff, store, wcat  # noqa: F401
from tests.test_u4_regions import _scan
from tests.test_u5_studio import S, Script, _call, _new, _text_draft, providers  # noqa: F401


def _events(raw: str) -> list[tuple[str, dict]]:
    out = []
    for block in raw.split("\n\n"):
        lines = [x for x in block.split("\n") if x and not x.startswith(":")]
        name = next((x[7:] for x in lines if x.startswith("event: ")), None)
        data = next((x[6:] for x in lines if x.startswith("data: ")), None)
        if name:
            out.append((name, json.loads(data or "{}")))
    return out


# ---------------------------------------------------------------------------------------------------------- streaming
def test_the_stream_reports_each_step_then_the_same_turn_as_the_plain_route(client, cust, wcat, store, providers):
    d = _text_draft(client, cust, wcat)
    providers["list"] = [Script("p1", [ProviderError("SERVER", 500)]),
                         Script("p2", [_call("choose_materials", pen_type_id=wcat["fountain"],
                                             ink_color_id=wcat["fountain_ink"]),
                                       Reply("Đã đổi sang bút máy.", [], 9, 4)])]
    r = client.post(f"{S}/{d['id']}/messages/stream", headers=cust, json={"text": "đổi bút máy", "ai_consent": True})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream"), r.text
    ev = _events(r.text)
    names = [n for n, _ in ev]
    assert names == ["user_saved", "provider", "failover", "provider", "tool", "reply", "done"], names
    assert ev[2][1] == {"provider": "p1", "reason": "SERVER"} and ev[3][1]["provider"] == "p2"
    tool = ev[4][1]
    assert tool["name"] == "choose_materials" and tool["ok"] and tool["revision_id"]
    turn = ev[5][1]
    assert turn["reply"]["content"] == "Đã đổi sang bút máy." and turn["reply"]["provider"] == "p2"
    assert turn["user"]["id"] == ev[0][1]["id"] and turn["draft"]["content"]["pen_type_id"] == wcat["fountain"]
    # committed by the worker: the plain routes see it
    msgs = client.get(f"{S}/{d['id']}/messages", headers=cust).json()
    assert [m["role"] for m in msgs] == ["USER", "ASSISTANT"] and msgs[1]["tool_calls"][0]["revision_id"] == tool["revision_id"]
    assert _sql("select attempts::text from ai_messages where id=:i", i=turn["reply"]["id"]).count('"ok": false') == 1


def test_refusals_before_the_model_are_plain_http_errors_and_a_full_outage_still_replies(client, cust, wcat, store,
                                                                                       providers):
    d = _text_draft(client, cust, wcat)
    providers["list"] = [Script("p1", [Reply("x", [], 1, 1)])]
    r = client.post(f"{S}/{d['id']}/messages/stream", headers=cust, json={"text": "chào"})
    assert r.status_code == 422 and _err(r) == "AI_CONSENT_REQUIRED"
    providers["list"] = []
    r = client.post(f"{S}/{d['id']}/messages/stream", headers=cust, json={"text": "chào", "ai_consent": True})
    assert r.status_code == 503 and _err(r) == "AI_UNAVAILABLE"
    providers["list"] = [Script("p1", [ProviderError("TIMEOUT", None)])]
    r = client.post(f"{S}/{d['id']}/messages/stream", headers=cust, json={"text": "chào", "ai_consent": True})
    ev = _events(r.text)
    assert [n for n, _ in ev] == ["user_saved", "provider", "failover", "reply", "done"]
    assert ev[3][1]["reply"]["status"] == "FAILED"
    other = _new(client, cust)
    client.delete(f"{S}/{other['id']}", headers=cust)
    r = client.post(f"{S}/{other['id']}/messages/stream", headers=cust, json={"text": "chào", "ai_consent": True})
    assert r.status_code == 409 and _err(r) == "DRAFT_CLOSED"


# ---------------------------------------------------------------------------------------------------------- regions
def _restore_draft(client, h, store, cat, data):
    d = _new(client, h, "RESTORE")
    up = client.post(f"{S}/{d['id']}/images/upload-url", headers=h, json={"mime_type": "image/png", "size_bytes": len(data)})
    store.put(up.json()["upload_url"].removeprefix("memory://"), data)
    r = client.post(f"{S}/{d['id']}/images/confirm", headers=h, json={"image_id": up.json()["image_id"]})
    assert r.status_code == 200, r.text
    r = client.patch(f"{S}/{d['id']}", headers=h, json={"paper_type_id": cat["paper"], "pen_type_id": cat["gel"],
                                                        "ink_color_id": cat["gel_ink"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_customer_edits_regions_in_the_studio_and_the_staff_sketch_gets_the_same_edits(client, cust, staff, wcat, store):
    sh, _ = staff
    d = _restore_draft(client, cust, store, wcat, _scan())
    did = d["id"]
    reg = client.get(f"{S}/{did}/regions", headers=cust).json()
    assert reg["restoration_mode"] == "FAITHFUL" and [r["region_no"] for r in reg["regions"]] == [1, 2, 3, 4, 5, 6]
    assert {r["label"] for r in reg["regions"]} == {"ORIGINAL"}

    r = client.put(f"{S}/{did}/regions/1/2", headers=cust, json={"action": "REMOVE", "note": "vết bẩn"})
    assert r.status_code == 200, r.text
    assert r.json()["content"]["region_edits"] == [{"page": 1, "region": 2, "action": "REMOVE", "note": "vết bẩn"}]
    assert [x["region_no"] for x in client.get(f"{S}/{did}/regions", headers=cust).json()["regions"]] == [1, 3, 4, 5, 6]
    r = client.put(f"{S}/{did}/regions/1/1", headers=cust, json={"action": "TEXT", "text": "Nét"})
    assert r.status_code == 409 and _err(r) == "INFERRED_NOT_ALLOWED"                  # FAITHFUL: no guessed text
    r = client.put(f"{S}/{did}/regions/1/99", headers=cust, json={"action": "REMOVE"})
    assert r.status_code == 409 and _err(r) == "REGION_MISMATCH"
    assert client.patch(f"{S}/{did}", headers=cust, json={"restoration_mode": "ASSISTED"}).status_code == 200
    r = client.put(f"{S}/{did}/regions/1/1", headers=cust, json={"action": "TEXT", "text": "Nét", "note": "chữ đầu"})
    assert r.status_code == 200, r.text
    one = next(x for x in client.get(f"{S}/{did}/regions", headers=cust).json()["regions"] if x["region_no"] == 1)
    assert (one["label"], one["source"], one["text"], one["note"]) == ("INFERRED", "CUSTOMER", "Nét", "chữ đầu")
    r = client.patch(f"{S}/{did}", headers=cust, json={"restoration_mode": "FAITHFUL"})
    assert r.status_code == 409 and _err(r) == "INFERRED_NOT_ALLOWED"                  # would strand the guessed text
    assert client.get(f"{S}/{did}/preview", headers=cust).content[:2] == b"\xff\xd8"
    # undo / redo cover region edits; changing an image drops them (numbers come from the images)
    assert len(client.post(f"{S}/{did}/undo", headers=cust).json()["content"]["region_edits"]) == 1
    assert len(client.post(f"{S}/{did}/redo", headers=cust).json()["content"]["region_edits"]) == 2
    img = d["content"]["images"][0]["id"]
    r = client.patch(f"{S}/{did}/images/{img}", headers=cust, json={"rotation_deg": 0})
    assert r.status_code == 200 and r.json()["content"]["region_edits"] == []
    assert len(client.post(f"{S}/{did}/undo", headers=cust).json()["content"]["region_edits"]) == 2
    r = client.delete(f"{S}/{did}/regions/1/5", headers=cust)
    assert r.status_code == 404 and _err(r) == "REGION_EDIT_NOT_FOUND"

    r = client.post(f"{S}/{did}/submit", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 200, r.text
    oid = r.json()["order_id"]
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})
    assert r.status_code == 201, r.text
    s = r.json()
    assert "CUSTOMER_REGION_EDITS_APPLIED" in s["warnings"] and "CUSTOMER_REGION_EDITS_SKIPPED" not in s["warnings"]
    det = client.get(f"{W}/orders/{oid}/sketches/{s['version']}", headers=sh).json()
    rows = {x["region_no"]: x for x in det["regions"]}
    assert set(rows) == {1, 3, 4, 5, 6}
    assert (rows[1]["label"], rows[1]["source"], rows[1]["text"]) == ("INFERRED", "CUSTOMER", "Nét")
    applied = det["trajectory"]["engine"]["customer_region_edits"]
    assert applied["draft_id"] == did and len(applied["applied"]) == 2 and applied["skipped"] == []
    assert _sql("select count(*) from sketch_regions where sketch_id=:s and source='CUSTOMER'", s=s["id"]) == 1


def test_a_customer_edit_that_no_longer_fits_is_skipped_for_the_staff(client, cust, staff, wcat, store):
    sh, _ = staff
    d = _restore_draft(client, cust, store, wcat, _scan())
    assert client.put(f"{S}/{d['id']}/regions/1/6", headers=cust, json={"action": "REMOVE"}).status_code == 200
    oid = client.post(f"{S}/{d['id']}/submit", headers=cust, json={"terms_accepted": True}).json()["order_id"]
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    rev = _sql("select current_revision_id from studio_drafts where id=:d", d=d["id"])
    _sql("""update studio_revisions set content = jsonb_set(content, '{region_edits}',
            '[{"page": 1, "region": 42, "action": "REMOVE", "note": null}]') where id=:r returning 1""", r=rev)
    s = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={}).json()
    assert "CUSTOMER_REGION_EDITS_SKIPPED" in s["warnings"] and s["region_counts"] == {"ORIGINAL": 6}
