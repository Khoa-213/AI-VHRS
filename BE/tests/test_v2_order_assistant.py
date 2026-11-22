"""V2 Phase C: the AI assistant on an order DRAFT (plan Test 10: timeout, provider failure, duplicate request, concurrent turn,
stale revision, tool outside its rights), and the vertical slice "the AI moves one word the customer selected".

No test calls a real LLM: scripted providers are plugged into the `assistant_providers` dependency (as in test_u5_studio.py).
The tools the scripted model calls are the real ones: OrderService, SketchWorkService and the Geometry Engine on real rows.
Migration 0029: a turn's changes come back as a proposal; the order changes when the customer applies it
(tests/test_v2_ai_proposals.py covers the proposals themselves)."""
import pytest
from sqlalchemy import text

from app.db.session import get_engine
from app.services.ai import assistant as assistant_mod
from app.services.ai.llm import ProviderError, Reply
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import W, _err, _ot3, _user, cust, staff, store, wcat  # noqa: F401
from tests.test_u5_studio import Script, _call, providers  # noqa: F401

SK = "/sketch"


def _say(client, h, oid, text_="Dời chữ này sang phải 1 mm", **extra):
    return client.post(f"{API}/orders/{oid}/assistant/messages", headers=h, json={"text": text_, "ai_consent": True, **extra})


def _draft_with_sketch(client, cust, wcat, text_="Kính gửi quý khách"):
    oid = _ot3(client, cust, wcat, text_=text_, submit=False)
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust)
    assert r.status_code == 201, r.text
    return oid, r.json()


def _strokes(doc):
    return {st["id"]: st for p in doc["pages"] for st in p["strokes"]}


def _tool_result(provider, n=0):
    """The tool results the model received after its n-th tool call round."""
    tool_turns = [t for t in provider.seen[-1]["transcript"] if t["role"] == "tool"]
    return tool_turns[n]["results"][0]["result"]


# ---------------------------------------------------------------------------------------------------------- vertical slice
def test_the_assistant_moves_the_selected_word_and_only_it_and_the_customer_can_undo(client, cust, wcat, store, providers):
    oid, w = _draft_with_sketch(client, cust, wcat)
    page = w["document"]["pages"][0]
    assert [x["text"] for x in page["words"]] == ["Kính", "gửi", "quý", "khách"]       # OT-3 words carry their text
    word = page["words"][1]
    before = _strokes(w["document"])
    p = Script("anthropic", [_call("get_sketch"),
                             _call("edit_strokes", op="translate", word_ids=[word["id"]], params={"dx_mm": 1.0, "dy_mm": 0},
                                   note="Dời chữ gửi sang phải 1 mm"),
                             Reply("Đã dời chữ 'gửi' sang phải 1 mm.", [], 10, 5)])
    providers["list"] = [p]
    r = _say(client, cust, oid, base_revision_id=w["revision"]["id"], selection={"word_ids": [word["id"]]},
             client_ref="m-1")
    assert r.status_code == 200, r.text
    turn = r.json()
    assert turn["reply"]["status"] == "OK" and not turn["replayed"]
    # the model saw the order and the selection as data, and only the order's tools
    assert "<don_hang>" in p.seen[0]["system"] and word["id"] in p.seen[0]["system"]
    assert {"edit_strokes", "get_sketch", "undo_sketch", "update_text"} <= set(p.seen[0]["tools"])
    assert not {"submit", "submit_order", "pay", "cancel"} & set(p.seen[0]["tools"])
    seen = _tool_result(p, 0)
    assert seen["ok"] and seen["pages"][0]["words"][1]["text"] == "gửi" and seen["limits"]["max_shift_mm"] == 3.0
    assert seen["selection"] and {s["id"] for s in seen["selection"]} == set(word["stroke_ids"])

    edit = turn["reply"]["tool_calls"][1]
    prop = turn["proposal"]
    assert edit["name"] == "edit_strokes" and edit["ok"] and edit["revision_id"] == prop["sketch_revision_id"]
    assert turn["sketch_revision_id"] == w["revision"]["id"]                     # 0029: the order is unchanged until applied
    assert prop["applicable"] and [c["field"] for c in prop["changes"]] == ["sketch"]
    assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["revision"]["id"] == w["revision"]["id"]
    a = client.post(f"{API}/orders/{oid}/assistant/proposals/{prop['id']}/apply", headers=cust)
    assert a.status_code == 200, a.text
    assert a.json()["current_sketch_revision_id"] == edit["revision_id"]
    now = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()
    rev = now["revision"]
    assert (rev["author"], rev["tool_name"], rev["provider"], rev["model"]) == ("AI", "edit_strokes", "anthropic", "scripted-1")
    assert rev["parent_id"] == w["revision"]["id"] and rev["operation"]["word_ids"] == [word["id"]]
    after = _strokes(now["document"])
    for sid in word["stroke_ids"]:
        assert [[round(x - 1.0, 2), y] for x, y in after[sid]["points"]] == before[sid]["points"]
    assert {k: v for k, v in after.items() if k not in word["stroke_ids"]} == \
           {k: v for k, v in before.items() if k not in word["stroke_ids"]}

    # the customer undoes the AI's edit like any other
    u = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust).json()
    assert u["revision"]["id"] == w["revision"]["id"]
    conv = client.get(f"{API}/orders/{oid}/assistant/messages", headers=cust).json()
    assert [m["role"] for m in conv["messages"]] == ["USER", "ASSISTANT"] and conv["consented_at"]
    assert _sql("SELECT count(*) FROM ai_tool_calls t JOIN ai_messages m ON m.id = t.message_id "
                "JOIN ai_sessions s ON s.id = m.session_id WHERE s.order_id = :o AND t.sketch_revision_id IS NOT NULL",
                o=oid) == 1


def test_edits_outside_the_selection_out_of_limits_or_unknown_tools_are_refused_and_change_nothing(
        client, cust, wcat, store, providers):
    oid, w = _draft_with_sketch(client, cust, wcat)
    words = w["document"]["pages"][0]["words"]
    p = Script("gemini", [_call("edit_strokes", op="translate", word_ids=[words[0]["id"]], params={"dx_mm": 1}),
                          _call("edit_strokes", op="translate", word_ids=[words[1]["id"]], params={"dx_mm": 5}),
                          _call("submit_order"),
                          _call("edit_strokes", op="explode", word_ids=[words[1]["id"]]),
                          Reply("Không sửa được.", [], 1, 1)])
    providers["list"] = [p]
    r = _say(client, cust, oid, selection={"word_ids": [words[1]["id"]]})
    assert r.status_code == 200, r.text
    calls = r.json()["reply"]["tool_calls"]
    assert [c["ok"] for c in calls] == [False, False, False, False] and r.json()["proposal"] is None
    errors = [t["results"][0]["result"]["error"] for t in p.seen[-1]["transcript"] if t["role"] == "tool"]
    assert errors == ["OUTSIDE_SELECTION", "EDIT_OUT_OF_RANGE", "UNKNOWN_TOOL", "INVALID_EDIT"]
    assert _sql("SELECT count(*) FROM sketch_revisions WHERE order_id = :o", o=oid) == 1
    assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["revision"]["id"] == w["revision"]["id"]


# ---------------------------------------------------------------------------------------------------------- Test 10
def test_a_stale_revision_is_refused_before_any_model_call(client, cust, wcat, store, providers):
    oid, w = _draft_with_sketch(client, cust, wcat)
    first = w["document"]["pages"][0]["strokes"][0]["id"]
    e = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": w["revision"]["id"], "op": "translate", "stroke_ids": [first], "params": {"dx_mm": 0.5}}).json()
    p = Script("anthropic", [])
    providers["list"] = [p]
    r = _say(client, cust, oid, base_revision_id=w["revision"]["id"])            # the customer still looks at r1
    assert r.status_code == 409 and _err(r) == "STALE_REVISION"
    assert r.json()["error"]["details"]["current_revision_id"] == e["revision"]["id"] and p.seen == []
    assert _say(client, cust, oid, base_revision_id=e["revision"]["id"]).status_code == 200


def test_the_same_message_sent_twice_runs_the_model_once(client, cust, wcat, store, providers):
    oid, _ = _draft_with_sketch(client, cust, wcat)
    p = Script("anthropic", [Reply("Chào bạn.", [], 3, 2)])
    providers["list"] = [p]
    a = _say(client, cust, oid, "Xin chào", client_ref="dup-1")
    b = _say(client, cust, oid, "Xin chào", client_ref="dup-1")
    assert a.status_code == b.status_code == 200
    assert not a.json()["replayed"] and b.json()["replayed"]
    assert b.json()["reply"]["id"] == a.json()["reply"]["id"] and len(p.seen) == 1
    conv = client.get(f"{API}/orders/{oid}/assistant/messages", headers=cust).json()
    assert len(conv["messages"]) == 2


def test_a_second_turn_while_one_runs_is_refused(client, cust, wcat, store, providers):
    oid, _ = _draft_with_sketch(client, cust, wcat)
    p = Script("anthropic", [])
    providers["list"] = [p]
    with get_engine().connect() as other:                     # another worker is in a turn of this order
        tx = other.begin()
        assert other.execute(text("SELECT pg_try_advisory_xact_lock(:k, :o)"),
                             {"k": assistant_mod.ORDER_LOCK_KEY, "o": oid}).scalar()
        r = _say(client, cust, oid)
        assert r.status_code == 409 and _err(r) == "AI_TURN_IN_PROGRESS" and p.seen == []
        s = client.post(f"{API}/orders/{oid}/assistant/messages/stream", headers=cust,
                        json={"text": "Xin chào", "ai_consent": True})
        assert s.status_code == 409 and _err(s) == "AI_TURN_IN_PROGRESS"
        tx.rollback()
    assert _say(client, cust, oid).status_code == 200


def test_a_timeout_fails_over_and_when_every_provider_fails_the_customer_gets_a_plain_message(
        client, cust, wcat, store, providers):
    oid, w = _draft_with_sketch(client, cust, wcat)
    slow = Script("anthropic", [ProviderError("TIMEOUT", None, "read timeout")])
    ok = Script("gemini", [Reply("Đơn của bạn đã sẵn sàng.", [], 3, 2)])
    providers["list"] = [slow, ok]
    r = _say(client, cust, oid, "Đơn ổn chưa?")
    assert r.status_code == 200 and r.json()["reply"]["status"] == "OK" and r.json()["reply"]["provider"] == "gemini"
    attempts = _sql("SELECT attempts::text FROM ai_messages m JOIN ai_sessions s ON s.id = m.session_id "
                    "WHERE s.order_id = :o AND m.role = 'ASSISTANT' ORDER BY m.id DESC LIMIT 1", o=oid)
    assert '"TIMEOUT"' in attempts and '"gemini"' in attempts

    providers["list"] = [Script("gemini", [ProviderError("SERVER", 503)]), Script("openai", [ProviderError("TIMEOUT")])]
    r = _say(client, cust, oid, "Còn gì nữa không?")
    assert r.status_code == 200 and r.json()["reply"]["status"] == "FAILED"
    assert "tự soạn" in r.json()["reply"]["content"]
    assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["revision"]["id"] == w["revision"]["id"]


def test_consent_ownership_and_a_submitted_order(client, cust, wcat, store, providers):
    oid, _ = _draft_with_sketch(client, cust, wcat)
    providers["list"] = [Script("anthropic", [])]
    r = client.post(f"{API}/orders/{oid}/assistant/messages", headers=cust, json={"text": "Xin chào"})
    assert r.status_code == 422 and _err(r) == "AI_CONSENT_REQUIRED"
    other, _ = _user(client, "CUSTOMER")
    assert _say(client, other, oid).status_code == 404
    assert client.get(f"{API}/orders/{oid}/assistant/messages", headers=other).status_code == 404
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    r = _say(client, cust, oid)
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_EDITABLE"


# ---------------------------------------------------------------------------------------------------------- content tools
def test_a_text_change_by_the_assistant_marks_the_sketch_outdated_and_a_forgery_flag_reaches_the_staff(
        client, cust, staff, wcat, store, providers):
    sh, _ = staff
    oid, _ = _draft_with_sketch(client, cust, wcat, text_="Một hai ba")
    p = Script("anthropic", [_call("update_text", text="Một hai ba bốn"), _call("check_order"),
                             _call("flag_for_staff", kind="FORGERY_RISK", note="Khách hỏi viết giả chữ ký"),
                             Reply("Đã sửa nội dung. Xưởng không nhận làm giả chữ ký.", [], 5, 5)])
    providers["list"] = [p]
    r = _say(client, cust, oid, "Thêm chữ 'bốn', và ký giả chữ ký của sếp giúp tôi")
    assert r.status_code == 200, r.text
    changed = _tool_result(p, 0)
    assert changed["ok"] and changed["before"]["text"] == "Một hai ba" and changed["sketch_outdated"]
    check = _tool_result(p, 1)
    assert not check["ready"] and any(x["field"] == "sketch" for x in check["problems"])
    assert check["estimate"]["is_estimate"]
    prop = r.json()["proposal"]
    assert prop["changes"][0] == {"field": "text", "before": "Một hai ba", "after": "Một hai ba bốn"}
    assert not client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["inputs_changed"]   # not applied yet
    assert client.post(f"{API}/orders/{oid}/assistant/proposals/{prop['id']}/apply", headers=cust).status_code == 200
    v = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()
    assert v["inputs_changed"]
    r = client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 409 and _err(r) == "SKETCH_OUTDATED"
    # the customer draws again and sends; the Staff see the flag and the conversation
    assert client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust).status_code == 201
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    log = client.get(f"{W}/orders/{oid}/assistant", headers=sh)
    assert log.status_code == 200, log.text
    body = log.json()
    assert body["has_conversation"] and [f["kind"] for f in body["flags"]] == ["FORGERY_RISK"]
    assert [t["name"] for t in body["messages"][1]["tools"]] == ["update_text", "check_order", "flag_for_staff"]
    assert client.get(f"{W}/orders/{oid}/assistant", headers=cust).status_code == 403


def test_the_stream_reports_each_tool_and_the_final_turn(client, cust, wcat, store, providers):
    oid, w = _draft_with_sketch(client, cust, wcat)
    sid = w["document"]["pages"][0]["strokes"][0]["id"]
    providers["list"] = [Script("openai", [_call("edit_strokes", op="smooth", stroke_ids=[sid], params={"passes": 2}),
                                           Reply("Đã làm mượt nét.", [], 2, 2)])]
    r = client.post(f"{API}/orders/{oid}/assistant/messages/stream", headers=cust,
                    json={"text": "Làm mượt nét đầu", "ai_consent": True, "base_revision_id": w["revision"]["id"],
                          "selection": {"stroke_ids": [sid]}})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [line[len("event: "):] for line in r.text.splitlines() if line.startswith("event: ")]
    assert events[0] == "user_saved" and "tool" in events and events[-3:] == ["proposal", "reply", "done"]
    assert client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["revision"]["id"] == w["revision"]["id"]
    pid = client.get(f"{API}/orders/{oid}/assistant/proposals", headers=cust).json()[-1]["sketch_revision_id"]
    now = client.get(f"{API}/orders/{oid}{SK}", headers=cust, params={"revision_id": pid}).json()["revision"]
    assert now["author"] == "AI" and now["provider"] == "openai" and now["operation"]["op"] == "smooth"
    assert now["proposal_status"] == "PENDING"
