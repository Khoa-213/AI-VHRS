"""OT-2 Phase O3 (owner approved 2026-11-21, docs/OT2_LEARNED_STYLE_PLAN.md section 10): writing an order's text with the
writer's approved handwriting style.

The styles here come from the synthetic sheets of tests/test_ot2_style_sheet.py (Hershey glyphs drawn into the boxes and
photographed), so they check the composition (every Vietnamese letter, marks in the right place, the writer's own scale,
samples varied but reproducible, missing letters reported, never another font) and the order flow end to end. How real
handwriting looks is measured on real sheets, not here. No test calls a real model or a real robot; payment is MOCK.
"""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache

import pytest

from app.core.errors import AppError
from app.services.motion import validate as mv
from app.services.stroke_ai import engine, sample_sheet as ss, text_to_stroke as tts
from app.services.stroke_ai import trajectory as tj
from app.services.stroke_ai.style_source import CAP_XH_DEFAULT, StyleSource
from tests.conftest import auth
from tests.test_api_orders import API, _sql
from tests.test_api_orders import _upload as _order_upload
from tests.test_api_workshop import W, cust, policy, staff, store, wcat  # noqa: F401
from tests.test_motion_geometry import BOX, CFG, probes
from tests.test_ot2_style_sheet import _err, _upload, photo, read

SK = "/sketch"
VOWELS = "aăâeêioôơuưyAĂÂEÊIOÔƠUƯY"
TONES = "̣́̀̉̃"
CONSONANTS = "bcdđghklmnpqrstvxBCDĐGHKLMNPQRSTVX"
ALL_VI = CONSONANTS + "".join(unicodedata.normalize("NFC", v + t) for v in VOWELS for t in [""] + list(TONES))


@lru_cache(maxsize=1)
def _synthetic_set() -> str:
    return json.dumps(ss.glyph_set([read(p, flawed=False) for p in (1, 2, 3)]))


def synthetic_set() -> dict:
    return json.loads(_synthetic_set())


def _box(polys):
    xs = [p[0] for s in polys for p in s]
    ys = [p[1] for s in polys for p in s]
    return min(xs), min(ys), max(xs), max(ys)


def _style(gs: dict) -> dict:
    return {"id": 7, "sha256": "ab" * 32, "glyph_set": gs}


def _gen(text: str, gs: dict, **kw):
    args = {"font_uri": None, "font_size_mm": 8, "alignment": "LEFT", "paper_size": "A5", "seed": None,
            "v_max_mm_s": 30.0, "pen_category": None, "chars": len(text)}
    args.update(kw)
    return engine.generate_ot3(text, None, style=_style(gs), **args)


# ------------------------------------------------------------------------------------------------------- composition
def test_every_vietnamese_letter_digit_and_sheet_punctuation_is_written_with_the_writer_s_glyphs():
    src = StyleSource(synthetic_set(), seed=1)
    assert src.missing(ALL_VI + "0123456789" + "".join(ss.PUNCT)) == []
    assert src.scale_source == "writer_capitals"
    assert abs(src.cap_xh - 21.0 / 14.0) < 0.06                  # the synthetic writer: Hershey caps 21 over x-height 14
    a, big_a = src.char("a"), src.char("A")
    ratio = (9.0 - _box(big_a.base)[1]) / (9.0 - _box(a.base)[1])      # heights above the baseline (y = 9)
    assert 1.25 < ratio < 1.65                                    # a capital is taller by the writer's own ratio
    for ch in "@#%&/€":                                          # not on the sheet: never drawn from another font
        assert src.char(ch) is None


def test_marks_are_the_writer_s_own_and_sit_where_vietnamese_puts_them():
    src = StyleSource(synthetic_set(), seed=1)
    base_top = _box(src.char("a").base)[1]
    up = src.char("ấ")                                            # circumflex, then the acute above it
    assert len(up.marks) >= 2 and all(_box([m])[3] < base_top for m in up.marks)
    hat, tone = sorted(up.marks, key=lambda m: -_box([m])[3])[:2]
    assert _box([tone])[3] <= _box([hat])[1] + 0.5                # the tone sits on top of the hat, not through it
    dot = src.char("ạ")
    assert len(dot.marks) == 1 and _box(dot.marks)[1] > 9.0      # under the baseline (y = 9)
    i_plain, i_acute = src.char("i"), src.char("í")
    assert len(i_acute.base) == len(i_plain.base) - 1              # the dot of the i gives way to the tone mark
    horn = src.char("ở")
    assert horn is not None and len(horn.marks) == 1               # ơ comes from the sheet, the hook is added


def test_a_letter_repeated_takes_another_sample_each_time_and_the_same_content_gives_the_same_strokes():
    gs = {"format": "ot2-glyphs/1", "glyphs": {
        "a": [{"id": f"s{n}", "strokes": [[[0.0, -1.0], [0.4 + 0.2 * n, 0.0]]], "pen_width_mm": 0.5} for n in range(3)]},
        "marks": {}}
    def widths(seed):
        src = StyleSource(gs, seed)
        return [round(src.char("a").advance, 3) for _ in range(6)]
    w = widths(11)
    assert len(set(w[:3])) == 3 and w[:3] == w[3:]                  # every sample once before any repeats, then the same cycle
    assert widths(11) == w                                          # reproducible
    assert any(widths(s) != w for s in range(12, 20))               # another content seed, another choice
    a = _gen("aaa aaa", synthetic_set())
    b = _gen("aaa aaa", synthetic_set())
    assert [s.points for s in a.pages[0].strokes] == [s.points for s in b.pages[0].strokes]


def test_letters_the_style_lacks_are_listed_never_replaced():
    gs = synthetic_set()
    gs["glyphs"].pop("b")
    gs["marks"].pop("tilde")
    with pytest.raises(AppError) as e:
        _gen("bà bé ngã", gs)
    assert e.value.code == "UNSUPPORTED_CHARS"
    assert sorted({d["char"] for d in e.value.details}) == ["b", "ã"]
    with pytest.raises(AppError) as e:
        _gen("abc", {"format": "something-else"})
    assert e.value.code == "STYLE_UNAVAILABLE"


def test_the_drawing_records_the_style_and_is_judged_as_ot2():
    g = _gen("Kính gửi Ngọc Ánh,\nchúc mừng sinh nhật!", synthetic_set(),
             layout=None, font_size_mm=7)
    e = g.engine
    assert e["name"] == "learned-style-compose" and e["style_id"] == 7 and e["glyph_set_sha256"] == "ab" * 32
    assert e["font_uri"] is None and e["letters"] == "separate" and e["style_scale"] == "writer_capitals"
    assert g.complexity in ("MEDIUM", "COMPLEX")                    # OT-2 is never SIMPLE (no similarity to a template)
    words = [s.group for s in g.pages[0].strokes]
    assert len(set(words)) == 8                                      # one stroke group per word, as for OT-3
    no_caps = synthetic_set()
    for ch in list(no_caps["glyphs"]):
        if ch.isupper():
            no_caps["glyphs"].pop(ch)
    assert StyleSource(no_caps).cap_xh == CAP_XH_DEFAULT


# ------------------------------------------------------------------------------------------------------- order flow
def _approved_style(client, h, store, *, reject_chars: str = "") -> int:   # noqa: F811
    mgr = auth(client, "MANAGER")
    sid = client.post(f"{API}/styles", headers=h, json={"name": "Nét thử", "right_to_use_confirmed": True}).json()["id"]
    for p in (1, 2, 3):
        assert _upload(client, h, sid, p, photo(p, False), store).status_code == 200
    assert client.post(f"{API}/styles/{sid}/submit", headers=h).status_code == 200
    cells = client.get(f"{API}/manager/styles/{sid}", headers=mgr).json()["cells"]
    for c in cells:
        if c["char"] in reject_chars:
            assert client.put(f"{API}/manager/styles/{sid}/samples/{c['cell']}", headers=mgr,
                              json={"rejected": True}).status_code == 200
    r = client.post(f"{API}/manager/styles/{sid}/approve", headers=mgr)
    assert r.status_code == 200, r.text
    return sid


def _ot2(client, h, wcat, sid, text_):   # noqa: F811
    oid = client.post(f"{API}/orders", headers=h, json={"order_type": "OT2_LEARNED_STYLE"}).json()["id"]
    assert client.patch(f"{API}/orders/{oid}", headers=h, json={
        "paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]}).status_code == 200
    r = client.put(f"{API}/orders/{oid}/inputs/text", headers=h,
                   json={"text_content": text_, "handwriting_style_id": sid, "font_size_mm": 8, "alignment": "LEFT"})
    assert r.status_code == 200, r.text
    return oid


def test_an_ot2_order_end_to_end_with_the_customer_s_style(client, cust, staff, wcat, store):   # noqa: F811
    sh, _ = staff
    sid = _approved_style(client, cust, store)
    oid = _ot2(client, cust, wcat, sid, "Kính gửi Ngọc Ánh")
    w = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust)
    assert w.status_code == 201, w.text
    doc = w.json()["document"]
    assert doc["engine"]["name"] == "learned-style-compose" and doc["engine"]["style_id"] == sid
    words = doc["pages"][0]["words"]
    assert len(words) == 4
    r = client.post(f"{API}/orders/{oid}{SK}/edit", headers=cust, json={
        "base_revision_id": w.json()["revision"]["id"], "op": "translate", "word_ids": [words[0]["id"]],
        "params": {"dx_mm": 1.5}})
    assert r.status_code == 200, r.text                              # D3: the customer moves a word of their own writing
    r = client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 422                                      # BR-23: the right to use the handwriting
    r = client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True, "confirm_right_to_use": True})
    assert r.status_code == 200, r.text
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    v1 = client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()
    assert tj.parse(v1["trajectory"])                                # v1 = the customer's drawing (D2)
    assert client.post(f"{W}/orders/{oid}/sketches/1/finalize", headers=sh).status_code == 200
    q = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={})
    assert q.status_code == 201, q.text
    assert client.post(f"{W}/quotations/{q.json()['id']}/send", headers=sh).status_code == 200
    assert client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True}).status_code == 200
    assert client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={}).status_code == 200
    p = client.post(f"{API}/orders/{oid}/payments/deposit", headers=cust, json={"gateway": "VNPAY"}).json()
    assert client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"}).status_code == 200
    assert _sql("select count(*) from production_snapshots where order_id=:o and revoked_at is null", o=oid) == 1
    pages = tj.parse(client.get(f"{W}/orders/{oid}/sketches/1", headers=sh).json()["trajectory"])
    rep, plans = mv.validate(pages, probes(origin=(480.0, -150.0, 20.0)), CFG, BOX)
    assert rep.passed, rep.error_texts()
    assert plans and sum(len(pl.moves) for pl in plans) > 0


def test_missing_letters_a_style_that_is_gone_and_an_order_without_a_style(client, cust, staff, wcat, store):  # noqa: F811
    sh, _ = staff
    sid = _approved_style(client, cust, store, reject_chars="b")
    other = auth(client, "CUSTOMER")
    oid = _ot2(client, cust, wcat, sid, "bé ngoan")
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust)
    assert r.status_code == 422 and _err(r) == "UNSUPPORTED_CHARS"
    assert {d["char"] for d in r.json()["error"]["details"]} == {"b"}
    r = client.put(f"{API}/orders/{oid}/inputs/text", headers=other, json={"text_content": "x", "handwriting_style_id": sid})
    assert r.status_code in (403, 404)                               # not their order
    oid2 = client.post(f"{API}/orders", headers=other, json={"order_type": "OT2_LEARNED_STYLE"}).json()["id"]
    r = client.put(f"{API}/orders/{oid2}/inputs/text", headers=other, json={"text_content": "x", "handwriting_style_id": sid})
    assert r.status_code == 422 and _err(r) == "INVALID_STYLE"       # someone else's style
    assert client.put(f"{API}/orders/{oid}/inputs/text", headers=cust, json={
        "text_content": "Con ngoan", "handwriting_style_id": sid}).status_code == 200
    assert client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust).status_code == 201
    assert client.delete(f"{API}/styles/{sid}", headers=cust).status_code == 204
    r = client.post(f"{API}/orders/{oid}{SK}/generate", headers=cust, json={"discard_edits": True})
    assert r.status_code == 409 and _err(r) == "STYLE_UNAVAILABLE"   # never silently another font
    # an OT-2 order with only a free-form sample photo is still drawn by hand (O3-a)
    oid3 = client.post(f"{API}/orders", headers=cust, json={"order_type": "OT2_LEARNED_STYLE"}).json()["id"]
    assert _order_upload(client, cust, oid3, store, photo(1, False), kind="HANDWRITING_SAMPLE",
                         mime="image/jpeg")[0].status_code == 200
    assert client.put(f"{API}/orders/{oid3}/inputs/text", headers=cust, json={"text_content": "Gửi mẹ"}).status_code == 200
    r = client.post(f"{API}/orders/{oid3}{SK}/generate", headers=cust)
    assert r.status_code == 422 and _err(r) == "AI_TYPE_UNSUPPORTED"
