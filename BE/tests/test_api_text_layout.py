"""FR-08 on the real database: sizes and styles of parts of the text, from the order's text input to the sketch and the preview."""
import unicodedata

from tests.test_api_orders import API, _sql
from tests.test_api_workshop import W, _accepted, _ot3, cust, policy, staff, store, wcat  # noqa: F401

O = f"{API}/orders"
TEXT = "Chúc mừng năm mới"


def _put(client, cust, oid, layout=..., text=TEXT, size=8, expect=200, **extra):
    body = {"text_content": text, "template_id": _put.tpl, "font_size_mm": size, "alignment": "LEFT", **extra}
    if layout is not ...:
        body["layout"] = layout
    r = client.put(f"{O}/{oid}/inputs/text", headers=cust, json=body)
    assert r.status_code == expect, r.text
    return r


def _span(sub, text=TEXT, **kw):
    i = text.index(sub)
    return {"start": i, "end": i + len(sub), **kw}


def _draft(client, cust, wcat):
    _put.tpl = wcat["tpl"]
    return _ot3(client, cust, wcat, text_=TEXT, submit=False)


def test_the_layout_is_checked_stored_in_canonical_form_and_replaced_by_every_put(client, cust, wcat):
    oid = _draft(client, cust, wcat)
    layout = {"version": 1, "line_spacing": 1.5, "spans": [_span("mới", underline="double", italic=False),
                                                           _span("Chúc", size_mm=12, italic=True)]}
    r = _put(client, cust, oid, layout).json()
    assert r["layout"] == {"version": 1, "line_spacing": 1.5, "spans": [
        {"start": 0, "end": 4, "size_mm": 12.0, "italic": True}, {"start": 14, "end": 17, "underline": "double"}]}
    shown = client.get(f"{O}/{oid}", headers=cust).json()
    assert next(i for i in shown["inputs"] if i["kind"] == "TEXT_CONTENT")["layout"] == r["layout"]
    assert _sql("select layout->>'line_spacing' from order_inputs where order_id=:o and kind='TEXT_CONTENT'", o=oid) == "1.5"

    assert _put(client, cust, oid).json()["layout"] is None                         # a PUT without layout clears it
    assert _put(client, cust, oid, {"version": 1, "spans": []}).json()["layout"] is None   # a plain layout is not stored

    # offsets index the NFC text that is stored, even if the client typed it decomposed
    nfd = unicodedata.normalize("NFD", TEXT)
    assert len(nfd) > len(TEXT)
    r = _put(client, cust, oid, {"spans": [_span("mới", underline="single")]}, text=nfd).json()
    assert r["text_content"] == TEXT and r["layout"]["spans"] == [{"start": 14, "end": 17, "underline": "single"}]
    _put(client, cust, oid, {"spans": [{"start": 0, "end": len(nfd), "italic": True}]}, text=nfd, expect=422)   # past the NFC end

    for bad in ({"spans": [{"start": 0, "end": 99, "italic": True}]},                         # past the end
                {"spans": [{"start": 0, "end": 3, "bold": True}]},                            # there is no bold
                {"spans": [{"start": 0, "end": 5, "italic": True}, {"start": 4, "end": 8, "strike": True}]},
                {"spans": [{"start": 0, "end": 3, "size_mm": 3}]}, {"line_spacing": 9}, {"version": 3}, {"colour": "red"}):
        r = _put(client, cust, oid, bad, expect=422)
        assert r.json()["error"]["code"] == "INVALID_LAYOUT", bad
    assert _put(client, cust, oid, {"spans": [_span("mừng", size_mm=4)]}).status_code == 200   # 4 mm is the floor
    assert _put(client, cust, oid, size=3.9, expect=422).json()["error"]["code"] == "VALIDATION_ERROR"
    assert _put(client, cust, oid, size=4).status_code == 200


def test_a_styled_order_makes_a_styled_sketch_without_changing_the_complexity(client, cust, staff, store, wcat):
    sh, _ = staff
    _put.tpl = wcat["tpl"]
    plain = _accepted(client, cust, sh, wcat, text_=TEXT)
    styled = _ot3(client, cust, wcat, text_=TEXT, submit=False)
    layout = {"spans": [_span("Chúc", underline="double"), _span("năm", italic=True, size_mm=12), _span("mới", strike=True)]}
    _put(client, cust, styled, layout)
    assert client.post(f"{O}/{styled}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{styled}/accept", headers=sh, json={}).status_code == 200

    a = client.post(f"{W}/orders/{plain}/sketches/generate", headers=sh, json={"seed": 1}).json()
    b = client.post(f"{W}/orders/{styled}/sketches/generate", headers=sh, json={"seed": 1})
    assert b.status_code == 201, b.text
    b = b.json()
    assert b["pen_lift_count"] == a["pen_lift_count"] + 3                                  # an underline, a double underline (2), a strike
    assert b["suggested_complexity"] == a["suggested_complexity"]                          # styles do not move the price class
    detail = client.get(f"{W}/orders/{styled}/sketches/1", headers=sh).json()
    assert detail["trajectory"]["engine"]["layout"] == {"spans": 3, "line_spacing": 1.0}
    assert "layout" not in client.get(f"{W}/orders/{plain}/sketches/1", headers=sh).json()["trajectory"]["engine"]

    # a stale layout (the text no longer reaches its offsets) is refused when a sketch is made, not drawn wrongly
    _sql("update order_inputs set layout = cast(:l as jsonb) where order_id=:o and kind='TEXT_CONTENT' returning 1",
         l='{"version": 1, "spans": [{"start": 0, "end": 400, "italic": true}]}', o=styled)
    r = client.post(f"{W}/orders/{styled}/sketches/generate", headers=sh, json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_LAYOUT"


def test_catalog_text_styles_and_styled_preview(client, wcat):
    caps = client.get(f"{API}/catalog/text-styles")
    assert caps.status_code == 200
    c = caps.json()
    assert c["min_font_size_mm"] == 4.0 and c["bold"] is False and "underline" in c["styles"] and c["max_spans"] == 200

    url = f"{API}/catalog/templates/{wcat['tpl']}/preview"
    plain = client.post(url, json={"text": "Nét Việt"})
    assert plain.status_code == 200 and plain.headers["content-type"] == "image/png" and plain.content[:8] == b"\x89PNG\r\n\x1a\n"
    styled = client.post(url, json={"text": "Nét Việt", "font_size_mm": 12, "alignment": "CENTER",
                                    "layout": {"spans": [{"start": 0, "end": 3, "underline": "single", "italic": True}]}})
    assert styled.status_code == 200 and styled.content != plain.content
    assert client.get(url, params={"text": "Nét Việt"}).status_code == 200                      # the old GET still works
    bad = client.post(url, json={"text": "Nét", "layout": {"spans": [{"start": 0, "end": 99, "italic": True}]}})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_LAYOUT"
    assert client.post(url, json={"text": "Nét", "font_size_mm": 3}).status_code == 422
    assert client.post(url, json={"text": ""}).status_code == 422
    assert client.post(f"{API}/catalog/templates/999999999/preview", json={"text": "x"}).status_code == 404
    assert client.post(f"{API}/catalog/templates/{wcat['tpl_off']}/preview", json={"text": "x"}).status_code == 404   # a switched-off template
