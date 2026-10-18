"""Request / response schemas for payments, the Manager's catalog / pricing / robot administration and scheduling."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.catalog import PaperSize, TemplateKind
from app.models.ops import JobStatus, PaymentGateway, PaymentStatus, PaymentType, RobotStatus
from app.models.order import StyleStatus

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=30,
                                        pattern=r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Money = Annotated[int, Field(ge=0, le=10_000_000_000)]
Surface = Literal["PLAIN", "ART", "GLOSSY", "COATED", "CARD", "OTHER"]
PenCategory = Literal["BALLPOINT", "GEL", "FINELINER", "FOUNTAIN", "BRUSH", "MARKER"]


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- customer: approve + deposit
class ApproveQuotationIn(BaseModel):
    option: int | None = Field(default=None, ge=1, le=3, description="Required when the quote has several material options.")
    deposit_pct: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=2,
                                        description="Share of the total paid now; from the quote's minimum up to 100. Default: the minimum.")


class StartDepositIn(BaseModel):
    gateway: PaymentGateway = PaymentGateway.VNPAY


class MockCheckoutIn(BaseModel):
    result: Literal["SUCCESS", "FAILED"] = "SUCCESS"


class PaymentOut(_ORM):
    id: int
    order_id: int
    type: PaymentType
    amount: Decimal
    deposit_pct: Decimal | None
    gateway: PaymentGateway
    gateway_txn_id: str | None
    status: PaymentStatus
    paid_at: datetime | None
    created_at: datetime
    mode: str = Field(default="MOCK", description="MOCK = simulated payment, no real money moved.")
    checkout_path: str | None = Field(default=None, description="Where the (mock) gateway page lives while PENDING.")
    needs_refund: bool = False


class WebhookResult(BaseModel):
    result: Literal["PROCESSED", "ALREADY_PROCESSED", "IGNORED"]
    status: str
    order_status: str | None = None
    needs_refund: bool | None = None


# ---------------------------------------------------------------- manager: materials
class PaperIn(BaseModel):
    code: Code
    name: Name
    gsm: int = Field(gt=0, le=1000)
    surface: Surface
    size: PaperSize
    unit_price: Money
    stock_qty: int = Field(default=0, ge=0)
    is_active: bool = True


class PaperPatch(BaseModel):
    name: Name | None = None
    gsm: int | None = Field(default=None, gt=0, le=1000)
    surface: Surface | None = None
    size: PaperSize | None = None
    unit_price: Money | None = None
    is_active: bool | None = None


class PaperOut(_ORM):
    id: int
    code: str
    name: str
    gsm: int
    surface: str
    size: PaperSize
    unit_price: Decimal
    stock_qty: int
    is_active: bool


class PenIn(BaseModel):
    code: Code
    name: Name
    category: PenCategory
    stroke_width_mm: Decimal = Field(gt=0, le=20, decimal_places=2)
    f_target_n: Decimal = Field(ge=Decimal("0.3"), le=2, decimal_places=2)
    f_min_n: Decimal = Field(gt=0, decimal_places=2)
    f_max_n: Decimal = Field(gt=0, decimal_places=2)
    f_hard_n: Decimal = Field(gt=0, decimal_places=2)
    v_max_mm_s: Decimal = Field(gt=0, le=9999, decimal_places=1)
    surcharge: Money = 0
    stock_qty: int = Field(default=0, ge=0)
    is_active: bool = True

    @model_validator(mode="after")
    def _force_band(self) -> "PenIn":
        if not (0 < self.f_min_n < self.f_target_n < self.f_max_n < self.f_hard_n):
            raise ValueError("cần 0 < F_min < F_target < F_max < F_hard")
        return self


class PenPatch(BaseModel):
    name: Name | None = None
    category: PenCategory | None = None
    stroke_width_mm: Decimal | None = Field(default=None, gt=0, le=20, decimal_places=2)
    f_target_n: Decimal | None = Field(default=None, ge=Decimal("0.3"), le=2, decimal_places=2)
    f_min_n: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    f_max_n: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    f_hard_n: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    v_max_mm_s: Decimal | None = Field(default=None, gt=0, le=9999, decimal_places=1)
    surcharge: Money | None = None
    is_active: bool | None = None


class PenOut(_ORM):
    id: int
    code: str
    name: str
    category: str
    stroke_width_mm: Decimal
    f_target_n: Decimal
    f_min_n: Decimal
    f_max_n: Decimal
    f_hard_n: Decimal
    v_max_mm_s: Decimal
    surcharge: Decimal
    stock_qty: int
    is_active: bool


class InkIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    hex_code: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    unit_price: Money = 0
    stock_qty: int = Field(default=0, ge=0)
    is_active: bool = True


class InkPatch(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)] | None = None
    hex_code: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    unit_price: Money | None = None
    is_active: bool | None = None


class InkOut(_ORM):
    id: int
    pen_type_id: int
    name: str
    hex_code: str | None
    unit_price: Decimal
    stock_qty: int
    is_active: bool


class StockIn(BaseModel):
    mode: Literal["ADD", "SET"] = Field(description="ADD: change by `quantity` (may be negative). SET: set the new level.")
    quantity: int = Field(ge=-1_000_000, le=1_000_000)
    reason: Reason

    @model_validator(mode="after")
    def _set_non_negative(self) -> "StockIn":
        if self.mode == "SET" and self.quantity < 0:
            raise ValueError("SET cần quantity ≥ 0")
        return self


class CompatIn(BaseModel):
    is_compatible: bool
    note: str | None = Field(default=None, max_length=255)


class CompatOut(_ORM):
    paper_type_id: int
    pen_type_id: int
    is_compatible: bool
    note: str | None


# ---------------------------------------------------------------- manager: templates / styles
class TemplateIn(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=40,
                                           pattern=r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    kind: TemplateKind
    font_uri: str = Field(min_length=3, max_length=500, examples=["hershey:scripts"])
    is_active: bool = True


class TemplatePatch(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)] | None = None
    kind: TemplateKind | None = None
    font_uri: str | None = Field(default=None, min_length=3, max_length=500)
    is_active: bool | None = None


class TemplateAdminOut(_ORM):
    id: int
    code: str
    name: str
    kind: TemplateKind
    font_uri: str
    is_active: bool


class StyleOut(_ORM):
    id: int
    owner_id: int
    name: str
    status: StyleStatus
    coverage_pct: Decimal | None
    right_to_use_confirmed: bool
    keep_consent: bool
    approved_by: int | None
    approved_at: datetime | None
    created_at: datetime


# ---------------------------------------------------------------- manager: robots
class RobotIn(BaseModel):
    code: Code
    robot_type: str = Field(default="FAIRINO_FR3", min_length=1, max_length=50)
    station: str | None = Field(default=None, max_length=50)
    status: RobotStatus = RobotStatus.AVAILABLE
    is_simulated: bool = False
    supported_pen_categories: list[PenCategory] | None = Field(
        default=None, description="Empty / null = any pen category.")
    note: str | None = Field(default=None, max_length=1000)


class RobotPatch(BaseModel):
    robot_type: str | None = Field(default=None, min_length=1, max_length=50)
    station: str | None = Field(default=None, max_length=50)
    status: RobotStatus | None = None
    is_simulated: bool | None = None
    supported_pen_categories: list[PenCategory] | None = None
    note: str | None = Field(default=None, max_length=1000)


class RobotOut(_ORM):
    id: int
    code: str
    robot_type: str
    station: str | None
    status: RobotStatus
    is_simulated: bool
    supported_pen_categories: list[str] | None
    note: str | None
    affected_job_ids: list[int] = Field(default=[], description="Planned jobs that need a new robot (maintenance / broken).")


# ---------------------------------------------------------------- manager: pricing
class DiscountTier(BaseModel):
    min_qty: int = Field(ge=2, le=100000)
    pct: Decimal = Field(ge=0, lt=100, decimal_places=2)


class PricingSaveIn(BaseModel):
    """Only the fields to change; the rest is copied from the active version."""
    u_ot1: Money | None = None
    u_ot2: Money | None = None
    u_ot3: Money | None = None
    w_min: Money | None = None
    s_ot1: Money | None = None
    s_ot2: Money | None = None
    s_ot3: Money | None = None
    k_simple: Decimal | None = Field(default=None, gt=0, le=99, decimal_places=2)
    k_medium: Decimal | None = Field(default=None, gt=0, le=99, decimal_places=2)
    k_complex: Decimal | None = Field(default=None, gt=0, le=99, decimal_places=2)
    discount_tiers: list[DiscountTier] | None = None
    p_min_pct: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=2,
                                      description="Minimum deposit share (BR-10).")
    adjust_threshold_pct: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2,
                                                 description="Staff may adjust a quotation within +/- this % (BR-09).")
    canvas_mm_per_char: Decimal | None = Field(default=None, gt=0, le=1000, decimal_places=2)
    note: str | None = Field(default=None, max_length=500, description="Why the prices changed.")


class PricingOut(_ORM):
    id: int
    version: int
    is_active: bool
    u_ot1: Decimal
    u_ot2: Decimal
    u_ot3: Decimal
    w_min: Decimal
    s_ot1: Decimal
    s_ot2: Decimal
    s_ot3: Decimal
    k_simple: Decimal
    k_medium: Decimal
    k_complex: Decimal
    discount_tiers: list[dict[str, Any]]
    p_min_pct: Decimal
    adjust_threshold_pct: Decimal
    canvas_mm_per_char: Decimal
    note: str | None
    created_by: int | None
    created_at: datetime


# ---------------------------------------------------------------- manager: scheduling
class ProductionQueueRow(BaseModel):
    order_id: int
    code: str
    customer_name: str
    order_type: str
    quantity: int
    eta: date | None
    production_status: str
    confirmed_at: datetime | None
    duration_min: int | None


class Suggestion(BaseModel):
    robot_id: int
    robot_code: str
    is_simulated: bool
    technician_id: int
    technician_name: str
    slot_start: datetime
    slot_end: datetime
    finish_by: date
    eta_risk: bool = Field(description="True when finishing + hand-over margin is later than the promised ETA.")


class SuggestionOut(BaseModel):
    order_id: int
    duration_min: int
    writing_sec_per_copy: int
    quantity: int
    eta: date | None
    stock_warnings: list[str]
    suggestions: list[Suggestion]


class ScheduleIn(BaseModel):
    robot_id: int
    technician_id: int
    slot_start: datetime
    note: str | None = Field(default=None, max_length=500)


class RescheduleIn(BaseModel):
    robot_id: int | None = None
    technician_id: int | None = None
    slot_start: datetime | None = None
    reason: Reason


class UnscheduleIn(BaseModel):
    reason: Reason


class JobOut(_ORM):
    id: int
    order_id: int
    order_code: str = ""
    robot_id: int
    robot_code: str = ""
    technician_id: int
    technician_name: str = ""
    status: JobStatus
    is_rewrite: bool
    slot_start: datetime
    slot_end: datetime
    estimated_duration_min: int
    package_hash: str | None


class TechnicianOut(BaseModel):
    id: int
    full_name: str
    email: str
    active_jobs: int
