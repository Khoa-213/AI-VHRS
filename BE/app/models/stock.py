"""Stock ledger (migration 0033): goods receipts and one append-only row per change of a material's `stock_qty`."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

MOVE_KINDS = ("RECEIPT", "ISSUE", "RETURN", "ADJUST")
ITEM_KINDS = ("PAPER", "PEN", "INK")


class StockReceipt(Base):
    __tablename__ = "stock_receipts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str | None] = mapped_column(String(20))
    supplier: Mapped[str | None] = mapped_column(String(200))
    received_on: Mapped[date] = mapped_column(Date, server_default=text("CURRENT_DATE"))
    note: Mapped[str | None] = mapped_column(Text)
    client_ref: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))
    item_kind: Mapped[str] = mapped_column(String(5))
    item_id: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(Integer)
    stock_after: Mapped[int] = mapped_column(Integer)
    shortfall: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    job_id: Mapped[int | None] = mapped_column(ForeignKey("production_jobs.id"))
    receipt_id: Mapped[int | None] = mapped_column(ForeignKey("stock_receipts.id"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
