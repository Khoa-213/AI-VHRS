"""ORM mapping for roles, accounts, audit_logs (existing tables; schema owned by SQL migrations)."""
import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, SmallInteger, String, Text, Uuid
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class AccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    DISABLED = "DISABLED"


class RoleCode(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    STAFF = "STAFF"
    TECHNICAL_STAFF = "TECHNICAL_STAFF"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(20))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, name="account_status", create_type=False), default=AccountStatus.ACTIVE)
    failed_login_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    addresses: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    role: Mapped[Role] = relationship(lazy="joined")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    policy_version: Mapped[str | None] = mapped_column(String(20))
    ip_address: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class AuthSession(Base):
    """One login. Tokens carry its id; revoking the row kills both access and refresh token."""
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(255))
