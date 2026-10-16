"""ORM mapping for sketches, quotations and order messages (existing tables; schema owned by SQL migrations).

quotations.adjustment_pct and final_total are GENERATED columns: never set them, only read.
Quotation status transitions have no DB guard; QuotationService enforces them.
"""
import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (BigInteger, Boolean, Date, DateTime, Enum, FetchedValue, ForeignKey, Integer, Numeric,
                        SmallInteger, String, Text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.order import ComplexityLevel


class QuotationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    SENT = "SENT"
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class AdjustmentStatus(str, enum.Enum):
    NONE = "NONE"
    WITHIN_THRESHOLD = "WITHIN_THRESHOLD"
    PENDING_MANAGER = "PENDING_MANAGER"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Sketch(Base):
    __tablename__ = "sketches"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    version: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    trajectory_uri: Mapped[str] = mapped_column(Text)          # storage object path of the trajectory JSON
    preview_url: Mapped[str | None] = mapped_column(Text)      # storage object path of page 1 preview
    similarity_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    suggested_complexity: Mapped[ComplexityLevel | None] = mapped_column(
        Enum(ComplexityLevel, name="complexity_level", create_type=False))
    estimated_writing_sec: Mapped[int | None] = mapped_column(Integer)
    total_stroke_mm: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pen_lift_count: Mapped[int | None] = mapped_column(Integer)
    approach_note: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class Quotation(Base):
    __tablename__ = "quotations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    version: Mapped[int] = mapped_column(Integer)
    sketch_id: Mapped[int] = mapped_column(ForeignKey("sketches.id"))
    pricing_config_id: Mapped[int] = mapped_column(ForeignKey("pricing_configs.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    status: Mapped[QuotationStatus] = mapped_column(
        Enum(QuotationStatus, name="quotation_status", create_type=False), default=QuotationStatus.DRAFT)
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    chosen_option: Mapped[int | None] = mapped_column(SmallInteger)
    char_count: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    complexity: Mapped[ComplexityLevel] = mapped_column(Enum(ComplexityLevel, name="complexity_level", create_type=False))
    computed_total: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    adjusted_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 0))
    adjustment_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), server_default=FetchedValue(),
                                                           server_onupdate=FetchedValue())
    adjustment_reason: Mapped[str | None] = mapped_column(Text)
    adjustment_status: Mapped[AdjustmentStatus] = mapped_column(
        Enum(AdjustmentStatus, name="adjustment_status", create_type=False), default=AdjustmentStatus.NONE)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_total: Mapped[Decimal] = mapped_column(Numeric(14, 0), server_default=FetchedValue(),
                                                 server_onupdate=FetchedValue())
    min_deposit_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    price_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    eta: Mapped[date | None] = mapped_column(Date)
    file_url: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    sender_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    body: Mapped[str | None] = mapped_column(Text)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
