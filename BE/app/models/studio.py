"""Upgrade U5: studio drafts, their revisions, and the AI assistant's log (schema: migration 0021; orders: 0024)."""
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class StudioDraft(Base):
    __tablename__ = "studio_drafts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    mode: Mapped[str] = mapped_column(String(10))                 # TEXT (-> OT-3) | RESTORE (-> OT-1)
    status: Mapped[str] = mapped_column(String(10), default="OPEN")
    title: Mapped[str | None] = mapped_column(String(150))
    current_revision_id: Mapped[int | None] = mapped_column(BigInteger)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StudioRevision(Base):
    __tablename__ = "studio_revisions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("studio_drafts.id"))
    parent_id: Mapped[int | None] = mapped_column(BigInteger)
    seq: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    author: Mapped[str] = mapped_column(String(10))               # CUSTOMER | AI
    tool_name: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class AiSession(Base):
    __tablename__ = "ai_sessions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("studio_drafts.id"))      # a studio draft (U5) ...
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))             # ... or an order (V2 Phase C, 0024)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)          # order sessions: flags for the Staff
    customer_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    provider: Mapped[str | None] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(80))
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiMessage(Base):
    __tablename__ = "ai_messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("ai_sessions.id"))
    role: Mapped[str] = mapped_column(String(10))                 # USER | ASSISTANT
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="OK")  # OK | FAILED | CAPPED
    provider: Mapped[str | None] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(80))
    model_calls: Mapped[int] = mapped_column(SmallInteger, default=0)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_sha256: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    client_ref: Mapped[str | None] = mapped_column(String(64))                        # FE message id (duplicates, 0024)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class AiToolCall(Base):
    __tablename__ = "ai_tool_calls"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("ai_messages.id"))
    name: Mapped[str] = mapped_column(String(40))
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ok: Mapped[bool] = mapped_column(Boolean)
    revision_id: Mapped[int | None] = mapped_column(BigInteger)                       # studio_revisions
    sketch_revision_id: Mapped[int | None] = mapped_column(BigInteger)                # sketch_revisions (orders, 0024)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
