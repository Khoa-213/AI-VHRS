"""Unified sketch, first step: the studio preview and the Staff's official sketch of the same content are the same strokes.

Before, the studio drew OT-3 with seed = draft.id and the workshop with seed = order.id, and the studio placed text without the
order's canonical layout (vertical MIDDLE), so the customer approved one drawing and the Staff received another."""
import json

import pytest

from app.db.session import _factory
from app.models.account import Account
from app.models.studio import StudioDraft
from app.services.stroke_ai import engine
from app.services.stroke_ai import trajectory as tj
from app.services.studio import StudioService
from tests.test_api_workshop import W, cust, staff, store, wcat  # noqa: F401
from tests.test_u5_studio import S, _new


def _geometry(pages):
    return [[(s.kind, [(round(x, 2), round(y, 2)) for x, y in s.points]) for s in p.strokes if s.kind != "watermark"]
            for p in pages]


def _studio_pages(draft_id, store):
    with _factory()() as session:
        draft = session.get(StudioDraft, draft_id)
        svc = StudioService(session, session.get(Account, draft.customer_id), store)
        return svc.generate(draft, svc.content(draft), 0).pages


@pytest.mark.parametrize("extra", [
    {"alignment": "LEFT"},                                                        # plain text, top-left wording
    {"alignment": None},                                                          # no choice: the default alignment
    {"alignment": "CENTER", "layout": {"spans": [{"start": 0, "end": 4, "size_mm": 12}]}},   # a styled part
])
def test_the_staff_sketch_is_the_studio_preview(client, cust, staff, wcat, store, extra):
    sh, _ = staff
    d = _new(client, cust)
    body = {"text": "Kính gửi quý khách\nhẹn gặp lại", "template_id": wcat["tpl"], "font_size_mm": 8,
            "paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"], **extra}
    r = client.patch(f"{S}/{d['id']}", headers=cust, json=body)
    assert r.status_code == 200, r.text
    preview = _geometry(_studio_pages(d["id"], store))
    assert preview and preview[0]

    r = client.post(f"{S}/{d['id']}/submit", headers=cust, json={"terms_accepted": True})
    assert r.status_code == 200, r.text
    oid = r.json()["order_id"]
    assert client.post(f"{W}/orders/{oid}/accept", headers=sh, json={}).status_code == 200
    r = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})
    assert r.status_code == 201, r.text
    s = r.json()
    det = client.get(f"{W}/orders/{oid}/sketches/{s['version']}", headers=sh).json()
    assert det["trajectory"]["engine"]["seed_source"] == "content"
    official = _geometry(tj.parse(det["trajectory"]))
    assert official == preview                                   # same strokes, same order, same place


def test_the_seed_follows_the_content_and_an_explicit_seed_is_a_variant():
    base = dict(font_uri="hershey://futural", font_size_mm=8.0, alignment="LEFT", paper_size="A4", layout=None)
    a = engine.content_seed("Xin chào", None, **base)
    assert a == engine.content_seed("Xin chào", None, **base)
    assert a == engine.content_seed("Xin chào", None, **base)          # NFC: the same text typed another way
    assert a != engine.content_seed("Xin chào!", None, **base)
    assert a != engine.content_seed("Xin chào", None, **{**base, "font_size_mm": 9.0})
    assert 0 <= a < 2 ** 31
