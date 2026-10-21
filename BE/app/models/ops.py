"""ORM mapping for payments, robots and production jobs (existing tables; schema owned by SQL migrations).

Only the columns the web/API side reads or writes are mapped. The robot-facing columns (package, simulation,
progress) belong to the Technical Staff phase.
"""
import enum
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, FetchedValue, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PaymentType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    FINAL = "FINAL"
    SHIPPING = "SHIPPING"
    REFUND = "REFUND"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PaymentGateway(str, enum.Enum):
    VNPAY = "VNPAY"
    MOMO = "MOMO"


class RobotStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    MAINTENANCE = "MAINTENANCE"
    BROKEN = "BROKEN"


class JobStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    PREPARING = "PREPARING"
    WRITING = "WRITING"
    PAUSED = "PAUSED"
    WRITTEN = "WRITTEN"
    PHOTO_UPLOADED = "PHOTO_UPLOADED"
    DONE = "DONE"
    FAILED = "FAILED"
    REWRITE_REQUIRED = "REWRITE_REQUIRED"
    CANCELLED = "CANCELLED"


# Statuses in which a job occupies its robot / technician (mirrors the EXCLUDE constraint ex_job_robot_overlap).
ACTIVE_JOB_STATUSES = (JobStatus.SCHEDULED, JobStatus.PREPARING, JobStatus.WRITING, JobStatus.PAUSED)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    type: Mapped[PaymentType] = mapped_column(Enum(PaymentType, name="payment_type", create_type=False))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    deposit_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    gateway: Mapped[PaymentGateway] = mapped_column(Enum(PaymentGateway, name="payment_gateway", create_type=False))
    gateway_txn_id: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", create_type=False), default=PaymentStatus.PENDING)
    refund_of_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))
    refund_reason: Mapped[str | None] = mapped_column(Text)
    gateway_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue(),
                                                 server_onupdate=FetchedValue())


class Robot(Base):
    __tablename__ = "robots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(30))
    robot_type: Mapped[str] = mapped_column(String(50), default="FAIRINO_FR3")
    station: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[RobotStatus] = mapped_column(
        Enum(RobotStatus, name="robot_status", create_type=False), default=RobotStatus.AVAILABLE)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    supported_pen_categories: Mapped[list[str] | None] = mapped_column(
        ARRAY(ENUM("BALLPOINT", "GEL", "FINELINER", "FOUNTAIN", "BRUSH", "MARKER", name="pen_category",
                   create_type=False)))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue(),
                                                 server_onupdate=FetchedValue())


class ProductionJob(Base):
    __tablename__ = "production_jobs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    sketch_id: Mapped[int] = mapped_column(ForeignKey("sketches.id"))
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id"))
    technician_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    scheduled_by: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status", create_type=False),
                                              default=JobStatus.SCHEDULED)
    is_rewrite: Mapped[bool] = mapped_column(Boolean, default=False)
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estimated_duration_min: Mapped[int] = mapped_column(Integer)
    package_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue(),
                                                 server_onupdate=FetchedValue())
