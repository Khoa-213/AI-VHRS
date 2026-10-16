"""Data access for sketches, quotations and messages. No business rules."""
from __future__ import annotations  # methods named `list` would otherwise shadow the builtin in later annotations

from datetime import datetime

from sqlalchemy import func, select, update
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
