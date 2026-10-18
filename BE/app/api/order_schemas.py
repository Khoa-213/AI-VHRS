"""Request/response schemas for catalog, pricing and customer orders (kept separate from ORM models)."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import OrderInputKind, OrderStatus, OrderType, ProductionStatus


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- catalog (FR-04, FR-09) -------------------------------------------------------------
class PaperOut(_ORM):
    id: int
    code: str
    name: str
    gsm: int
    surface: str
    size: str
    unit_price: Decimal


class PenOut(_ORM):
    id: int
    code: str
    name: str
    category: str
    stroke_width_mm: Decimal
    surcharge: Decimal


class InkOut(_ORM):
    id: int
    pen_type_id: int
    name: str
    hex_code: str | None
    unit_price: Decimal


class PenWithInksOut(PenOut):
    inks: list[InkOut]


class SuggestMaterialsOut(BaseModel):
    """Everything the customer can still pick after choosing the paper: the pens that suit it, each with its inks."""
    paper: PaperOut
    pens: list[PenWithInksOut]


class TemplateOut(_ORM):
    id: int
    code: str
    name: str
    kind: str
    preview_url: str | None


# ---- pricing (FR-10, FR-29) -------------------------------------------------------------
class EstimateIn(BaseModel):
    order_type: OrderType
    quantity: int = Field(default=1, ge=1, le=10000)
    paper_type_id: int | None = None
    pen_type_id: int | None = None
    ink_color_id: int | None = None
    text: str | None = Field(default=None, max_length=20000,
                             description="Typed content (OT-2/OT-3). Counted automatically; never ask the customer for N.")
    order_id: int | None = Field(default=None, description="Use the saved content of this order (incl. image estimates).")


class EstimateOut(BaseModel):
    chars_min: int
    chars_max: int
    price_min: Decimal
    price_max: Decimal
    min_deposit_pct: Decimal
    basis: Literal["TEXT", "IMAGE_ESTIMATE", "CANVAS", "MIXED", "MINIMUM_CHARGE"]
    materials_priced: bool
    note: str = "Giá ước tính, chưa gồm phí giao hàng. Báo giá chính thức sau khi có phác thảo."


# ---- orders (FR-05, FR-11, FR-55, FR-56) ---------------------------------------------------
class OrderCreateIn(BaseModel):
    order_type: OrderType
    quantity: int = Field(default=1, ge=1, le=10000)


class OrderUpdateIn(BaseModel):
    """Only the fields that are sent are changed."""
    order_type: OrderType | None = Field(default=None, description="Đổi loại đơn khi còn DRAFT (BR-03).")
    paper_type_id: int | None = None
    pen_type_id: int | None = None
    ink_color_id: int | None = None
    workshop_suggest_materials: bool | None = None
    quantity: int | None = Field(default=None, ge=1, le=10000)
    customer_note: str | None = Field(default=None, max_length=2000)


class OrderOut(_ORM):
    id: int
    code: str
    order_type: OrderType
    order_status: OrderStatus
    production_status: ProductionStatus
    paper_type_id: int | None
    pen_type_id: int | None
    ink_color_id: int | None
    workshop_suggest_materials: bool
    quantity: int
    char_count: int | None
    estimated_price_min: Decimal | None
    estimated_price_max: Decimal | None
    total_amount: Decimal | None = None
    deposit_pct: Decimal | None = None
    deposit_amount: Decimal | None = None
    customer_note: str | None
    info_request_note: str | None
    reject_reason: str | None
    reject_note: str | None
    eta: Any | None
    last_saved_at: datetime
    submitted_at: datetime | None
    created_at: datetime


class InputOut(_ORM):
    id: int
    kind: OrderInputKind
    sort_order: int
    mime_type: str | None
    file_size_bytes: int | None
    rotation_deg: int | None
    crop_box: dict[str, Any] | None
    quality_result: dict[str, Any] | None
    is_quality_warning: bool
    confirmed: bool = True
    text_content: str | None
    template_id: int | None
    handwriting_style_id: int | None
    font_size_mm: Decimal | None
    alignment: str | None
    layout: dict[str, Any] | None
    canvas_data: dict[str, Any] | None


class OrderDetailOut(OrderOut):
    inputs: list[InputOut] = []
    warnings: list[str] = []


class TextInputIn(BaseModel):
    text_content: str = Field(min_length=1, max_length=20000)
    template_id: int | None = None
    handwriting_style_id: int | None = None
    font_size_mm: Decimal | None = Field(default=None, gt=0, le=100)
    alignment: Literal["LEFT", "CENTER", "RIGHT", "JUSTIFY"] | None = None
    layout: dict[str, Any] | None = None


class CanvasInputIn(BaseModel):
    canvas_data: dict[str, Any] = Field(
        description='{"strokes": [{"points": [{"x": mm, "y": mm, "p": 0..1}, ...]}, ...]}  (x, y in millimetres)')


class UploadUrlIn(BaseModel):
    kind: Literal["ORIGINAL_IMAGE", "HANDWRITING_SAMPLE"]
    mime_type: Literal["image/jpeg", "image/png", "application/pdf"]
    size_bytes: int = Field(gt=0)


class UploadUrlOut(BaseModel):
    input_id: int
    upload_url: str
    method: str
    expires_in: int


class ImagePatchIn(BaseModel):
    rotation_deg: Literal[0, 90, 180, 270] | None = None
    crop_box: dict[str, float] | None = Field(
        default=None, description='{"x","y","w","h"}: 0..1 fractions of the (rotated) image, or pixels')


class SubmitIn(BaseModel):
    terms_accepted: bool
    confirm_right_to_use: bool = Field(
        default=False, description="OT-2 only: customer confirms the right to use the handwriting (BR-23).")


class CancelIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class FileUrlOut(BaseModel):
    url: str
    expires_in: int


class StyleOut(_ORM):
    id: int
    name: str
