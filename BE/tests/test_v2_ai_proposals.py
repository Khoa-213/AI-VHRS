"""AI proposals on an order (migration 0029, owner request 2026-11-22): the assistant helps through the whole Create Order flow,
but the order changes only when the customer applies a proposal.

Scripted providers as in test_v2_order_assistant.py; the tools they call are the real ones on real rows."""
import json

from app.services.ai.llm import ProviderError, Reply
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import _err, _ot3, _user, cust, store, wcat  # noqa: F401
from tests.test_u5_studio import Script, _call, providers  # noqa: F401

SK = "/sketch"


def _say(client, h, oid, text_="Giúp tôi", **extra):
    return client.post(f"{API}/orders/{oid}/assistant/messages", headers=h, json={"text": text_, "ai_consent": True, **extra})


def _apply(client, h, oid, pid):
    return client.post(f"{API}/orders/{oid}/assistant/proposals/{pid}/apply", headers=h)


def _reject(client, h, oid, pid):
    return client.post(f"{API}/orders/{oid}/assistant/proposals/{pid}/reject", headers=h)


def _order(client, h, oid):
    o = client.get(f"{API}/orders/{oid}", headers=h).json()
    text = next((i for i in o["inputs"] if i["kind"] == "TEXT_CONTENT"), None)
    return o, text


def _draft(client, cust, wcat, text_="Một hai ba"):
    oid = _ot3(client, cust, wcat, text_=text_, submit=False)
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust)
    assert r.status_code == 201, r.text
    return oid, r.json()["revision"]["id"]


def _snapshot(client, h, oid):
    o, t = _order(client, h, oid)
    # last_saved_at is left out: the DB trigger sets it on every write of a DRAFT order (also when the turn is put back)
    return {k: o[k] for k in ("quantity", "estimated_price_min", "estimated_price_max", "char_count", "paper_type_id",
                              "pen_type_id", "ink_color_id", "customer_note")}, t["text_content"], t["font_size_mm"]


# ---------------------------------------------------------------------------------------------------------- propose / apply
def test_a_turn_proposes_content_options_and_a_new_sketch_and_the_order_changes_only_when_applied(
        client, cust, wcat, store, providers):
    oid, r1 = _draft(client, cust, wcat)
    before = _snapshot(client, cust, oid)
    providers["list"] = [Script("anthropic", [
        _call("update_text", text="Một hai ba bốn"), _call("set_options", quantity=3),
        _call("generate_sketch"), _call("check_order"),
        Reply("Tôi đề xuất thêm chữ 'bốn', 3 bản và phác thảo mới. Bạn xem rồi bấm Áp dụng nhé.", [], 9, 9)])]
    r = _say(client, cust, oid, "Thêm chữ bốn, in 3 bản và vẽ lại")
    assert r.status_code == 200, r.text
    turn = r.json()
    prop = turn["proposal"]
    assert prop and prop["status"] == "PENDING" and prop["applicable"] and prop["blocked_reason"] is None
    assert turn["reply"]["proposal"]["id"] == prop["id"]
    fields = [c["field"] for c in prop["changes"]]
    assert fields == ["text", "quantity", "sketch"]
    assert {"field": "quantity", "before": 1, "after": 3} in prop["changes"]
    assert prop["sketch_revision_id"] and prop["sketch_revision_id"] != r1
    assert prop["estimate"]["is_estimate"] and prop["estimate"]["price_min"] > int(before[0]["estimated_price_min"])

    # nothing changed on the order: form, price, sketch cursor; redo does not reach the proposal
    assert _snapshot(client, cust, oid) == before
    cur = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()
    assert cur["revision"]["id"] == r1 and not cur["inputs_changed"] and not cur["can_redo"]
    revs = {x["id"]: x for x in client.get(f"{API}/orders/{oid}{SK}/revisions", headers=cust).json()}
    assert revs[prop["sketch_revision_id"]]["proposal_status"] == "PENDING"
    assert revs[r1]["proposal_id"] is None
    assert client.post(f"{API}/orders/{oid}{SK}/redo", headers=cust).status_code == 409        # NOTHING_TO_REDO
    # the proposal picture can be shown before applying
    img = client.get(f"{API}/orders/{oid}{SK}/preview", headers=cust,
                     params={"page": 1, "revision_id": prop["sketch_revision_id"]})
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"

    # the conversation carries the proposal
    conv = client.get(f"{API}/orders/{oid}/assistant/messages", headers=cust).json()
    assert conv["messages"][1]["proposal"]["id"] == prop["id"] and [p["id"] for p in conv["proposals"]] == [prop["id"]]

    a = _apply(client, cust, oid, prop["id"])
    assert a.status_code == 200, a.text
    assert a.json()["proposal"]["status"] == "APPLIED" and not a.json()["proposal"]["applicable"]
    assert a.json()["current_sketch_revision_id"] == prop["sketch_revision_id"]
    o, t = _order(client, cust, oid)
    assert t["text_content"] == "Một hai ba bốn" and o["quantity"] == 3
    assert int(o["estimated_price_min"]) == a.json()["estimate"]["price_min"]
    cur = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()
    assert cur["revision"]["id"] == prop["sketch_revision_id"] and not cur["inputs_changed"]
    assert cur["revision"]["proposal_status"] == "APPLIED"
    # a second click returns the same result; rejecting an applied proposal is refused
    again = _apply(client, cust, oid, prop["id"])
    assert again.status_code == 200 and again.json()["proposal"]["status"] == "APPLIED"
    assert _reject(client, cust, oid, prop["id"]).status_code == 409
    assert _sql("SELECT count(*) FROM audit_logs WHERE action = 'AI_PROPOSAL_APPLIED' AND entity_id = :o", o=oid) == 1

    # undo after applying: the sketch and the text drawn with it go back (the form follows the drawing, V2 Phase D)
    u = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust)
    assert u.status_code == 200 and u.json()["revision"]["id"] == r1 and u.json()["inputs_restored"]
    assert _order(client, cust, oid)[1]["text_content"] == "Một hai ba"
    # redo now reaches the applied revision again
    assert client.post(f"{API}/orders/{oid}{SK}/redo", headers=cust).json()["revision"]["id"] == prop["sketch_revision_id"]
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200


def test_a_read_only_turn_makes_no_proposal(client, cust, wcat, store, providers):
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("gemini", [_call("get_order"), _call("check_order"), _call("list_materials"),
                                           Reply("Đơn đã đủ thông tin.", [], 3, 3)])]
    r = _say(client, cust, oid, "Đơn của tôi ổn chưa?")
    assert r.status_code == 200 and r.json()["proposal"] is None
    assert client.get(f"{API}/orders/{oid}/assistant/proposals", headers=cust).json() == []


def test_a_failed_turn_after_a_tool_ran_leaves_the_order_unchanged_and_makes_no_proposal(client, cust, wcat, store, providers):
    oid, r1 = _draft(client, cust, wcat)
    before = _snapshot(client, cust, oid)
    providers["list"] = [Script("anthropic", [_call("update_text", text="Chữ khác hẳn"), ProviderError("TIMEOUT")]),
                         Script("openai", [ProviderError("SERVER", 503)])]
    r = _say(client, cust, oid, "Đổi nội dung")
    assert r.status_code == 200 and r.json()["reply"]["status"] == "FAILED" and r.json()["proposal"] is None
    assert _snapshot(client, cust, oid) == before
    assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["revision"]["id"] == r1


# ---------------------------------------------------------------------------------------------------------- stale / reject
def test_a_proposal_goes_stale_when_the_order_changes_and_applying_one_makes_the_others_stale(
        client, cust, wcat, store, providers):
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("anthropic", [_call("set_options", quantity=2), Reply("Đề xuất 2 bản.", [], 1, 1)])]
    p1 = _say(client, cust, oid, "2 bản", from_order=True).json()["proposal"]
    providers["list"] = [Script("anthropic", [_call("set_options", quantity=5), Reply("Đề xuất 5 bản.", [], 1, 1)])]
    p2 = _say(client, cust, oid, "5 bản", from_order=True).json()["proposal"]
    assert p1["applicable"] and p2["applicable"] and p2["parent_proposal_id"] is None

    assert _apply(client, cust, oid, p2["id"]).status_code == 200
    listed = {p["id"]: p for p in client.get(f"{API}/orders/{oid}/assistant/proposals", headers=cust).json()}
    assert listed[p1["id"]]["blocked_reason"] == "ORDER_CHANGED" and not listed[p1["id"]]["applicable"]
    r = _apply(client, cust, oid, p1["id"])
    assert r.status_code == 409 and _err(r) == "PROPOSAL_STALE" and r.json()["error"]["details"]["reason"] == "ORDER_CHANGED"
    assert _order(client, cust, oid)[0]["quantity"] == 5

    # the customer edits the form after a proposal: stale, nothing written
    providers["list"] = [Script("anthropic", [_call("set_options", quantity=7), Reply("Đề xuất 7 bản.", [], 1, 1)])]
    p3 = _say(client, cust, oid, "7 bản").json()["proposal"]
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={"customer_note": "giao sớm"}).status_code == 200
    r = _apply(client, cust, oid, p3["id"])
    assert r.status_code == 409 and _err(r) == "PROPOSAL_STALE"
    assert _order(client, cust, oid)[0]["quantity"] == 5


def test_reject_ownership_and_a_submitted_order(client, cust, wcat, store, providers):
    oid, r1 = _draft(client, cust, wcat)
    w = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["document"]
    sid = w["pages"][0]["strokes"][0]["id"]
    providers["list"] = [Script("anthropic", [_call("edit_strokes", op="smooth", stroke_ids=[sid], params={"passes": 1}),
                                              Reply("Đề xuất làm mượt.", [], 1, 1)])]
    prop = _say(client, cust, oid, "Làm mượt nét đầu").json()["proposal"]
    other, _ = _user(client, "CUSTOMER")
    assert client.get(f"{API}/orders/{oid}/assistant/proposals", headers=other).status_code == 404
    assert _apply(client, other, oid, prop["id"]).status_code == 404
    assert _reject(client, other, oid, prop["id"]).status_code == 404
    assert _apply(client, cust, oid, 999999999).status_code == 404

    rj = _reject(client, cust, oid, prop["id"])
    assert rj.status_code == 200 and rj.json()["status"] == "REJECTED" and rj.json()["blocked_reason"] == "REJECTED"
    assert _reject(client, cust, oid, prop["id"]).status_code == 200                       # idempotent
    r = _apply(client, cust, oid, prop["id"])
    assert r.status_code == 409 and _err(r) == "PROPOSAL_NOT_PENDING"
    # the rejected revision stays out of redo and the history marks it
    assert not client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["can_redo"]
    revs = {x["id"]: x for x in client.get(f"{API}/orders/{oid}{SK}/revisions", headers=cust).json()}
    assert revs[prop["sketch_revision_id"]]["proposal_status"] == "REJECTED"
    # continuing from a rejected proposal is refused before any model call
    p = Script("anthropic", [])
    providers["list"] = [p]
    r = _say(client, cust, oid, "Tiếp tục", base_proposal_id=prop["id"])
    assert r.status_code == 409 and _err(r) == "PROPOSAL_NOT_PENDING" and p.seen == []

    providers["list"] = [Script("anthropic", [_call("set_options", quantity=4), Reply("4 bản.", [], 1, 1)])]
    p4 = _say(client, cust, oid, "4 bản").json()["proposal"]
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    r = _apply(client, cust, oid, p4["id"])
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_EDITABLE"
    listed = client.get(f"{API}/orders/{oid}/assistant/proposals", headers=cust).json()
    assert listed[-1]["blocked_reason"] == "ORDER_NOT_EDITABLE"


def test_applying_is_refused_when_a_proposed_material_was_withdrawn(client, cust, wcat, store, providers):
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("anthropic", [_call("set_options", quantity=2), Reply("2 bản.", [], 1, 1)])]
    prop = _say(client, cust, oid, "2 bản").json()["proposal"]
    _sql("UPDATE pen_types SET is_active = false WHERE id = :p RETURNING 1", p=wcat["gel"])
    try:
        r = _apply(client, cust, oid, prop["id"])
        assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "MATERIAL_UNAVAILABLE"
        assert _order(client, cust, oid)[0]["quantity"] == 1
    finally:
        _sql("UPDATE pen_types SET is_active = true WHERE id = :p RETURNING 1", p=wcat["gel"])


# ---------------------------------------------------------------------------------------------------------- continue
def test_a_turn_continues_the_pending_proposal_unless_asked_to_start_from_the_order(client, cust, wcat, store, providers):
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("anthropic", [_call("set_options", quantity=3), Reply("Đề xuất 3 bản.", [], 1, 1)])]
    p1 = _say(client, cust, oid, "3 bản").json()["proposal"]

    second = Script("anthropic", [_call("update_text", text="Một hai ba bốn"), Reply("Thêm chữ bốn.", [], 1, 1)])
    providers["list"] = [second]
    r = _say(client, cust, oid, "và thêm chữ bốn", client_ref="c-2")
    p2 = r.json()["proposal"]
    assert p2["parent_proposal_id"] == p1["id"]
    assert [c["field"] for c in p2["changes"]] == ["text", "quantity"]           # both changes, made on the same order state
    assert '"proposal_base"' in second.seen[0]["system"] and '"quantity": 3' in second.seen[0]["system"]
    o, t = _order(client, cust, oid)
    assert o["quantity"] == 1 and t["text_content"] == "Một hai ba"
    # the same message again returns the stored turn with its proposal
    again = _say(client, cust, oid, "và thêm chữ bốn", client_ref="c-2").json()
    assert again["replayed"] and again["proposal"]["id"] == p2["id"]

    third = Script("anthropic", [_call("set_options", customer_note="giao giờ hành chính"), Reply("Đã ghi chú.", [], 1, 1)])
    providers["list"] = [third]
    p3 = _say(client, cust, oid, "ghi chú giao giờ hành chính", from_order=True).json()["proposal"]
    assert p3["parent_proposal_id"] is None and [c["field"] for c in p3["changes"]] == ["customer_note"]
    assert '"proposal_base"' not in third.seen[0]["system"]

    assert _apply(client, cust, oid, p2["id"]).status_code == 200
    o, t = _order(client, cust, oid)
    assert o["quantity"] == 3 and t["text_content"] == "Một hai ba bốn"


def test_the_stream_sends_the_proposal_before_the_reply(client, cust, wcat, store, providers):
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("openai", [_call("set_options", quantity=2), Reply("2 bản.", [], 1, 1)])]
    r = client.post(f"{API}/orders/{oid}/assistant/messages/stream", headers=cust,
                    json={"text": "2 bản", "ai_consent": True})
    assert r.status_code == 200
    events = [line[len("event: "):] for line in r.text.splitlines() if line.startswith("event: ")]
    assert events[-3:] == ["proposal", "reply", "done"]
    lines = r.text.splitlines()
    reply = json.loads(lines[lines.index("event: reply") + 1][len("data: "):])
    assert reply["proposal"]["changes"] == [{"field": "quantity", "before": 1, "after": 2}]
