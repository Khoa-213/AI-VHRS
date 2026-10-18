"""ORM mapping for payments, robots and production jobs (existing tables; schema owned by SQL migrations).

Only the columns the web/API side reads or writes are mapped. The Technical Staff phase (4a) adds the job's package,
simulation and progress columns plus Calibration, JobEvent and Incident. No schema change.
"""
import enum
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (BigInteger, Boolean, DateTime, Enum, FetchedValue, ForeignKey, Integer, Numeric, String, Text,
                        text)
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


class JobEventType(str, enum.Enum):
    DOWNLOADED = "DOWNLOADED"
    HASH_MISMATCH = "HASH_MISMATCH"
    CALIBRATED = "CALIBRATED"
    SIMULATED = "SIMULATED"
    START = "START"
    PROGRESS = "PROGRESS"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    ESTOP = "ESTOP"
    OVER_FORCE = "OVER_FORCE"
    STROKE_LOST = "STROKE_LOST"
    SENSOR_LOST = "SENSOR_LOST"
    INCIDENT = "INCIDENT"
    WRITTEN = "WRITTEN"
    FORCE_SUMMARY = "FORCE_SUMMARY"


class PhotoKind(str, enum.Enum):
    OVERALL = "OVERALL"
    CLOSE_UP = "CLOSE_UP"
    OTHER = "OTHER"


class QcResult(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class IncidentType(str, enum.Enum):
    ROBOT = "ROBOT"
    MATERIAL = "MATERIAL"
    FORCE_MODULE = "FORCE_MODULE"
    OTHER = "OTHER"


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
    package_uri: Mapped[str | None] = mapped_column(Text)               # storage path of the approved trajectory JSON
    package_hash: Mapped[str | None] = mapped_column(String(64))        # SHA-256 of that file (FR-38)
    packaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    simulation_passed: Mapped[bool | None] = mapped_column(Boolean)    # FR-45; DB refuses WRITING unless TRUE
    simulation_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    progress_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue(),
                                                 server_onupdate=FetchedValue())


class Calibration(Base):
    """Paper / force calibration of one job (FR-44, BR-19). A new valid record supersedes the older ones."""
    __tablename__ = "calibrations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("production_jobs.id"))
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id"))
    technician_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    paper_type_id: Mapped[int | None] = mapped_column(ForeignKey("paper_types.id"))
    pen_type_id: Mapped[int | None] = mapped_column(ForeignKey("pen_types.id"))
    checklist: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    force_zero_offset: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    probe_points: Mapped[Any] = mapped_column(JSONB)
    frame_transform: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    height_map: Mapped[Any | None] = mapped_column(JSONB)
    force_curve: Mapped[Any | None] = mapped_column(JSONB)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class Incident(Base):
    """Robot / material / force-module incident (FR-48, UC-37). Photos belong to a later step; the column stays empty."""
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("production_jobs.id"))
    robot_id: Mapped[int | None] = mapped_column(ForeignKey("robots.id"))
    reported_by: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    type: Mapped[IncidentType] = mapped_column(Enum(IncidentType, name="incident_type", create_type=False))
    description: Mapped[str] = mapped_column(Text)
    photo_urls: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    robot_status_after: Mapped[RobotStatus | None] = mapped_column(Enum(RobotStatus, name="robot_status", create_type=False))
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class JobEvent(Base):
    """Append-only log of what happened to a job (FR-47, FR-48). actor_id NULL = Robot Agent / IoT device."""
    __tablename__ = "job_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("production_jobs.id"))
    event_type: Mapped[JobEventType] = mapped_column(Enum(JobEventType, name="job_event_type", create_type=False))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"))
    stroke_index: Mapped[int | None] = mapped_column(Integer)
    force_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class ProductPhoto(Base):
    """Photo of the written product with the technician's QC verdict (FR-49, BR-21). `url` is the storage path.
    A removed photo keeps its row (`deleted_at`) so the history stays; only live photos count for BR-21."""
    __tablename__ = "product_photos"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("production_jobs.id"))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    kind: Mapped[PhotoKind] = mapped_column(Enum(PhotoKind, name="photo_kind", create_type=False))
    url: Mapped[str] = mapped_column(Text)
    overlay_url: Mapped[str | None] = mapped_column(Text)
    qc_result: Mapped[QcResult | None] = mapped_column(Enum(QcResult, name="qc_result", create_type=False))
    qc_note: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
