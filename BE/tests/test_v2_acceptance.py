"""V2 Phase I (owner approved 2026-11-20): the acceptance tests the earlier phases did not cover yet.

* Test 10: a revision whose save fails (the file store, or the database after the file is written) leaves nothing half-saved,
  and the next edit works; an assistant tool whose save fails is a refused call the model can explain, not a broken turn.
* Test 6: one order, never two submits: a second submit (also one racing the first) is refused, the Staff get one v1.
* Test 5: a reading with words that have no ink (more words than ink, invented text) gives no hint at all; "[?]" stays UNREAD.
* Test 4: an OT-1 photo with washed-out ink end to end: hints, the unread word reaches the Staff, the Staff write it (labelled
  INFERRED, never ORIGINAL), quote, approval, snapshot of that version, motion validation (no robot, MOCK payment).
No test calls a real model or a real robot.
"""
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import get_engine
from app.main import app
from app.services import sketch_work
from app.services.motion import validate as mv
from app.services.stroke_ai import htr_align
from app.services.stroke_ai import trajectory as tj
from app.services.ai.llm import Reply
from tests.test_api_orders import API, _sql, _upload
from tests.test_api_workshop import W, _err, _ot3, cust, policy, staff, store, wcat  # noqa: F401
from tests.test_motion_geometry import BOX, CFG, probes
from tests.test_u4_regions import _scan
from tests.test_u5_studio import Script, _call, providers  # noqa: F401
from tests.test_v2_htr_hints import RT, FakeReader, htr_env  # noqa: F401
from tests.test_v2_order_assistant import _say, _tool_result

SK = "/sketch"


def _edit(client, h, oid, base, **body):
    return client.post(f"{API}/orders/{oid}{SK}/edit", headers=h, json={"base_revision_id": base, **body})


def _draft(client, cust, wcat):
    oid = _ot3(client, cust, wcat, text_="Kính gửi quý khách", submit=False)
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust)
    assert r.status_code == 201, r.text
    return oid, r.json()


def _revs(oid):
    return _sql("select count(*) from sketch_revisions where order_id=:o", o=oid)


# ---------------------------------------------------------------------------------------------------------- Test 10
def test_a_revision_whose_save_fails_leaves_nothing_half_saved_and_the_next_edit_works(client, cust, wcat, store,
                                                                                         monkeypatch):
    oid, w = _draft(client, cust, wcat)
    base, word = w["revision"]["id"], w["document"]["pages"][0]["words"][0]
    move = {"op": "translate", "word_ids": [word["id"]], "params": {"dx_mm": 1}}
    loose = TestClient(app, raise_server_exceptions=False)
    # 1. the file store fails: nothing reaches the database
    real_write = store.write

    def broken(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(store, "write", broken)
    r = _edit(loose, cust, oid, base, **move)
    assert r.status_code == 500
    monkeypatch.setattr(store, "write", real_write)
    # 2. the file is written, then the database fails (after the revision row was flushed): the whole request rolls back
    with monkeypatch.context() as m:
        def audit_down(*a, **k):
            raise RuntimeError("audit store down")
        m.setattr(sketch_work.audit, "record", audit_down)
        r = _edit(loose, cust, oid, base, **move)
    assert r.status_code == 500
    assert _revs(oid) == 1
    assert _sql("select current_sketch_revision_id from orders where id=:o", o=oid) == base
    assert _sql("select count(*) from audit_logs where action='SKETCH_REVISION' and entity_id=:o", o=oid) == 1
    # 3. the next edit works; its file (same path the failed save had written) matches the hash stored in the database
    r = _edit(client, cust, oid, base, **move)
    assert r.status_code == 200, r.text
    assert r.json()["revision"]["seq"] == 2 and _revs(oid) == 2
    g = client.get(f"{API}/orders/{oid}{SK}", headers=cust)
    assert g.status_code == 200 and g.json()["revision"]["id"] == r.json()["revision"]["id"]


def test_an_assistant_edit_whose_save_fails_is_a_refused_call_and_the_turn_still_answers(client, cust, wcat, store,
                                                                                         providers, monkeypatch):
    oid, w = _draft(client, cust, wcat)
    word = w["document"]["pages"][0]["words"][1]
    p = Script("anthropic", [_call("edit_strokes", op="translate", word_ids=[word["id"]], params={"dx_mm": 1}),
                             Reply("Xin lỗi, hệ thống chưa lưu được, bạn thử lại sau nhé.", [], 5, 5)])
    providers["list"] = [p]

    def broken(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(store, "write", broken)
    r = _say(client, cust, oid)
    assert r.status_code == 200, r.text
    assert r.json()["reply"]["status"] == "OK"
    res = _tool_result(p, 0)
    assert res["ok"] is False and res["error"] == "SAVE_FAILED"
    assert _revs(oid) == 1
    assert _sql("select current_sketch_revision_id from orders where id=:o", o=oid) == w["revision"]["id"]
    assert _sql("select count(*) from ai_tool_calls t join ai_messages m on m.id = t.message_id "
                "join ai_sessions s on s.id = m.session_id where s.order_id=:o and not t.ok", o=oid) == 1


# ---------------------------------------------------------------------------------------------------------- Test 6
def test_a_second_submit_is_refused_even_while_the_first_is_running_and_the_staff_get_one_v1(client, cust, staff, wcat,
                                                                                             store):
    sh, _ = staff
    oid, w = _draft(client, cust, wcat)
    r = _edit(client, cust, oid, w["revision"]["id"], op="translate",
              word_ids=[w["document"]["pages"][0]["words"][0]["id"]], params={"dx_mm": 1})
    assert r.status_code == 200
    edited = r.json()["revision"]
    orders_before = _sql("select count(*) from orders where customer_id=(select customer_id from orders where id=:o)", o=oid)
    # a first submit holds the order (as a slow request would) and commits SUBMITTED; the second one waits for it, then sees it
    locked, out = threading.Event(), {}

    def first():
        with get_engine().connect() as c:
            c.execute(text("select id from orders where id=:o for update"), {"o": oid})
            locked.set()
            time.sleep(2.0)
            c.execute(text("update orders set order_status='SUBMITTED', terms_accepted_at=now() where id=:o"), {"o": oid})
            c.commit()

    def second():
        with TestClient(app) as c:
            out["r"] = c.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    h = threading.Thread(target=first)
    h.start()
    locked.wait()
    t = threading.Thread(target=second)
    t.start()
    t.join()
    h.join()
    assert out["r"].status_code == 409 and _err(out["r"]) == "ORDER_NOT_EDITABLE", out["r"].text
    assert _sql("select count(*) from audit_logs where action='ORDER_SUBMIT' and entity_id=:o", o=oid) == 0
    # sent once more, one after the other: still refused; nothing duplicated, the customer's edit is what the Staff get
    r = client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 409 and _err(r) == "ORDER_NOT_EDITABLE"
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 409
    assert [s["version"] for s in client.get(f"{W}/orders/{oid}/sketches", headers=sh).json()] == [1]
    assert _sql("select source_revision_id from sketches where order_id=:o and version=1", o=oid) == edited["id"]
    assert _sql("select count(*) from orders where customer_id=(select customer_id from orders where id=:o)",
                o=oid) == orders_before
    assert _revs(oid) == 2


# ---------------------------------------------------------------------------------------------------------- Test 5
BOXES = [(6, 10, 17, 15), (19, 10, 33, 15), (56, 10, 70, 15), (6, 23, 26, 28), (29, 23, 42, 28), (45, 23, 56, 28)]
REGS = [SimpleNamespace(region_no=i + 1, bbox=b) for i, b in enumerate(BOXES)]


@pytest.mark.parametrize("reading", [
    "Net Viet Nam hôm nay\nxuong viet tay rất vui",                               # more words than there is ink
    "Kính gửi ông bà nội ngoại thân yêu của con\nCon xin chào cả nhà",           # a whole text that is not on the page
    "Mot hai ba bon nam sau bay tam chin muoi muoi mot muoi hai",
])
def test_a_reading_with_words_that_have_no_ink_gives_no_hint(reading):
    res = htr_align.match(REGS, reading)
    assert res["refused"] == "TOO_MANY_WORDS"
    assert all(v["status"] == "UNREAD" and v["text"] is None for v in res["regions"].values())


def test_unreadable_words_stay_unread_and_a_true_reading_is_matched():
    res = htr_align.match(REGS, "Net [?] Nam\nxuong ... tay")
    got = {n: (v["status"], v["text"]) for n, v in res["regions"].items()}
    assert got == {1: ("READ", "Net"), 2: ("UNREAD", None), 3: ("READ", "Nam"),
                   4: ("READ", "xuong"), 5: ("UNREAD", None), 6: ("READ", "tay")}
    assert htr_align.match(REGS, "")["refused"] is None
    assert all(v["status"] == "UNREAD" for v in htr_align.match(REGS, "")["regions"].values())
    ok = htr_align.match(REGS, "Net Viet Nam\nxuong viet tay")
    assert ok["refused"] is None and [v["text"] for _, v in sorted(ok["regions"].items())] == [
        "Net", "Viet", "Nam", "xuong", "viet", "tay"]


def test_an_invented_reading_reaches_neither_the_customer_nor_the_staff_as_text(client, cust, staff, wcat, store, htr_env):
    sh, _ = staff
    htr_env["readers"] = [FakeReader(text="Kính gửi ông bà nội ngoại thân yêu của con\nCon xin chào cả nhà hôm nay")]
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE"}).json()["id"]
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={
        "paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]}).status_code == 200
    assert _upload(client, cust, oid, store, _scan())[0].status_code == 200
    w = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust).json()
    r = client.post(f"{API}/orders/{oid}{RT}", headers=cust, json={"consent": True})
    assert r.status_code == 200, r.text
    hints = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()["text_hints"]
    assert hints["pages"][0]["status"] == "READ" and hints["pages"][0]["check"] == "TOO_MANY_WORDS"
    assert all(v["text"] is None and v["status"] == "UNREAD" for v in hints["words"].values())
    assert len(hints["words"]) == len(w["document"]["pages"][0]["words"])
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    regs = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()["regions"]
    assert all(x["text"] is None and (x["metrics"].get("htr") or {}).get("text") is None for x in regs)


# ---------------------------------------------------------------------------------------------------------- Test 4
def test_an_old_photo_end_to_end_the_unread_word_reaches_the_staff_who_write_it_as_inferred(client, cust, staff, wcat,
                                                                                            store, htr_env):
    sh, _ = staff
    htr_env["readers"] = [FakeReader(text="Net Viet [?]\nxuong viet tay")]      # "Nam" is washed out: the reader says so
    oid = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT1_COPY_RESTORE"}).json()["id"]
    assert client.patch(f"{API}/orders/{oid}", headers=cust, json={
        "paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"],
        "restoration_mode": "ASSISTED"}).status_code == 200
    assert _upload(client, cust, oid, store, _scan(140))[0].status_code == 200
    w = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust)
    assert w.status_code == 201, w.text
    assert client.post(f"{API}/orders/{oid}{RT}", headers=cust, json={"consent": True}).status_code == 200
    view = client.get(f"{API}/orders/{oid}{SK}", headers=cust).json()
    words = sorted(view["document"]["pages"][0]["words"], key=lambda x: (round(x["bbox"][1] / 10), x["bbox"][0]))
    hint = [view["text_hints"]["words"][x["id"]] for x in words]
    assert [h["text"] for h in hint] == ["Net", "Viet", None, "xuong", "viet", "tay"]
    assert hint[2]["status"] == "UNREAD"                                       # the customer sees which word is not read
    # the Staff get v1 = the customer's drawing, with the unread word flagged
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    det = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    by_pos = sorted(det["regions"], key=lambda x: (round(float(x["y0"]) / 10), float(x["x0"])))
    assert [x["metrics"]["htr"]["status"] for x in by_pos] == ["READ", "READ", "UNREAD", "READ", "READ", "READ"]
    nam = by_pos[2]
    assert nam["label"] == "RESTORED"                                           # washed-out ink, recovered, not invented
    # the Staff (after asking the customer) write that one word: a new version, labelled INFERRED, others untouched
    r = client.post(f"{W}/orders/{oid}/sketches/1/regions/{nam['id']}/edit", headers=sh,
                    json={"action": "TEXT", "text": "Nam", "note": "Khách xác nhận chữ thứ ba là 'Nam'"})
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["region_counts"].get("INFERRED") == 1 and v2["version"] == 2
    assert client.post(f"{W}/orders/{oid}/sketches/2/finalize", headers=sh).status_code == 200
    q = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={"char_count": 20})
    assert q.status_code == 201, q.text
    assert client.post(f"{W}/quotations/{q.json()['id']}/send", headers=sh).status_code == 200
    assert client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True}).status_code == 200
    shown = client.get(f"{API}/orders/{oid}/quotation", headers=cust).json()["sketch"]["regions"]
    assert any(x["label"] == "INFERRED" and x["text"] == "Nam" for x in shown)   # the customer approves knowing it
    assert client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={}).status_code == 200
    p = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "VNPAY"}).json()
    assert client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"}).status_code == 200
    assert _sql("select sketch_id from production_snapshots where order_id=:o and revoked_at is null", o=oid) == v2["id"]
    assert _sql("select sketch_content_hash from sketch_approvals where order_id=:o", o=oid) == v2["content_hash"]
    # motion planning + validation of the approved version (measured config, no robot)
    pages = tj.parse(client.get(f"{W}/orders/{oid}/sketches/2", headers=sh).json()["trajectory"])
    rep, plans = mv.validate(pages, probes(origin=(480.0, -150.0, 20.0)), CFG, BOX)   # paper placed inside the test box
    assert rep.passed, rep.error_texts()
    assert plans and sum(len(pl.moves) for pl in plans) > 0
