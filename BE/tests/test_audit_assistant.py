"""Audit 2026-11-27, batch 4 (docs/audit/05_ISSUES_AND_RECOMMENDATIONS.md): the AI assistant.

AI-02  only a few turns run at once, and a turn stops asking the model once it is out of time
AI-03  the assistant cannot change the customer's own drawing by walking the history
AI-04  what a provider's tools changed before it failed is undone
AI-06  an empty reply is a failure, not "I have updated the draft"; the calls of failed providers are counted

No real LLM: scripted providers (tests/test_u5_studio.py) call the real tools on real rows.
"""
import time

from app.core.config import get_settings
from app.services.ai import assistant as assistant_mod
from app.services.ai.llm import ProviderError, Reply
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import _err, cust, staff, store, wcat  # noqa: F401
from tests.test_u5_studio import Script, _call, providers  # noqa: F401
from tests.test_v2_order_assistant import SK, _draft_with_sketch, _say


def _revision_count(oid):
    return _sql("select count(*) from sketch_revisions where order_id=:o", o=oid)


def _last_reply(oid, column):
    return _sql(f"select m.{column} from ai_messages m join ai_sessions s on s.id = m.session_id "
                "where s.order_id=:o and m.role='ASSISTANT' order by m.id desc limit 1", o=oid)


# ---------------------------------------------------------------------------------------------- AI-04
def test_what_a_failed_provider_changed_is_undone_before_the_next_one_starts(client, cust, wcat, store, providers):
    oid, w = _draft_with_sketch(client, cust, wcat)
    word = w["document"]["pages"][0]["words"][1]
    n0 = _revision_count(oid)
    edit = _call("edit_strokes", op="translate", word_ids=[word["id"]], params={"dx_mm": 1.0, "dy_mm": 0}, note="dời")
    a = Script("anthropic", [edit, ProviderError("SERVER", 503, "boom")])      # edits, then dies
    b = Script("gemini", [Reply("Tôi chưa sửa gì.", [], 3, 2)])               # answers without touching anything
    providers["list"] = [a, b]
    r = _say(client, cust, oid, base_revision_id=w["revision"]["id"])
    assert r.status_code == 200 and r.json()["reply"]["status"] == "OK" and r.json()["reply"]["provider"] == "gemini", r.text
    assert r.json()["proposal"] is None                                       # nothing is proposed: B changed nothing
    assert _revision_count(oid) == n0                                         # A's revision did not survive A's failure
    assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["revision"]["id"] == w["revision"]["id"]
    redo = client.post(f"{API}/orders/{oid}{SK}/redo", headers=cust)
    assert redo.status_code == 409 and _err(redo) == "NOTHING_TO_REDO"        # Redo cannot walk into an edit nobody proposed


def test_when_every_provider_fails_after_editing_nothing_is_left_behind(client, cust, wcat, store, providers):
    oid, w = _draft_with_sketch(client, cust, wcat)
    word = w["document"]["pages"][0]["words"][0]
    n0 = _revision_count(oid)
    edit = _call("edit_strokes", op="translate", word_ids=[word["id"]], params={"dx_mm": 1.0, "dy_mm": 0}, note="dời")
    providers["list"] = [Script("anthropic", [edit, ProviderError("TIMEOUT")]), Script("gemini", [edit, ProviderError("SERVER", 500)])]
    r = _say(client, cust, oid, base_revision_id=w["revision"]["id"])
    assert r.status_code == 200 and r.json()["reply"]["status"] == "FAILED"
    assert _revision_count(oid) == n0
    assert _err(client.post(f"{API}/orders/{oid}{SK}/redo", headers=cust)) == "NOTHING_TO_REDO"
    assert _last_reply(oid, "model_calls") == 4                               # AI-06: two calls each, all of them counted


# ---------------------------------------------------------------------------------------------- AI-06
def test_an_empty_reply_is_a_failure_and_never_i_have_updated_the_draft(client, cust, wcat, store, providers):
    oid, w = _draft_with_sketch(client, cust, wcat)
    providers["list"] = [Script("anthropic", [Reply("", [], 5, 0)]), Script("gemini", [Reply("   ", [], 5, 0)])]
    r = _say(client, cust, oid, "Đổi giúp tôi cỡ chữ")
    assert r.status_code == 200 and r.json()["reply"]["status"] == "FAILED", r.text
    assert "đã cập nhật" not in r.json()["reply"]["content"].lower()
    assert '"BAD_RESPONSE"' in _last_reply(oid, "attempts::text")

    providers["list"] = [Script("anthropic", [Reply("", [], 5, 0)]), Script("gemini", [Reply("Bạn muốn cỡ chữ bao nhiêu?", [], 5, 4)])]
    r = _say(client, cust, oid, "Đổi giúp tôi cỡ chữ")
    assert r.json()["reply"]["status"] == "OK" and r.json()["reply"]["provider"] == "gemini"       # the next provider answers
    assert _last_reply(oid, "model_calls") == 2                                                      # the empty one is counted too


def test_a_silent_reply_after_real_work_still_closes_the_turn(client, cust, wcat, store, providers):
    oid, w = _draft_with_sketch(client, cust, wcat)
    word = w["document"]["pages"][0]["words"][1]
    providers["list"] = [Script("anthropic", [
        _call("edit_strokes", op="translate", word_ids=[word["id"]], params={"dx_mm": 1.0, "dy_mm": 0}, note="dời"),
        Reply("", [], 5, 0)])]
    r = _say(client, cust, oid, base_revision_id=w["revision"]["id"])
    assert r.status_code == 200 and r.json()["reply"]["status"] == "OK" and r.json()["proposal"] is not None, r.text


# ---------------------------------------------------------------------------------------------- AI-03
def test_the_assistant_cannot_swap_the_customers_drawing_by_undoing(client, cust, wcat, store, providers):
    oid, w1 = _draft_with_sketch(client, cust, wcat)
    canvas = {"version": 1, "paper": "A4", "strokes": [{"points": [[20, 200], [60, 200], [60, 230]]}]}
    r = client.put(f"{API}/orders/{oid}/inputs/canvas", headers=cust, json={"canvas_data": canvas})
    assert r.status_code == 200, r.text
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust)         # a second drawing, now with the customer's own lines
    assert r.status_code == 201, r.text
    w2 = r.json()
    stored = _sql("select canvas_data from order_inputs where order_id=:o and kind='CANVAS'", o=oid)
    assert stored is not None

    p = Script("anthropic", [_call("undo_sketch", discard_input_changes=True), Reply("Tôi không tự hoàn tác bước này được.", [], 5, 5)])
    providers["list"] = [p]
    r = _say(client, cust, oid, "Hoàn tác giúp tôi", base_revision_id=w2["revision"]["id"])
    assert r.status_code == 200, r.text
    tool = r.json()["reply"]["tool_calls"][0]
    assert tool["name"] == "undo_sketch" and tool["ok"] is False
    told = [t for t in p.seen[-1]["transcript"] if t["role"] == "tool"][0]["results"][0]["result"]
    assert told["error"] == "CANVAS_WOULD_CHANGE"                             # the model is told why, in words it can pass on
    assert _sql("select canvas_data from order_inputs where order_id=:o and kind='CANVAS'", o=oid) == stored   # still the customer's
    assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["revision"]["id"] == w2["revision"]["id"]

    # the customer's own Undo still goes back across the drawing (and takes the canvas with it, as before)
    u = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust)
    assert u.status_code == 200 and u.json()["revision"]["id"] == w1["revision"]["id"], u.text


# ---------------------------------------------------------------------------------------------- AI-02
def test_only_a_few_turns_run_at_once_the_rest_are_told_to_retry(client, cust, wcat, store, providers, monkeypatch):
    oid, w = _draft_with_sketch(client, cust, wcat)
    monkeypatch.setattr(get_settings(), "ai_max_concurrent_turns", 1)
    slots = assistant_mod._turn_slots()
    assert slots.acquire(blocking=False)                                       # another customer's turn holds the only slot
    try:
        ran = Script("anthropic", [Reply("xin chào", [], 1, 1)])
        providers["list"] = [ran]
        r = _say(client, cust, oid, "Chào bạn")
        assert r.status_code == 503 and _err(r) == "AI_BUSY", r.text
        assert ran.seen == []                                                  # the model was not called, nothing was stored
        assert _sql("select count(*) from ai_messages m join ai_sessions s on s.id=m.session_id where s.order_id=:o", o=oid) == 0
    finally:
        slots.release()
    r = _say(client, cust, oid, "Chào bạn")
    assert r.status_code == 200 and r.json()["reply"]["status"] == "OK"
    assert assistant_mod._turn_slots().acquire(blocking=False)                 # the slot came back after the turn
    assistant_mod._turn_slots().release()


def test_a_turn_out_of_time_stops_asking_the_model(client, cust, wcat, store, providers, monkeypatch):
    oid, w = _draft_with_sketch(client, cust, wcat)
    monkeypatch.setattr(get_settings(), "ai_turn_deadline_seconds", 0.05)

    def slow_first(transcript):
        time.sleep(0.12)
        return _call("get_order")
    p = Script("anthropic", [slow_first, _call("get_order"), _call("get_order"), Reply("xong", [], 1, 1)])
    providers["list"] = [p]
    r = _say(client, cust, oid, "Xem đơn giúp tôi")
    assert r.status_code == 200 and r.json()["reply"]["status"] == "OK", r.text
    assert len(p.seen) == 1                                                    # one call, then the deadline: no second round


# ---------------------------------------------------------------------------------------------- D02
def _revert(client, h, oid, pid):
    return client.post(f"{API}/orders/{oid}/assistant/proposals/{pid}/revert", headers=h)


def test_a_proposal_says_whether_the_screen_may_apply_it_or_the_customer_must_decide(client, cust, wcat, store, providers):
    from tests.test_v2_ai_proposals import _draft
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("anthropic", [_call("update_text", text="Một hai ba bốn"), _call("generate_sketch"),
                                              Reply("Tôi đề xuất thêm chữ 'bốn'.", [], 5, 5)])]
    safe = _say(client, cust, oid, "Thêm chữ bốn").json()["proposal"]
    assert safe["needs_confirmation"] is False and safe["confirm_reasons"] == []      # text and sketch: Undo brings them back

    oid2, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("anthropic", [_call("set_options", quantity=5, customer_note="giao buổi sáng"),
                                              Reply("Tôi đề xuất 5 bản và ghi chú giao buổi sáng.", [], 5, 5)])]
    risky = _say(client, cust, oid2, "In 5 bản, giao buổi sáng").json()["proposal"]
    assert risky["needs_confirmation"] is True and set(risky["confirm_reasons"]) == {"quantity", "customer_note"}


def test_a_redraw_that_throws_away_the_customers_own_edits_waits_for_the_customer(client, cust, wcat, store, providers):
    oid, w = _draft_with_sketch(client, cust, wcat)
    word = w["document"]["pages"][0]["words"][1]
    mine = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": w["revision"]["id"], "op": "translate", "word_ids": [word["id"]], "params": {"dx_mm": 1.0, "dy_mm": 0}})
    assert mine.status_code in (200, 201), mine.text
    cur = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["revision"]["id"]
    providers["list"] = [Script("anthropic", [_call("generate_sketch", discard_edits=True), Reply("Tôi đề xuất vẽ lại.", [], 5, 5)])]
    r = _say(client, cust, oid, "Vẽ lại từ đầu", base_revision_id=cur)
    assert r.status_code == 200, r.text
    prop = r.json()["proposal"]
    assert prop is not None and prop["needs_confirmation"] is True and "DISCARDS_MANUAL_EDITS" in prop["confirm_reasons"], prop


def test_an_applied_proposal_can_be_taken_back_whole_while_nothing_else_changed(client, cust, wcat, store, providers):
    from tests.test_v2_ai_proposals import _apply, _draft, _order, _snapshot
    oid, r1 = _draft(client, cust, wcat)
    before = _snapshot(client, cust, oid)
    providers["list"] = [Script("anthropic", [_call("update_text", text="Một hai ba bốn"), _call("set_options", quantity=3),
                                              _call("generate_sketch"), Reply("Tôi đề xuất thêm chữ, 3 bản.", [], 9, 9)])]
    prop = _say(client, cust, oid, "Thêm chữ bốn, in 3 bản").json()["proposal"]
    assert prop["revertible"] is False                                         # nothing applied yet
    no = _revert(client, cust, oid, prop["id"])
    assert no.status_code == 409 and _err(no) == "PROPOSAL_NOT_APPLIED"

    applied = _apply(client, cust, oid, prop["id"]).json()
    assert applied["proposal"]["status"] == "APPLIED" and applied["proposal"]["revertible"] is True
    assert _order(client, cust, oid)[0]["quantity"] == 3

    back = _revert(client, cust, oid, prop["id"])
    assert back.status_code == 200, back.text
    assert back.json()["proposal"]["status"] == "REJECTED" and back.json()["proposal"]["revertible"] is False
    assert back.json()["current_sketch_revision_id"] == r1
    assert _snapshot(client, cust, oid) == before                              # every field, the quantity Undo could not restore too
    assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["revision"]["id"] == r1
    assert _err(client.post(f"{API}/orders/{oid}{SK}/redo", headers=cust)) == "NOTHING_TO_REDO"    # its sketch left the Redo path
    assert _sql("select count(*) from audit_logs where action='AI_PROPOSAL_REVERTED' and entity_id=:o", o=oid) == 1
    again = _revert(client, cust, oid, prop["id"])
    assert again.status_code == 409 and _err(again) == "PROPOSAL_NOT_APPLIED"


def test_a_proposal_is_not_taken_back_once_the_customer_changed_the_order_again(client, cust, wcat, store, providers):
    from tests.test_v2_ai_proposals import _apply, _draft, _order
    oid, _ = _draft(client, cust, wcat)
    providers["list"] = [Script("anthropic", [_call("set_options", quantity=4), Reply("Tôi đề xuất 4 bản.", [], 5, 5)])]
    prop = _say(client, cust, oid, "In 4 bản").json()["proposal"]
    assert _apply(client, cust, oid, prop["id"]).status_code == 200
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={"quantity": 7}).status_code == 200      # the customer's own change
    r = _revert(client, cust, oid, prop["id"])
    assert r.status_code == 409 and _err(r) == "PROPOSAL_STALE" and r.json()["error"]["details"]["reason"] == "ORDER_CHANGED"
    assert _order(client, cust, oid)[0]["quantity"] == 7                       # their change stays
    stranger = __import__("tests.conftest", fromlist=["auth"]).auth(client, "CUSTOMER")
    assert _revert(client, stranger, oid, prop["id"]).status_code == 404
