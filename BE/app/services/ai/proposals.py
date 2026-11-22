"""Proposals of the order assistant (migration 0029, owner request 2026-11-22).

The assistant helps the customer through the whole Create Order flow, but the order changes only when the customer agrees:

* During one turn the assistant's tools work on the real order as before (so the model sees the result of its own calls:
  change the text, draw the sketch again, check the price). When the turn ends, the order state after the turn is stored as a
  PROPOSAL and the order is put back exactly as it was before the turn (form, sketch cursor, price). `last_saved_at` moves
  like on any write to a DRAFT order (trigger fn_order_state_guard, 0002).
* The sketch revisions the turn made stay in the history (author AI / ENGINE, parent = the revision shown before), but are
  kept out of redo while their proposal is not applied, so a redo never applies a proposal behind the customer's back.
* Applying writes the proposed state onto the order (the price is computed again). It is allowed only while the order is in
  the state the proposal was made on (`base_state_hash`); otherwise `409 PROPOSAL_STALE` and nothing changes. Applying one
  proposal makes the other pending ones stale (they were made on the state before).
* A turn may continue a pending proposal (`base_proposal_id`, by default the latest applicable one): the proposal is applied
  for the turn only, so "và đổi mực xanh" adds to the earlier proposal instead of starting over; the new proposal contains
  both and is made on the same order state.
* A failed turn (every provider failed) leaves the order as it was and makes no proposal.

State = what the customer edits on the order: text input (text, template, style, size, alignment, layout), materials, quantity,
options, restoration mode, and the sketch cursor. The canvas and the images are hashed (they are not tools of the assistant,
but the customer changing them makes a proposal stale) and never written back. Price, character count and last saved time
are derived and not part of the hash (last saved time is set by the DB trigger on every write of a DRAFT).
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text as sql
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.models.account import Account
from app.models.order import Order, OrderInput, OrderInputKind
from app.models.sketch import SketchRevision
from app.models.studio import AiProposal
from app.repositories.catalog import CatalogRepository
from app.repositories.orders import OrderRepository
from app.services import audit

STATE_VERSION = 1
ORDER_FIELDS = ("order_type", "paper_type_id", "pen_type_id", "ink_color_id", "quantity", "customer_note", "restoration_mode",
                "physical_watermark", "workshop_suggest_materials", "current_sketch_revision_id")
WRITABLE_FIELDS = tuple(f for f in ORDER_FIELDS if f != "order_type")      # the assistant has no tool that changes the type
TEXT_FIELDS = ("text_content", "template_id", "handwriting_style_id", "font_size_mm", "alignment", "layout")
DERIVED_FIELDS = ("char_count", "estimated_price_min", "estimated_price_max", "last_saved_at")


# ---------------------------------------------------------------------------------------------------------- state
def _plain(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "value"):
        return v.value
    return v


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def capture(session: Session, order: Order) -> dict[str, Any]:
    """The order state a proposal is made on / proposes (JSON)."""
    text = canvas = None
    images = []
    for r in OrderRepository(session).inputs(order.id):
        if r.kind == OrderInputKind.TEXT_CONTENT:
            text = {k: _plain(getattr(r, k)) for k in TEXT_FIELDS}
            if text["text_content"] is not None:
                text["text_content"] = unicodedata.normalize("NFC", text["text_content"])
        elif r.kind == OrderInputKind.CANVAS:
            canvas = _sha(r.canvas_data)
        elif r.kind == OrderInputKind.ORIGINAL_IMAGE:
            images.append([r.id, r.file_url, r.rotation_deg, r.crop_box])
    return {"version": STATE_VERSION, "order": {k: _plain(getattr(order, k)) for k in ORDER_FIELDS}, "text": text,
            "canvas_sha256": canvas, "images": images,
            "derived": {k: _plain(getattr(order, k)) for k in DERIVED_FIELDS}}


def state_hash(state: dict[str, Any]) -> str:
    return _sha({k: v for k, v in state.items() if k != "derived"})


def restore(session: Session, customer: Account, order: Order, state: dict[str, Any], *, exact: bool) -> None:
    """Write `state` onto the order. `exact`: also the stored price / character count (putting the order back after a turn);
    otherwise the price is computed again (applying a proposal)."""
    set_actor(session, customer.id)
    for k in WRITABLE_FIELDS:
        setattr(order, k, state["order"][k])
    repo = OrderRepository(session)
    row = next((r for r in repo.inputs(order.id) if r.kind == OrderInputKind.TEXT_CONTENT), None)
    want = state["text"]
    if want is None:
        if row is not None:
            repo.delete_input(row)
    else:
        fields = {**want, "font_size_mm": Decimal(want["font_size_mm"]) if want.get("font_size_mm") is not None else None}
        if row is None:
            repo.add_input(OrderInput(order_id=order.id, kind=OrderInputKind.TEXT_CONTENT, **fields))
        else:
            for k, v in fields.items():
                setattr(row, k, v)
    session.flush()
    if exact:
        d = state["derived"]
        order.char_count = d["char_count"]
        order.estimated_price_min = Decimal(d["estimated_price_min"]) if d["estimated_price_min"] is not None else None
        order.estimated_price_max = Decimal(d["estimated_price_max"]) if d["estimated_price_max"] is not None else None
        session.flush()
    else:
        from app.services.orders import OrderService
        OrderService(session, customer)._touch_and_price(order)


def max_revision_seq(session: Session, order_id: int) -> int:
    return session.scalar(select(func.max(SketchRevision.seq)).where(SketchRevision.order_id == order_id)) or 0


def revisions_since(session: Session, order_id: int, seq: int) -> list[int]:
    return list(session.scalars(select(SketchRevision.id).where(SketchRevision.order_id == order_id, SketchRevision.seq > seq)
                                .order_by(SketchRevision.seq)))


def hidden_revision_ids(session: Session, order_id: int) -> set[int]:
    """Revisions only reachable through proposals that are not applied (kept out of redo)."""
    rows = session.execute(sql(
        "SELECT unnest(sketch_revision_ids) FROM ai_proposals WHERE order_id = :o AND status <> 'APPLIED' "
        "EXCEPT SELECT unnest(sketch_revision_ids) FROM ai_proposals WHERE order_id = :o AND status = 'APPLIED'"),
        {"o": order_id}).scalars()
    return set(rows)


def revision_proposals(session: Session, order_id: int) -> dict[int, AiProposal]:
    """Each revision -> the first proposal that relies on it (for the revision list)."""
    out: dict[int, AiProposal] = {}
    for p in session.scalars(select(AiProposal).where(AiProposal.order_id == order_id).order_by(AiProposal.id)):
        for rid in p.sketch_revision_ids or []:
            out.setdefault(rid, p)
    return out


# ---------------------------------------------------------------------------------------------------------- diff
def _names(catalog: CatalogRepository, field: str, value: Any) -> Any:
    if value is None:
        return None
    get = {"paper_type_id": catalog.paper, "pen_type_id": catalog.pen, "ink_color_id": catalog.ink,
           "template_id": catalog.template}.get(field)
    if get is None:
        return value
    obj = get(value)
    return {"id": value, "name": obj.name if obj else None}


def diff(session: Session, before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """What a proposal changes, in the order of the Create Order steps (content, materials, options, sketch)."""
    catalog = CatalogRepository(session)
    out: list[dict[str, Any]] = []
    bt, at = before["text"] or {}, after["text"] or {}
    for k, name in (("text_content", "text"), ("template_id", "template_id"), ("handwriting_style_id", "handwriting_style_id"),
                    ("font_size_mm", "font_size_mm"), ("alignment", "alignment"), ("layout", "layout")):
        if bt.get(k) != at.get(k):
            out.append({"field": name, "before": _names(catalog, k, bt.get(k)), "after": _names(catalog, k, at.get(k))})
    bo, ao = before["order"], after["order"]
    for k in ("paper_type_id", "pen_type_id", "ink_color_id", "workshop_suggest_materials", "quantity", "physical_watermark",
              "restoration_mode", "customer_note"):
        if bo[k] != ao[k]:
            out.append({"field": k, "before": _names(catalog, k, bo[k]), "after": _names(catalog, k, ao[k])})
    if bo["current_sketch_revision_id"] != ao["current_sketch_revision_id"]:
        out.append({"field": "sketch", "before": bo["current_sketch_revision_id"], "after": ao["current_sketch_revision_id"]})
    return out


def _estimate(state: dict[str, Any]) -> dict[str, Any] | None:
    d = state["derived"]
    if d["estimated_price_min"] is None:
        return None
    return {"price_min": int(Decimal(d["estimated_price_min"])),
            "price_max": int(Decimal(d["estimated_price_max"] or d["estimated_price_min"])), "currency": "VND",
            "is_estimate": True}


# ---------------------------------------------------------------------------------------------------------- service
class ProposalService:
    def __init__(self, session: Session, customer: Account, ip: str | None = None):
        self.session, self.customer, self.ip = session, customer, ip

    def _order(self, order_id: int, *, write: bool = False) -> Order:
        from app.services.sketch_work import SketchWorkService
        return SketchWorkService(self.session, self.customer, None).order(order_id, write=write)

    def get(self, order_id: int, proposal_id: int) -> AiProposal:
        p = self.session.get(AiProposal, proposal_id)
        if p is None or p.order_id != order_id:
            raise AppError(404, "PROPOSAL_NOT_FOUND", "Không tìm thấy đề xuất của trợ lý.")
        return p

    def of_order(self, order_id: int) -> list[AiProposal]:
        return list(self.session.scalars(select(AiProposal).where(AiProposal.order_id == order_id).order_by(AiProposal.id)))

    def of_messages(self, message_ids: list[int]) -> dict[int, AiProposal]:
        if not message_ids:
            return {}
        return {p.message_id: p for p in self.session.scalars(select(AiProposal).where(AiProposal.message_id.in_(message_ids)))}

    def current_hash(self, order: Order) -> str:
        return state_hash(capture(self.session, order))

    def applicability(self, order: Order, p: AiProposal, now_hash: str | None = None) -> tuple[bool, str | None]:
        """(can be applied now, why not: APPLIED | REJECTED | ORDER_NOT_EDITABLE | ORDER_CHANGED)."""
        from app.services.orders import EDITABLE
        if p.status != "PENDING":
            return False, p.status
        if order.order_status not in EDITABLE:
            return False, "ORDER_NOT_EDITABLE"
        if (now_hash or self.current_hash(order)) != p.base_state_hash:
            return False, "ORDER_CHANGED"
        return True, None

    def latest_applicable(self, order: Order, session_id: int) -> AiProposal | None:
        now = self.current_hash(order)
        for p in reversed(list(self.session.scalars(select(AiProposal).where(
                AiProposal.session_id == session_id, AiProposal.status == "PENDING").order_by(AiProposal.id)))):
            if p.base_state_hash == now:
                return p
        return None

    def create(self, order: Order, *, session_id: int, message_id: int, before: dict[str, Any], after: dict[str, Any],
               new_revision_ids: list[int], parent: AiProposal | None) -> AiProposal | None:
        """Store the proposal of one turn (None when the turn changed nothing compared with what it started from)."""
        start = parent.after_state if parent is not None else before
        if state_hash(after) == state_hash(start):
            return None
        cursor = after["order"]["current_sketch_revision_id"]
        rev_ids = list(dict.fromkeys([*(parent.sketch_revision_ids if parent else []), *new_revision_ids]))
        p = AiProposal(order_id=order.id, session_id=session_id, message_id=message_id,
                       parent_proposal_id=parent.id if parent else None, status="PENDING",
                       base_state_hash=state_hash(before), before_state=before, after_state=after,
                       changes=diff(self.session, before, after), estimate=_estimate(after),
                       sketch_revision_id=cursor if cursor != before["order"]["current_sketch_revision_id"] else None,
                       sketch_revision_ids=rev_ids)
        self.session.add(p)
        self.session.flush()
        return p

    def apply(self, order_id: int, proposal_id: int) -> tuple[AiProposal, Order]:
        from app.services.ai.assistant import AssistantService
        AssistantService(self.session, self.customer, None).lock_order(order_id)   # not while a turn of this order runs
        order = self._order(order_id, write=True)                                   # owner + editable, row locked
        p = self.get(order_id, proposal_id)
        if p.status == "APPLIED":                                                   # a second click: same answer
            return p, order
        if p.status == "REJECTED":
            raise AppError(409, "PROPOSAL_NOT_PENDING", "Đề xuất này đã bị bỏ qua; hãy nhắn trợ lý để đề xuất lại.")
        ok, why = self.applicability(order, p)
        if not ok:
            raise AppError(409, "PROPOSAL_STALE",
                           "Đơn đã thay đổi sau khi trợ lý đề xuất; hãy nhắn trợ lý để đề xuất lại trên đơn hiện tại.",
                           {"reason": why})
        self._check_still_valid(order, p.after_state)
        restore(self.session, self.customer, order, p.after_state, exact=False)
        p.status, p.decided_at = "APPLIED", datetime.now(timezone.utc)
        self.session.flush()
        audit.record(self.session, actor_id=self.customer.id, action="AI_PROPOSAL_APPLIED", entity_type="order",
                     entity_id=order.id, new={"proposal_id": p.id, "fields": [c["field"] for c in p.changes or []],
                                              "sketch_revision_id": p.sketch_revision_id}, ip=self.ip)
        return p, order

    def reject(self, order_id: int, proposal_id: int) -> AiProposal:
        self._order(order_id)
        p = self.get(order_id, proposal_id)
        if p.status == "REJECTED":
            return p
        if p.status == "APPLIED":
            raise AppError(409, "PROPOSAL_NOT_PENDING", "Đề xuất đã được áp dụng; dùng Hoàn tác hoặc sửa đơn để đổi lại.")
        p.status, p.decided_at = "REJECTED", datetime.now(timezone.utc)
        self.session.flush()
        audit.record(self.session, actor_id=self.customer.id, action="AI_PROPOSAL_REJECTED", entity_type="order",
                     entity_id=order_id, new={"proposal_id": p.id}, ip=self.ip)
        return p

    def _check_still_valid(self, order: Order, state: dict[str, Any]) -> None:
        """Materials / template deactivated since the proposal was made: refuse instead of writing an invalid order."""
        catalog = CatalogRepository(self.session)
        o = state["order"]
        for field, get in (("paper_type_id", catalog.paper), ("pen_type_id", catalog.pen), ("ink_color_id", catalog.ink)):
            if o[field] is not None:
                obj = get(o[field])
                if obj is None or not obj.is_active:
                    raise AppError(409, "PROPOSAL_STALE", "Vật tư trong đề xuất đã ngừng cung cấp; hãy nhắn trợ lý để chọn lại.",
                                   {"reason": "MATERIAL_UNAVAILABLE", "field": field})
        t = state["text"]
        if t and t.get("template_id") is not None:
            tpl = catalog.template(t["template_id"])
            if tpl is None or not getattr(tpl, "is_active", True):
                raise AppError(409, "PROPOSAL_STALE", "Mẫu chữ trong đề xuất đã ngừng dùng; hãy nhắn trợ lý để chọn lại.",
                               {"reason": "TEMPLATE_UNAVAILABLE"})
        rid = o["current_sketch_revision_id"]
        if rid is not None:
            rev = self.session.get(SketchRevision, rid)
            if rev is None or rev.order_id != order.id:
                raise AppError(409, "PROPOSAL_STALE", "Phác thảo của đề xuất không còn; hãy nhắn trợ lý để đề xuất lại.",
                               {"reason": "REVISION_MISSING"})
