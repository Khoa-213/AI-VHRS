"""Schemas for the workshop side (Staff / Manager): queue, intake, sketches, quotations, messages, privacy."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.api.order_schemas import InputOut, OrderOut, _ORM
from app.models.order import ComplexityLevel, OrderStatus, OrderType
from app.models.sketch import AdjustmentStatus, QuotationStatus

PaperSizeLit = Literal["A6", "A5", "A4"]
RejectReasonLit = Literal["TOO_OLD", "DAMAGED", "MISSING_CONTENT", "PROHIBITED_CONTENT", "OTHER"]


# ---- queue & intake (UC-23, UC-24, UC-47) ----------------------------------------------------------
class WorkshopOrderRow(OrderOut):
    customer_name: str = ""
    assigned_staff_id: int | None = None
    complexity: ComplexityLevel | None = None
    privacy_accepted_at: datetime | None = None


class WorkshopInputOut(InputOut):
    file_url: str | None = Field(default=None, description="Signed link, valid 10 minutes")


class WorkshopOrderDetail(WorkshopOrderRow):
    inputs: list[WorkshopInputOut] = []
    warnings: list[str] = []
    final_sketch_version: int | None = None
    open_quotation_id: int | None = None


class AssignIn(BaseModel):
    staff_id: int


class AcceptIn(BaseModel):
    staff_id: int | None = Field(default=None, description="Manager only, when the order has no Staff yet.")


class RejectIn(BaseModel):
    reason: RejectReasonLit
    note: str | None = Field(default=None, max_length=1000, description="Required when reason = OTHER.")
    staff_id: int | None = None


class RequestInfoIn(BaseModel):
    note: str = Field(min_length=1, max_length=1000)
    staff_id: int | None = None


class StaffBrief(BaseModel):
    id: int
    full_name: str
    email: str
    open_orders: int


# ---- sketches (UC-25) ------------------------------------------------------------------------------
class SketchGenerateIn(BaseModel):
    paper_size: PaperSizeLit | None = Field(default=None, description="Default: the order's paper, else A4.")
    approach_note: str | None = Field(default=None, max_length=2000)
    seed: int | None = Field(default=None, description="Natural-variation seed (OT-3). Default: order id.")


class SketchManualIn(BaseModel):
    trajectory: dict[str, Any] = Field(description='{"format":"vhrs-trajectory/1","pages":[{"paper":{"size":"A4"},'
                                                   '"strokes":[{"kind":"manual","points":[[x_mm,y_mm],...]}]}]}')
    approach_note: str | None = Field(default=None, max_length=2000)
    suggested_complexity: ComplexityLevel | None = None


class SketchPatchIn(BaseModel):
    approach_note: str | None = Field(default=None, max_length=2000)
    suggested_complexity: ComplexityLevel | None = None


class SketchOut(_ORM):
    id: int
    version: int
    created_by: int
    similarity_score: Decimal | None
    suggested_complexity: ComplexityLevel | None
    estimated_writing_sec: int | None
    total_stroke_mm: Decimal | None
    pen_lift_count: int | None
    approach_note: str | None
    content_hash: str | None
    is_final: bool
    created_at: datetime
    preview_urls: list[str] = []
    image_urls: list[str] = []          # customer-facing JPEG per page (what the customer will see)
    trajectory_url: str | None = None   # signed link of the robot trajectory JSON
    warnings: list[str] = []


class SketchDetailOut(SketchOut):
    trajectory: dict[str, Any]


# ---- quotations (UC-26) ----------------------------------------------------------------------------
class MaterialOptionIn(BaseModel):
    """One material option. Whatever the customer already chose is kept and may be left out; Staff only fill the rest."""
    paper_type_id: int | None = None
    pen_type_id: int | None = None
    ink_color_id: int | None = None


class QuotationCreateIn(BaseModel):
    complexity: ComplexityLevel | None = Field(default=None, description="K_cx; default: the sketch's suggestion.")
    char_count: int | None = Field(default=None, ge=0, le=1_000_000, description="N confirmed by Staff.")
    options: list[MaterialOptionIn] | None = Field(default=None, max_length=3,
                                                   description="1-3 material options when the customer chose 'workshop suggests'.")
    eta: date | None = None


class AdjustIn(BaseModel):
    adjusted_total: Decimal = Field(gt=0, description="VND, multiple of 100.")
    reason: str = Field(min_length=1, max_length=1000)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class OptionSummary(BaseModel):
    option: int
    paper: str
    pen: str
    ink: str
    total: int
    min_deposit: int


class QuotationOut(_ORM):
    id: int
    order_id: int
    version: int
    sketch_id: int
    status: QuotationStatus
    adjustment_status: AdjustmentStatus
    line_items: list[dict[str, Any]]
    chosen_option: int | None
    char_count: int
    quantity: int
    complexity: ComplexityLevel
    computed_total: Decimal
    adjusted_total: Decimal | None
    adjustment_pct: Decimal | None
    adjustment_reason: str | None
    final_total: Decimal
    min_deposit_pct: Decimal
    eta: date | None
    sent_at: datetime | None
    valid_until: datetime | None
    approved_by: int | None
    approved_at: datetime | None
    customer_note: str | None
    created_at: datetime
    options: list[OptionSummary] = []
    has_pdf: bool = False


class FileLinkOut(BaseModel):
    url: str
    expires_in: int = 600


# ---- messages (UC-27) ------------------------------------------------------------------------------
class AttachmentRef(BaseModel):
    path: str


class MessageIn(BaseModel):
    kind: Literal["TEXT", "ORDER_CARD"] = Field(default="TEXT", description="`ORDER_CARD`: the customer shares this order's card "
                                                "(no body, no attachments; the card always shows the order's current state).")
    body: str | None = Field(default=None, max_length=2000)
    attachments: list[AttachmentRef] = Field(default_factory=list, max_length=5)


class MessageUploadIn(BaseModel):
    mime_type: Literal["image/jpeg", "image/png"]
    size_bytes: int = Field(gt=0)


class MessageUploadOut(BaseModel):
    path: str
    upload_url: str
    method: str
    expires_in: int


class AttachmentOut(BaseModel):
    url: str
    mime: str


class OrderCardOut(BaseModel):
    code: str
    order_type: OrderType
    order_status: OrderStatus
    quantity: int
    total_amount: Decimal | None = Field(default=None, description="null until a quotation has been approved")


class MessageOut(BaseModel):
    id: int
    sender_id: int
    mine: bool
    kind: Literal["TEXT", "ORDER_CARD"] = "TEXT"
    order_card: OrderCardOut | None = Field(default=None, description="Only for `ORDER_CARD`: read from the order's CURRENT state, "
                                            "so the card never disagrees with the order.")
    body: str | None
    attachments: list[AttachmentOut]
    read_at: datetime | None
    created_at: datetime


class MessagePage(BaseModel):
    items: list[MessageOut]
    total: int
    page: int
    page_size: int
    unread: int


# ---- conversation list (one row per order that has messages) --------------------------------------------
class LastMessageOut(BaseModel):
    body: str | None
    kind: Literal["TEXT", "ORDER_CARD"]
    has_attachment: bool
    created_at: datetime
    mine: bool


class ConversationOut(BaseModel):
    order_id: int
    code: str
    order_type: OrderType
    order_status: OrderStatus
    customer_name: str | None = Field(default=None, description="Workshop side only; null for the customer")
    last_message: LastMessageOut
    unread: int


class ConversationPage(BaseModel):
    items: list[ConversationOut]
    total: int
    page: int
    page_size: int


class UnreadCountOut(BaseModel):
    unread: int = Field(description="Messages from the other side not yet read, across all the caller's conversations")


# ---- customer: privacy + viewing the quote (UC-15, FR-52) ------------------------------------------
class PrivacyPolicyOut(BaseModel):
    version: str
    title: str | None = None
    body: str


class PrivacyDecisionIn(BaseModel):
    accept: bool


class ChangeRequestIn(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


class SketchForCustomer(BaseModel):
    version: int
    preview_urls: list[str]
    image_urls: list[str] = []
    approach_note: str | None
    estimated_writing_sec: int | None
    similarity_score: Decimal | None


class QuotationCustomerOut(BaseModel):
    id: int
    version: int
    status: QuotationStatus
    line_items: list[dict[str, Any]]
    options: list[OptionSummary]
    chosen_option: int | None
    char_count: int
    quantity: int
    final_total: Decimal
    min_deposit_pct: Decimal
    eta: date | None
    valid_until: datetime | None
    pdf_url: str | None
    note: str = "Giá chưa bao gồm phí giao hàng."
    sketch: SketchForCustomer | None
