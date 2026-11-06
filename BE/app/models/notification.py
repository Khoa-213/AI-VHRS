"""ORM mapping for `notifications` (existing table of the baseline schema, FR-27). No schema change."""
import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class NotificationType(str, enum.Enum):
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_REJECTED = "ORDER_REJECTED"
    NEED_INFO = "NEED_INFO"
    ORDER_STATUS_CHANGED = "ORDER_STATUS_CHANGED"
    PRODUCTION_STATUS_CHANGED = "PRODUCTION_STATUS_CHANGED"
    SKETCH_READY = "SKETCH_READY"
    QUOTATION_AVAILABLE = "QUOTATION_AVAILABLE"
    QUOTATION_EXPIRED = "QUOTATION_EXPIRED"
    ETA_POSTPONED = "ETA_POSTPONED"
    NEW_MESSAGE = "NEW_MESSAGE"
    PRODUCT_COMPLETED = "PRODUCT_COMPLETED"
    DELIVERING = "DELIVERING"
    PAYMENT = "PAYMENT"
    SYSTEM = "SYSTEM"


class NotificationChannel(str, enum.Enum):
    EMAIL = "EMAIL"
    IN_APP = "IN_APP"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accounts.id"))
    order_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("orders.id"))
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType, name="notification_type", create_type=False))
    msg_code: Mapped[str | None] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel", create_type=False))
    is_read: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
