"""Data access for sketches, quotations and messages. No business rules."""
from __future__ import annotations  # methods named `list` would otherwise shadow the builtin in later annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.models.sketch import AdjustmentStatus, Message, Quotation, QuotationStatus, Sketch

LIVE_QUOTATION = (QuotationStatus.DRAFT, QuotationStatus.PENDING_APPROVAL, QuotationStatus.SENT)


class SketchRepository:
    def __init__(self, session: Session):
        self.s = session

    def next_version(self, order_id: int) -> int:
        return (self.s.scalar(select(func.max(Sketch.version)).where(Sketch.order_id == order_id)) or 0) + 1

    def add(self, row: Sketch) -> Sketch:
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def list(self, order_id: int) -> list[Sketch]:
        return list(self.s.scalars(select(Sketch).where(Sketch.order_id == order_id).order_by(Sketch.version.desc())))

    def get(self, order_id: int, version: int) -> Sketch | None:
        return self.s.scalar(select(Sketch).where(Sketch.order_id == order_id, Sketch.version == version))

    def get_by_id(self, sketch_id: int) -> Sketch | None:
        return self.s.get(Sketch, sketch_id)

    def final(self, order_id: int) -> Sketch | None:
        return self.s.scalar(select(Sketch).where(Sketch.order_id == order_id, Sketch.is_final))

    def clear_final(self, order_id: int) -> None:
        self.s.execute(update(Sketch).where(Sketch.order_id == order_id, Sketch.is_final).values(is_final=False))


class QuotationRepository:
    def __init__(self, session: Session):
        self.s = session

    def next_version(self, order_id: int) -> int:
        return (self.s.scalar(select(func.max(Quotation.version)).where(Quotation.order_id == order_id)) or 0) + 1

    def add(self, row: Quotation) -> Quotation:
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def get(self, quotation_id: int, *, lock: bool = False) -> Quotation | None:
        stmt = select(Quotation).where(Quotation.id == quotation_id)
        return self.s.scalar(stmt.with_for_update() if lock else stmt)

    def list(self, order_id: int) -> list[Quotation]:
        return list(self.s.scalars(select(Quotation).where(Quotation.order_id == order_id)
                                   .order_by(Quotation.version.desc())))

    def live(self, order_id: int) -> Quotation | None:
        return self.s.scalar(select(Quotation).where(Quotation.order_id == order_id,
                                                     Quotation.status.in_(LIVE_QUOTATION)))

    def latest(self, order_id: int, statuses: tuple[QuotationStatus, ...]) -> Quotation | None:
        return self.s.scalar(select(Quotation).where(Quotation.order_id == order_id, Quotation.status.in_(statuses))
                             .order_by(Quotation.version.desc()).limit(1))

    def supersede_open_changes(self, order_id: int) -> None:
        self.s.execute(update(Quotation).where(Quotation.order_id == order_id,
                                               Quotation.status == QuotationStatus.CHANGES_REQUESTED)
                       .values(status=QuotationStatus.SUPERSEDED))

    def pending_approval(self, *, offset: int, limit: int) -> tuple[list[Quotation], int]:
        stmt = select(Quotation).where(Quotation.adjustment_status == AdjustmentStatus.PENDING_MANAGER,
                                       Quotation.status == QuotationStatus.PENDING_APPROVAL)
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        return list(self.s.scalars(stmt.order_by(Quotation.created_at).offset(offset).limit(limit))), total

    def overdue(self, now: datetime) -> list[Quotation]:
        return list(self.s.scalars(select(Quotation).where(Quotation.status == QuotationStatus.SENT,
                                                           Quotation.valid_until < now).with_for_update()))


class MessageRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, row: Message) -> Message:
        self.s.add(row)
        self.s.flush()
        self.s.refresh(row)
        return row

    def list(self, order_id: int, *, offset: int, limit: int) -> tuple[list[Message], int]:
        stmt = select(Message).where(Message.order_id == order_id)
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        return list(self.s.scalars(stmt.order_by(Message.created_at, Message.id).offset(offset).limit(limit))), total

    def unread_count(self, order_id: int, reader_id: int) -> int:
        return self.s.scalar(select(func.count()).where(Message.order_id == order_id, Message.sender_id != reader_id,
                                                        Message.read_at.is_(None))) or 0

    def mark_read(self, order_id: int, reader_id: int, now: datetime) -> int:
        res = self.s.execute(update(Message).where(Message.order_id == order_id, Message.sender_id != reader_id,
                                                   Message.read_at.is_(None)).values(read_at=now))
        return res.rowcount

    def recent_card(self, order_id: int, since: datetime) -> Message | None:
        """The newest order card of this order created at or after `since` (anti-spam: one card per window)."""
        return self.s.scalars(select(Message).where(Message.order_id == order_id, Message.kind == "ORDER_CARD",
                                                    Message.created_at >= since)
                              .order_by(Message.created_at.desc(), Message.id.desc()).limit(1)).first()


# Which orders each role may see in the chat lists: the same rule as WorkshopAccess (a Manager sees every non-draft order, a
# Staff the orders assigned to them plus the unclaimed SUBMITTED pool, a customer their own non-draft orders).
_SCOPE = {
    "CUSTOMER": "o.customer_id = :me AND o.order_status <> 'DRAFT'",
    "MANAGER": "o.order_status <> 'DRAFT'",
    "STAFF": "o.order_status <> 'DRAFT' AND (o.assigned_staff_id = :me OR (o.assigned_staff_id IS NULL AND o.order_status = 'SUBMITTED'))",
}


class ConversationRepository:
    """The chat lists in two queries (a count and one page), never one query per order."""

    def __init__(self, session: Session):
        self.s = session

    def page(self, role: str, me: int, *, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        scope = _SCOPE[role]
        total = self.s.execute(text(f"SELECT count(*) FROM orders o WHERE {scope} "
                                    "AND EXISTS (SELECT 1 FROM messages m WHERE m.order_id = o.id)"), {"me": me}).scalar() or 0
        rows = self.s.execute(text(f"""
            SELECT o.id AS order_id, o.code, o.order_type::text AS order_type, o.order_status::text AS order_status,
                   a.full_name AS customer_name,
                   l.body AS last_body, l.kind AS last_kind, (jsonb_array_length(l.attachments) > 0) AS last_has_attachment,
                   l.created_at AS last_created_at, (l.sender_id = :me) AS last_mine, COALESCE(u.unread, 0) AS unread
            FROM orders o
            JOIN accounts a ON a.id = o.customer_id
            JOIN LATERAL (SELECT m.body, m.kind, m.attachments, m.created_at, m.sender_id, m.id
                          FROM messages m WHERE m.order_id = o.id ORDER BY m.created_at DESC, m.id DESC LIMIT 1) l ON true
            LEFT JOIN LATERAL (SELECT count(*) AS unread FROM messages m
                               WHERE m.order_id = o.id AND m.sender_id <> :me AND m.read_at IS NULL) u ON true
            WHERE {scope}
            ORDER BY l.created_at DESC, l.id DESC, o.id DESC
            OFFSET :off LIMIT :lim"""), {"me": me, "off": offset, "lim": limit}).mappings().all()
        return [dict(r) for r in rows], int(total)

    def unread_total(self, role: str, me: int) -> int:
        return int(self.s.execute(text(f"""
            SELECT count(*) FROM messages m JOIN orders o ON o.id = m.order_id
            WHERE {_SCOPE[role]} AND m.sender_id <> :me AND m.read_at IS NULL"""), {"me": me}).scalar() or 0)

