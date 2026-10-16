"""ORM mapping for the material catalog and pricing (existing tables; schema owned by SQL migrations)."""
import enum
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, FetchedValue, ForeignKey, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PaperSize(str, enum.Enum):
    A6 = "A6"
    A5 = "A5"
    A4 = "A4"


class TemplateKind(str, enum.Enum):
    TYPOGRAPHY = "TYPOGRAPHY"
    CALLIGRAPHY = "CALLIGRAPHY"
    SINGLE_LINE_FONT = "SINGLE_LINE_FONT"


class PaperType(Base):
    __tablename__ = "paper_types"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(120))
    gsm: Mapped[int] = mapped_column(SmallInteger)
    surface: Mapped[str] = mapped_column(ENUM("PLAIN", "ART", "GLOSSY", "COATED", "CARD", "OTHER",
                                              name="paper_surface", create_type=False))
    size: Mapped[PaperSize] = mapped_column(Enum(PaperSize, name="paper_size", create_type=False))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PenType(Base):
    __tablename__ = "pen_types"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(ENUM("BALLPOINT", "GEL", "FINELINER", "FOUNTAIN", "BRUSH", "MARKER",
                                               name="pen_category", create_type=False))
    stroke_width_mm: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    f_target_n: Mapped[Decimal] = mapped_column(Numeric(4, 2))     # force profile (BR-20), used by the robot phase
    f_min_n: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    f_max_n: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    f_hard_n: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    v_max_mm_s: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    surcharge: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InkColor(Base):
    __tablename__ = "ink_colors"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pen_type_id: Mapped[int] = mapped_column(ForeignKey("pen_types.id"))
    name: Mapped[str] = mapped_column(String(60))
    hex_code: Mapped[str | None] = mapped_column(String(7))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PaperPenCompat(Base):
    __tablename__ = "paper_pen_compats"
    paper_type_id: Mapped[int] = mapped_column(ForeignKey("paper_types.id"), primary_key=True)
    pen_type_id: Mapped[int] = mapped_column(ForeignKey("pen_types.id"), primary_key=True)
    is_compatible: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(String(255))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))


class Template(Base):
    __tablename__ = "templates"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(150))
    kind: Mapped[TemplateKind] = mapped_column(Enum(TemplateKind, name="template_kind", create_type=False))
    font_uri: Mapped[str] = mapped_column(Text)          # "hershey:<font>" for single-line fonts
    preview_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))


class PricingConfig(Base):
    __tablename__ = "pricing_configs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean)
    u_ot1: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    u_ot2: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    u_ot3: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    w_min: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    s_ot1: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    s_ot2: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    s_ot3: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    k_simple: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    k_medium: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    k_complex: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    discount_tiers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    p_min_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    adjust_threshold_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))   # BR-09
    canvas_mm_per_char: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
