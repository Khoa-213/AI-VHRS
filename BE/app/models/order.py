"""ORM mapping for orders and their inputs (existing tables; schema owned by SQL migrations).

order_status / production_status transitions are enforced by DB triggers (fn_order_state_guard);
services only issue UPDATEs and let the DB reject illegal ones (SQLSTATE P0409 -> 409).
"""
import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, SmallInteger, String,
                        Text)
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OrderType(str, enum.Enum):
    OT1_COPY_RESTORE = "OT1_COPY_RESTORE"
    OT2_LEARNED_STYLE = "OT2_LEARNED_STYLE"
    OT3_TEMPLATE = "OT3_TEMPLATE"


class OrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    NEED_INFO = "NEED_INFO"
    REJECTED = "REJECTED"
    ACCEPTED = "ACCEPTED"
    AWAITING_PRIVACY = "AWAITING_PRIVACY"
    QUOTED = "QUOTED"
    AWAITING_DEPOSIT = "AWAITING_DEPOSIT"
    CONFIRMED = "CONFIRMED"
    AWAITING_ACCEPTANCE = "AWAITING_ACCEPTANCE"
    AWAITING_FINAL_PAYMENT = "AWAITING_FINAL_PAYMENT"
    READY_TO_DELIVER = "READY_TO_DELIVER"
    DELIVERING = "DELIVERING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ProductionStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    PENDING_SCHEDULE = "PENDING_SCHEDULE"
    SCHEDULED = "SCHEDULED"
    PREPARING = "PREPARING"
    WRITING = "WRITING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    WRITTEN = "WRITTEN"
    PHOTO_UPLOADED = "PHOTO_UPLOADED"
    REWRITE_REQUIRED = "REWRITE_REQUIRED"
    FINISHED = "FINISHED"


class OrderInputKind(str, enum.Enum):
    ORIGINAL_IMAGE = "ORIGINAL_IMAGE"
    HANDWRITING_SAMPLE = "HANDWRITING_SAMPLE"
    TEXT_CONTENT = "TEXT_CONTENT"
    CANVAS = "CANVAS"


class StyleStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DELETED = "DELETED"


class DeliveryMethod(str, enum.Enum):
    DELIVERY = "DELIVERY"
    PICKUP = "PICKUP"


class ComplexityLevel(str, enum.Enum):
    SIMPLE = "SIMPLE"
    MEDIUM = "MEDIUM"
    COMPLEX = "COMPLEX"


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(20))
    customer_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType, name="order_type", create_type=False))
    order_status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", create_type=False), default=OrderStatus.DRAFT)
    production_status: Mapped[ProductionStatus] = mapped_column(
        Enum(ProductionStatus, name="production_status", create_type=False), default=ProductionStatus.NOT_STARTED)
    paper_type_id: Mapped[int | None] = mapped_column(ForeignKey("paper_types.id"))
    pen_type_id: Mapped[int | None] = mapped_column(ForeignKey("pen_types.id"))
    ink_color_id: Mapped[int | None] = mapped_column(BigInteger)
    workshop_suggest_materials: Mapped[bool] = mapped_column(Boolean, default=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    char_count: Mapped[int | None] = mapped_column(Integer)
    complexity: Mapped[ComplexityLevel | None] = mapped_column(
        Enum(ComplexityLevel, name="complexity_level", create_type=False))
    estimated_price_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 0))
    estimated_price_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 0))
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 0))       # G of the approved quotation
    deposit_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    deposit_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 0))     # D
    customer_note: Mapped[str | None] = mapped_column(Text)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_staff_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    reject_reason: Mapped[str | None] = mapped_column(ENUM(
        "TOO_OLD", "DAMAGED", "MISSING_CONTENT", "PROHIBITED_CONTENT", "OTHER", name="reject_reason",
        create_type=False))
    reject_note: Mapped[str | None] = mapped_column(Text)
    info_request_note: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    privacy_policy_version: Mapped[str | None] = mapped_column(String(20))
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    privacy_declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eta: Mapped[date | None] = mapped_column(Date)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Acceptance (FR-28, BR-13). awaiting_acceptance_at is set by the DB trigger when the order reaches AWAITING_ACCEPTANCE.
    awaiting_acceptance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_product_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    free_rewrite_used: Mapped[bool] = mapped_column(Boolean, default=False)
    # Delivery (Phase 4c, FR-21..23). For PICKUP, delivery_address holds only the contact {receiver, phone}.
    delivery_method: Mapped[DeliveryMethod | None] = mapped_column(
        Enum(DeliveryMethod, name="delivery_method", create_type=False))
    delivery_address: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    pickup_slot_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pickup_slot_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The carrier service the customer chose for DELIVERY (Phase 4c-2b); all NULL for PICKUP.
    shipping_carrier: Mapped[str | None] = mapped_column(ENUM("GHN", "GHTK", name="carrier", create_type=False))
    shipping_service_code: Mapped[str | None] = mapped_column(String(30))
    shipping_eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class HandwritingStyle(Base):
    __tablename__ = "handwriting_styles"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    name: Mapped[str] = mapped_column(String(150))
    status: Mapped[StyleStatus] = mapped_column(Enum(StyleStatus, name="style_status", create_type=False))
    glyph_set_uri: Mapped[str | None] = mapped_column(Text)
    coverage_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    right_to_use_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    keep_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class OrderInput(Base):
    __tablename__ = "order_inputs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    kind: Mapped[OrderInputKind] = mapped_column(Enum(OrderInputKind, name="order_input_kind", create_type=False))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    file_url: Mapped[str | None] = mapped_column(Text)   # storage object path, not a public URL
    mime_type: Mapped[str | None] = mapped_column(String(50))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    rotation_deg: Mapped[int | None] = mapped_column(SmallInteger, default=0)
    crop_box: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    quality_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_quality_warning: Mapped[bool] = mapped_column(Boolean, default=False)
    text_content: Mapped[str | None] = mapped_column(Text)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id"))
    handwriting_style_id: Mapped[int | None] = mapped_column(ForeignKey("handwriting_styles.id"))
    font_size_mm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    alignment: Mapped[str | None] = mapped_column(String(10))
    layout: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    canvas_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
