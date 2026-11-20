"""V2 Phase E2b: AI text hints for the word regions of an OT-1 order (owner approved 2026-11-19).

* reading the photos needs the Admin switch, a reader and the customer's consent every time (wording names the provider and
  says Google may use the photo on the free tier); OT-3 orders and other customers are refused;
* each photo is read once per order; the hints follow the shown revision (edit, undo) and never change strokes or text;
* Gemini refusing / failing moves on to Claude (E2-d); when nobody reads, the page is FAILED and the words stay without hint;
* the daily page cap; the Staff get the hints with v1 (`metrics.htr`, never `text`) and keep them across their edits;
* the assistant sees `text_hint` and is told it is a hint.
No test calls a real model: readers are scripted (fake objects or httpx.MockTransport); the settings are patched in memory
(the real `system_settings` rows are never written).
"""
import json

import httpx
import pytest

from app.services import htr_hints
from app.services.ai import htr
from app.services.ai.llm import ProviderError, Reply
from tests.test_api_orders import API, _sql, _upload
from tests.test_api_workshop import W, _err, _ot3, cust, staff, store, wcat  # noqa: F401
from tests.test_u4_regions import _scan
from tests.test_u5_studio import Script, _call, providers  # noqa: F401
from tests.test_v2_order_assistant import _say, _tool_result
from tests.conftest import auth

SK = "/sketch"
RT = f"{SK}/read-text"
TRANSCRIPT = "Net Viet Nam\nxuong viet tay"
WORDS = ["Net", "Viet", "Nam", "xuong", "viet", "tay"]


class FakeReader:
    def __init__(self, name="gemini", text=TRANSCRIPT, fail=None):
        self.name, self.model, self.text, self.fail, self.calls = name, f"{name}-test", text, fail, 0

    def read(self, jpeg):
        self.calls += 1
        assert jpeg[:2] == b"\xff\xd8"                                   # the photo is sent as JPEG
        if self.fail:
            raise ProviderError(self.fail, 503, "scripted")
        return htr.Transcript(self.name, self.model, self.text, "STOP", 1000, 20)


@pytest.fixture
def htr_env(monkeypatch):
    """Switch on / cap / readers, in memory only."""
    env = {"settings": {"htr_enabled": True, "htr_daily_pages": 1000}, "readers": [FakeReader()]}
    monkeypatch.setattr(htr_hints.HtrService, "setting", lambda self, k: env["settings"][k])
    monkeypatch.setattr(htr, "configured_readers", lambda: env["readers"])
    return env


def _ot1(client, cust, wcat, store):
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE"}).json()["id"]
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={
        "paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]}).status_code == 200
    assert _upload(client, cust, oid, store, _scan())[0].status_code == 200
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust)
    assert r.status_code == 201, r.text
    return oid, r.json()


def _code(r, status):
    assert r.status_code == status, r.text
    return _err(r)


def _hinted(w):
    """Hint texts in reading order of the regions (line, then x)."""
    words = sorted(w["document"]["pages"][0]["words"], key=lambda x: (round(x["bbox"][1] / 10), x["bbox"][0]))
    return [(w["text_hints"]["words"].get(x["id"]) or {}).get("text") for x in words]


# ---------------------------------------------------------------------------------------------------------- vertical slice
def test_the_customer_agrees_the_photo_is_read_once_and_the_hints_follow_the_sketch(client, cust, wcat, store, htr_env):
    oid, w = _ot1(client, cust, wcat, store)
    assert w["text_hints"] == {"state": "NOT_READ", "pages": [{"no": 1, "status": "NOT_READ", "provider": None, "check": None}], "words": {}}
    st = client.get(f"{API}/orders/{oid}{RT}", headers=cust).json()
    assert st["enabled"] and st["available"] and st["providers"] == ["gemini"]
    assert "Google (Gemini)" in st["consent_text"] and "cải thiện dịch vụ" in st["consent_text"]
    assert st["pages"][0]["status"] == "NOT_READ"
    # no consent, no call
    r = client.post(f"{API}/orders/{oid}{RT}", headers=cust, json={"consent": False})
    assert _code(r, 400) == "HTR_CONSENT_REQUIRED" and r.json()["error"]["details"]["consent_text"] == st["consent_text"]
    assert htr_env["readers"][0].calls == 0
    r = client.post(f"{API}/orders/{oid}{RT}", headers=cust, json={"consent": True})
    assert r.status_code == 200, r.text
    assert r.json()["read_now"] == [{"input_id": st["pages"][0]["input_id"], "status": "READ", "provider": "gemini"}]
    w = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()
    assert w["text_hints"]["state"] == "READY" and _hinted(w) == WORDS
    assert all(x["text"] is None for x in w["document"]["pages"][0]["words"])     # a hint never becomes the text
    row = _sql("select json_build_object('s', status, 'p', provider, 'c', consent_text, 'by', consent_by, "
               "'a', jsonb_array_length(attempts)) from htr_readings where order_id=:o", o=oid)
    assert row["s"] == "READ" and row["p"] == "gemini" and row["c"] == st["consent_text"] and row["a"] == 1
    assert _sql("select count(*) from audit_logs where action='HTR_READ' and entity_id=:o", o=oid) == 1
    # read once: asking again sends nothing
    again = client.post(f"{API}/orders/{oid}{RT}", headers=cust, json={"consent": True}).json()
    assert again["read_now"] == [] and htr_env["readers"][0].calls == 1
    # the hints follow edits and undo (computed on the shown revision), strokes are not touched by a hint
    word = w["document"]["pages"][0]["words"][2]
    e = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": w["revision"]["id"], "op": "translate", "word_ids": [word["id"]], "params": {"dx_mm": 1.5}})
    assert e.status_code == 200, e.text
    assert _hinted(e.json()) == WORDS
    u = client.post(f"{API}/orders/{oid}{SK}/undo", headers=cust).json()
    assert _hinted(u) == WORDS and u["revision"]["id"] == w["revision"]["id"]
    # a changed photo (rotation) makes the drawing outdated: no hint is shown on the old drawing
    iid = st["pages"][0]["input_id"]
    assert client.patch(f"{API}/orders/{oid}/inputs/{iid}", headers=cust, json={"rotation_deg": 180}).status_code == 200
    out = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()
    assert out["inputs_changed"] and out["text_hints"] == {"state": "SKETCH_OUTDATED", "pages": [], "words": {}}
    assert client.get(f"{API}/orders/{oid}{RT}", headers=cust).json()["pages"][0]["status"] == "NOT_READ"


def test_reading_is_refused_without_the_switch_a_reader_or_the_right_order(client, cust, wcat, store, htr_env):
    oid, _ = _ot1(client, cust, wcat, store)
    htr_env["settings"]["htr_enabled"] = False
    assert _code(client.post(f"{API}/orders/{oid}{RT}", headers=cust, json={"consent": True}), 409) == "HTR_DISABLED"
    assert client.get(f"{API}/orders/{oid}{RT}", headers=cust).json()["available"] is False
    htr_env["settings"]["htr_enabled"] = True
    htr_env["readers"] = []
    assert _code(client.post(f"{API}/orders/{oid}{RT}", headers=cust, json={"consent": True}), 503) == "HTR_UNAVAILABLE"
    htr_env["readers"] = [FakeReader()]
    other = auth(client, "CUSTOMER")
    assert _code(client.post(f"{API}/orders/{oid}{RT}", headers=other, json={"consent": True}), 404) == "ORDER_NOT_FOUND"
    ot3 = _ot3(client, cust, wcat, submit=False)
    assert _code(client.post(f"{API}/orders/{ot3}{RT}", headers=cust, json={"consent": True}), 422) == "HTR_NOT_OT1"
    # daily cap for the whole system: nothing is sent and nothing stored
    used = client.get(f"{API}/orders/{oid}{RT}", headers=cust).json()["used_today"]
    htr_env["settings"]["htr_daily_pages"] = used
    r = client.post(f"{API}/orders/{oid}{RT}", headers=cust, json={"consent": True})
    assert _code(r, 429) == "HTR_DAILY_CAP" and r.json()["error"]["details"]["pages_needed"] == 1
    assert htr_env["readers"][0].calls == 0 and _sql("select count(*) from htr_readings where order_id=:o", o=oid) == 0


def _mock(handler):
    return httpx.MockTransport(handler)


def test_gemini_refusing_moves_on_to_claude_and_nobody_reading_is_not_a_guess(client, cust, wcat, store, htr_env):
    seen = []

    def gemini(req):
        body = json.loads(req.content)
        seen.append(("gemini", req.headers.get("x-goog-api-key"), body))
        return httpx.Response(200, json={"candidates": [{"finishReason": "RECITATION", "content": {"parts": []}}]})

    def claude(req):
        body = json.loads(req.content)
        seen.append(("anthropic", req.headers.get("x-api-key"), body))
        return httpx.Response(200, json={"content": [{"type": "text", "text": TRANSCRIPT}], "stop_reason": "end_turn",
                                         "usage": {"input_tokens": 900, "output_tokens": 15}})

    htr_env["readers"] = [htr.GeminiReader("g-key", "gemini-test", transport=_mock(gemini)),
                          htr.AnthropicReader("a-key", "claude-test", transport=_mock(claude))]
    oid, _ = _ot1(client, cust, wcat, store)
    st = client.get(f"{API}/orders/{oid}{RT}", headers=cust).json()
    assert st["providers"] == ["gemini", "anthropic"] and "Anthropic (Claude)" in st["consent_text"]
    r = client.post(f"{API}/orders/{oid}{RT}", headers=cust, json={"consent": True}).json()
    assert r["read_now"][0]["status"] == "READ" and r["read_now"][0]["provider"] == "anthropic"
    g, a = seen
    assert g[1] == "g-key" and g[2]["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/jpeg"
    assert g[2]["contents"][0]["parts"][1]["text"] == htr.PROMPT and g[2]["generationConfig"]["temperature"] == 0
    assert a[1] == "a-key" and a[2]["messages"][0]["content"][0]["type"] == "image"
    att = _sql("select attempts from htr_readings where order_id=:o", o=oid)
    assert [(x["provider"], x["ok"]) for x in att] == [("gemini", False), ("anthropic", True)]
    assert att[0]["reason"] == "BLOCKED"
    w = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()
    assert _hinted(w) == WORDS
    # nobody can read a new photo: FAILED, no hint, the order goes on
    oid2, _ = _ot1(client, cust, wcat, store)
    htr_env["readers"] = [FakeReader("gemini", fail="SERVER"), FakeReader("anthropic", fail="AUTH")]
    r = client.post(f"{API}/orders/{oid2}{RT}", headers=cust, json={"consent": True})
    assert r.status_code == 200 and r.json()["read_now"][0]["status"] == "FAILED"
    w2 = client.get(f"{API}/orders/{oid2}{SK}", headers=cust).json()
    assert w2["text_hints"]["state"] == "FAILED" and w2["text_hints"]["words"] == {}
    # a FAILED page is tried again on the next request (it counts again)
    htr_env["readers"] = [FakeReader()]
    r = client.post(f"{API}/orders/{oid2}{RT}", headers=cust, json={"consent": True}).json()
    assert r["read_now"][0]["status"] == "READ"
    assert _hinted(client.get(f"{API}/orders/{oid2}{SK}", headers=cust).json()) == WORDS


def test_the_staff_get_the_hints_with_v1_and_keep_them_across_their_edits(client, cust, staff, wcat, store, htr_env):
    sh, _ = staff
    oid, _ = _ot1(client, cust, wcat, store)
    assert client.post(f"{API}/orders/{oid}{RT}", headers=cust, json={"consent": True}).status_code == 200
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    regs = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()["regions"]
    by_pos = sorted(regs, key=lambda x: (round(float(x["y0"]) / 10), float(x["x0"])))
    assert [x["metrics"]["htr"]["text"] for x in by_pos] == WORDS
    assert all(x["metrics"]["htr"]["status"] == "READ" and x["text"] is None for x in regs)
    # a Staff geometry edit makes v2; the hints stay with their regions
    doc = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()["document"]
    wid = doc["pages"][0]["words"][0]["id"]
    r = client.post(f"{W}/orders/{oid}/sketches/1/edit", headers=sh, json={
        "note": "chỉnh tay", "op": "translate", "word_ids": [wid], "params": {"dx_mm": 1.0}})
    assert r.status_code in (200, 201), r.text
    regs2 = client.get(f"{W}/orders/{oid}/sketches/2", headers=sh).json()["regions"]
    assert sorted(x["metrics"]["htr"]["text"] for x in regs2) == sorted(WORDS)


def test_the_assistant_sees_the_hints_and_is_told_they_are_hints(client, cust, wcat, store, htr_env, providers):
    oid, _ = _ot1(client, cust, wcat, store)
    p = Script("anthropic", [_call("get_sketch"), Reply("Trang có 6 chữ.", [], 5, 5)])
    providers["list"] = [p]
    assert _say(client, cust, oid, "Thư có những chữ gì?").status_code == 200
    res = _tool_result(p, 0)
    assert res["text_hints"]["state"] == "NOT_READ"
    assert all("text_hint" not in w for w in res["pages"][0]["words"])
    assert client.post(f"{API}/orders/{oid}{RT}", headers=cust, json={"consent": True}).status_code == 200
    q = Script("anthropic", [_call("get_sketch"), Reply("Trang có 6 chữ.", [], 5, 5)])
    providers["list"] = [q]
    assert _say(client, cust, oid, "Thư có những chữ gì?").status_code == 200
    res = _tool_result(q, 0)
    assert res["text_hints"]["state"] == "READY" and "có thể sai" in res["text_hints"]["note"]
    assert sorted(w["text_hint"] for w in res["pages"][0]["words"]) == sorted(WORDS)
