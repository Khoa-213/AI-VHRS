"""Customer order use cases: UC-07..14 (FR-05..11, FR-55, FR-56).

Business rules live here. Order status transitions are NOT re-implemented: the service issues the
UPDATE and the DB trigger fn_order_state_guard accepts or rejects it (SQLSTATE P0409 -> HTTP 409).
"""
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.integrations.storage import ObjectStorage
from app.models.account import Account
from app.models.catalog import PricingConfig
from app.models.ops import PaymentStatus, PaymentType
from app.models.order import (Order, OrderInput, OrderInputKind, OrderStatus, OrderType, StyleStatus)
from app.repositories.catalog import CatalogRepository
from app.models.sketch import QuotationStatus
from app.repositories.ops import PaymentRepository
from app.repositories.orders import OrderRepository
from app.repositories.workshop import QuotationRepository
from app.services import audit, gateway_checkout as checkout
from app.services.handwriting_image import analyze_image, sniff_mime
from app.services.pricing import (MaterialPrices, PricingParams, canvas_chars, compute_price, count_text_chars,
                                  parse_tiers)

EDITABLE = {OrderStatus.DRAFT, OrderStatus.NEED_INFO}
CANCELLABLE_ONLINE = {OrderStatus.SUBMITTED, OrderStatus.NEED_INFO, OrderStatus.QUOTED, OrderStatus.AWAITING_DEPOSIT}
ALLOWED_INPUTS: dict[OrderType, set[OrderInputKind]] = {  # BR-03: one order type per order
    OrderType.OT1_COPY_RESTORE: {OrderInputKind.ORIGINAL_IMAGE},
    OrderType.OT2_LEARNED_STYLE: {OrderInputKind.HANDWRITING_SAMPLE, OrderInputKind.TEXT_CONTENT},
    OrderType.OT3_TEMPLATE: {OrderInputKind.TEXT_CONTENT, OrderInputKind.CANVAS},
}
IMAGE_KINDS = {OrderInputKind.ORIGINAL_IMAGE, OrderInputKind.HANDWRITING_SAMPLE}
# FR-10: "default complexity per order type". ASSUMPTION - to be confirmed with the workshop.
DEFAULT_COMPLEXITY = {OrderType.OT1_COPY_RESTORE: "MEDIUM", OrderType.OT2_LEARNED_STYLE: "MEDIUM",
                      OrderType.OT3_TEMPLATE: "SIMPLE"}
DEFAULTS = {"max_upload_mb": 20, "max_pages_per_order": 10}  # BR-04, used if system_settings has no row
_EXT = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}


@dataclass(frozen=True)
class Estimate:
    chars_min: int
    chars_max: int
    price_min: Decimal
    price_max: Decimal
    min_deposit_pct: Decimal
    basis: str
    materials_priced: bool


def _text_chars(rows: list[OrderInput]) -> int:
    return sum(count_text_chars(unicodedata.normalize("NFC", r.text_content or ""))
               for r in rows if r.kind == OrderInputKind.TEXT_CONTENT)


def _stroke_length_mm(canvas: dict[str, Any] | None) -> float:
    total = 0.0
    for stroke in (canvas or {}).get("strokes", []):
        pts = stroke.get("points", [])
        for a, b in zip(pts, pts[1:]):
            try:
                total += ((float(b["x"]) - float(a["x"])) ** 2 + (float(b["y"]) - float(a["y"])) ** 2) ** 0.5
            except (KeyError, TypeError, ValueError):
                continue
    return total


class PricingService:
    """Resolves the active price list and prices an order or an ad-hoc selection."""

    def __init__(self, session: Session):
        self.catalog = CatalogRepository(session)

    def _params(self, cfg: PricingConfig, order_type: OrderType) -> PricingParams:
        n = {OrderType.OT1_COPY_RESTORE: 1, OrderType.OT2_LEARNED_STYLE: 2, OrderType.OT3_TEMPLATE: 3}[order_type]
        return PricingParams(
            u_per_char=getattr(cfg, f"u_ot{n}"), w_min=cfg.w_min, setup_fee=getattr(cfg, f"s_ot{n}"),
            k_by_complexity={"SIMPLE": cfg.k_simple, "MEDIUM": cfg.k_medium, "COMPLEX": cfg.k_complex},
            discount_tiers=parse_tiers(cfg.discount_tiers), p_min_pct=cfg.p_min_pct,
            canvas_mm_per_char=cfg.canvas_mm_per_char)

    def params_for(self, cfg: PricingConfig, order_type: OrderType) -> PricingParams:
        return self._params(cfg, order_type)

    def exact_chars(self, order_type: OrderType, inputs: list[OrderInput], mm_per_char: Decimal) -> int:
        """N from typed text and canvas strokes (OT-2/OT-3); 0 when the order has none of them."""
        canvas = sum(canvas_chars(_stroke_length_mm(r.canvas_data), mm_per_char)
                     for r in inputs if r.kind == OrderInputKind.CANVAS)
        return _text_chars(inputs) + canvas

    def estimate(self, *, order_type: OrderType, quantity: int, paper_id: int | None, pen_id: int | None,
                 ink_id: int | None, inputs: list[OrderInput]) -> Estimate:
        cfg = self.catalog.active_pricing()
        if cfg is None:
            raise AppError(503, "PRICING_NOT_CONFIGURED", "Chưa có bảng giá đang áp dụng.")
        params = self._params(cfg, order_type)

        paper = self.catalog.paper(paper_id) if paper_id else None
        pen = self.catalog.pen(pen_id) if pen_id else None
        ink = self.catalog.ink(ink_id) if ink_id else None
        materials = MaterialPrices(paper=paper.unit_price if paper else Decimal(0),
                                   pen=pen.surcharge if pen else Decimal(0),
                                   ink=ink.unit_price if ink else Decimal(0))

        basis, lo, hi = "MINIMUM_CHARGE", 0, 0
        if order_type == OrderType.OT1_COPY_RESTORE:
            analysed = [r.quality_result for r in inputs if r.kind == OrderInputKind.ORIGINAL_IMAGE
                        and r.quality_result and r.quality_result.get("analysed")]
            if analysed:
                basis = "IMAGE_ESTIMATE"
                lo = sum(int(q["chars_min"]) for q in analysed)
                hi = sum(int(q["chars_max"]) for q in analysed)
        else:
            exact = _text_chars(inputs)
            canvas = sum(canvas_chars(_stroke_length_mm(r.canvas_data), params.canvas_mm_per_char)
                         for r in inputs if r.kind == OrderInputKind.CANVAS)
            if exact or canvas:
                basis = "MIXED" if exact and canvas else ("TEXT" if exact else "CANVAS")
                lo = hi = exact + canvas

        complexity = DEFAULT_COMPLEXITY[order_type]
        low = compute_price(params, chars=lo, quantity=quantity, complexity=complexity, materials=materials)
        high = compute_price(params, chars=hi, quantity=quantity, complexity=complexity, materials=materials)
        return Estimate(chars_min=lo, chars_max=hi, price_min=low.total, price_max=high.total,
                        min_deposit_pct=params.p_min_pct, basis=basis, materials_priced=bool(paper and pen))


class OrderService:
    def __init__(self, session: Session, customer: Account, storage: ObjectStorage | None = None,
                 ip: str | None = None):
        self.session, self.customer, self.storage, self.ip = session, customer, storage, ip
        self.orders = OrderRepository(session)
        self.catalog = CatalogRepository(session)
        self.pricing = PricingService(session)

    # ---- helpers ----
    def _get(self, order_id: int) -> Order:
        order = self.orders.get_owned(order_id, self.customer.id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        return order

    def _get_editable(self, order_id: int) -> Order:
        order = self._get(order_id)
        if order.order_status not in EDITABLE:
            raise AppError(409, "ORDER_NOT_EDITABLE", "Đơn đã gửi, không thể chỉnh sửa lúc này.")
        set_actor(self.session, self.customer.id)
        return order

    def _setting(self, key: str) -> Any:
        return self.catalog.setting(key, DEFAULTS[key])

    def _touch_and_price(self, order: Order) -> None:
        est = self.pricing.estimate(
            order_type=order.order_type, quantity=order.quantity, paper_id=order.paper_type_id,
            pen_id=order.pen_type_id, ink_id=order.ink_color_id, inputs=self.orders.inputs(order.id))
        order.char_count = (est.chars_min + est.chars_max) // 2
        order.estimated_price_min, order.estimated_price_max = est.price_min, est.price_max
        order.last_saved_at = datetime.now(timezone.utc)
        self.session.flush()

    # ---- orders ----
    def create(self, order_type: OrderType, quantity: int) -> Order:
        enabled = self.catalog.setting("order_types_enabled")
        if enabled is not None and order_type.value not in enabled:  # MSG03 / LI-10
            raise AppError(409, "ORDER_TYPE_SUSPENDED", "Loại dịch vụ này đang tạm ngừng nhận đơn.")
        set_actor(self.session, self.customer.id)
        order = self.orders.add(Order(code="VHRS-" + uuid.uuid4().hex[:8].upper(), customer_id=self.customer.id,
                                      order_type=order_type, quantity=quantity))
        self._touch_and_price(order)
        return order

    def update(self, order_id: int, changes: dict[str, Any]) -> tuple[Order, list[str]]:
        order = self._get_editable(order_id)
        warnings: list[str] = []
        if changes.get("order_type") is not None and changes["order_type"] != order.order_type:
            self._change_type(order, changes["order_type"])
        if "quantity" in changes and changes["quantity"] is not None:
            order.quantity = changes["quantity"]
        if "customer_note" in changes:
            order.customer_note = changes["customer_note"]
        if "workshop_suggest_materials" in changes and changes["workshop_suggest_materials"] is not None:
            order.workshop_suggest_materials = changes["workshop_suggest_materials"]
        if {"paper_type_id", "pen_type_id", "ink_color_id"} & changes.keys():
            self._apply_materials(order, changes, warnings)
        self._touch_and_price(order)
        return order, warnings

    def _change_type(self, order: Order, new_type: OrderType) -> None:
        """BR-03: the type may change while the order is still a draft, but only when every saved
        input is valid for the new type; otherwise the customer removes those inputs first."""
        if order.order_status != OrderStatus.DRAFT:
            raise AppError(409, "ORDER_TYPE_LOCKED", "Đơn đã gửi, không thể đổi loại đơn.")
        enabled = self.catalog.setting("order_types_enabled")
        if enabled is not None and new_type.value not in enabled:
            raise AppError(409, "ORDER_TYPE_SUSPENDED", "Loại dịch vụ này đang tạm ngừng nhận đơn.")
        blocking = [r.kind.value for r in self.orders.inputs(order.id) if r.kind not in ALLOWED_INPUTS[new_type]]
        if blocking:
            raise AppError(409, "ORDER_TYPE_HAS_INPUTS",
                           "Vui lòng xóa nội dung không dùng được với loại đơn mới trước khi đổi.", blocking)
        order.order_type = new_type

    def _apply_materials(self, order: Order, ch: dict[str, Any], warnings: list[str]) -> None:
        paper_id = ch.get("paper_type_id", order.paper_type_id) if "paper_type_id" in ch else order.paper_type_id
        pen_id = ch["pen_type_id"] if "pen_type_id" in ch else order.pen_type_id
        ink_id = ch["ink_color_id"] if "ink_color_id" in ch else order.ink_color_id

        if paper_id is not None:
            paper = self.catalog.paper(paper_id)
            if paper is None or not paper.is_active:
                raise AppError(422, "INVALID_PAPER", "Loại giấy không tồn tại hoặc đã ngừng cung cấp.")
        if pen_id is not None:
            pen = self.catalog.pen(pen_id)
            if pen is None or not pen.is_active:
                raise AppError(422, "INVALID_PEN", "Loại bút không tồn tại hoặc đã ngừng cung cấp.")
            if paper_id is not None and not self.catalog.is_compatible(paper_id, pen_id):  # BR-05, MSG05
                if "pen_type_id" in ch:
                    raise AppError(422, "PEN_INCOMPATIBLE",
                                   "Bút đã chọn không dùng được với loại giấy này. Vui lòng chọn lại bút.")
                pen_id, ink_id = None, None   # paper changed under an existing pen: reset (MSG05)
                warnings.append("PEN_RESET")
        elif ink_id is not None:
            raise AppError(422, "INK_REQUIRES_PEN", "Cần chọn bút trước khi chọn màu mực.")  # BR-05 order
        if ink_id is not None:
            ink = self.catalog.ink(ink_id)
            if ink is None or not ink.is_active or ink.pen_type_id != pen_id:
                if "ink_color_id" in ch:
                    raise AppError(422, "INVALID_INK", "Màu mực không thuộc bút đã chọn.")
                ink_id = None
                warnings.append("INK_RESET")
        order.paper_type_id, order.pen_type_id, order.ink_color_id = paper_id, pen_id, ink_id

    def cancel(self, order_id: int, reason: str) -> Order:
        """UC-21 for the part that needs no refund: SUBMITTED / NEED_INFO, and QUOTED / AWAITING_DEPOSIT where the
        customer declines the quotation or abandons the deposit (nothing paid yet). Cancelling after the deposit
        involves the refund policy (BR-14/16) and is handled in the production phase."""
        order = self._get(order_id)
        if order.order_status == OrderStatus.DRAFT:
            raise AppError(409, "ORDER_IS_DRAFT", "Bản nháp không cần hủy, hãy xóa bản nháp.")
        if order.order_status not in CANCELLABLE_ONLINE:
            raise AppError(409, "ORDER_CANCEL_UNSUPPORTED", "Đơn ở trạng thái này chưa thể hủy trực tuyến.")
        order = self.orders.get(order.id, lock=True)
        self.session.refresh(order)          # the object was loaded before the lock: a deposit confirmed meanwhile must be seen
        if order.order_status not in CANCELLABLE_ONLINE:
            raise AppError(409, "ORDER_CANCEL_UNSUPPORTED", "Đơn ở trạng thái này chưa thể hủy trực tuyến.")
        if order.order_status in (OrderStatus.QUOTED, OrderStatus.AWAITING_DEPOSIT):
            live = QuotationRepository(self.session).latest(order.id, (QuotationStatus.SENT,))
            if live is not None:
                live.status, live.customer_responded_at = QuotationStatus.CANCELLED, datetime.now(timezone.utc)
            for pay in PaymentRepository(self.session).pending(order.id, PaymentType.DEPOSIT):
                pay.status = PaymentStatus.CANCELLED
                checkout.close(pay)          # a payOS QR would otherwise stay payable until it expires
        set_actor(self.session, self.customer.id, reason)
        order.order_status = OrderStatus.CANCELLED
        order.cancel_reason = reason
        self.session.flush()
        self.session.refresh(order)
        audit.record(self.session, actor_id=self.customer.id, action="ORDER_CANCEL", entity_type="order",
                     entity_id=order.id, reason=reason, ip=self.ip)
        return order

    def file_url(self, order_id: int, input_id: int) -> tuple[str, int]:
        order = self._get(order_id)
        row = self.orders.input(order.id, input_id)
        if row is None or not row.file_url:
            raise AppError(404, "INPUT_NOT_FOUND", "Không tìm thấy tệp.")
        if self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        return self.storage.create_download_url(row.file_url, 600), 600

    def delete_draft(self, order_id: int) -> None:
        order = self._get(order_id)
        if order.order_status != OrderStatus.DRAFT:
            raise AppError(409, "ORDER_NOT_DRAFT", "Chỉ xóa được bản nháp.")
        paths = [r.file_url for r in self.orders.inputs(order.id) if r.file_url]
        self.orders.delete(order)
        for p in paths:
            self._delete_object(p)

    # ---- inputs ----
    def _check_kind(self, order: Order, kind: OrderInputKind) -> None:
        if kind not in ALLOWED_INPUTS[order.order_type]:
            raise AppError(422, "INPUT_KIND_NOT_ALLOWED", "Loại nội dung này không dùng được với loại đơn đã chọn.")

    def _validate_template_style(self, template_id: int | None, style_id: int | None) -> None:
        if template_id is not None:
            tpl = self.catalog.template(template_id)
            if tpl is None or not tpl.is_active:
                raise AppError(422, "INVALID_TEMPLATE", "Mẫu chữ không tồn tại hoặc đang tắt.")
        if style_id is not None:
            style = self.orders.style(style_id)
            if style is None or style.owner_id != self.customer.id or style.status != StyleStatus.APPROVED:
                raise AppError(422, "INVALID_STYLE", "Bộ nét đã lưu không hợp lệ.")

    def set_text(self, order_id: int, data: dict[str, Any]) -> OrderInput:
        order = self._get_editable(order_id)
        self._check_kind(order, OrderInputKind.TEXT_CONTENT)
        self._validate_template_style(data.get("template_id"), data.get("handwriting_style_id"))
        if order.order_type == OrderType.OT3_TEMPLATE and data.get("template_id") is None:
            raise AppError(422, "TEMPLATE_REQUIRED", "Vui lòng chọn mẫu chữ.")
        if not count_text_chars(data["text_content"]):
            raise AppError(422, "EMPTY_TEXT", "Nội dung không được để trống.")
        row = next((r for r in self.orders.inputs(order.id) if r.kind == OrderInputKind.TEXT_CONTENT), None)
        if row is None:
            row = self.orders.add_input(OrderInput(order_id=order.id, kind=OrderInputKind.TEXT_CONTENT))
        for k, v in data.items():
            setattr(row, k, v)
        row.text_content = unicodedata.normalize("NFC", row.text_content or "")  # S0: Unicode NFC
        self._touch_and_price(order)
        return row

    def set_canvas(self, order_id: int, canvas_data: dict[str, Any]) -> OrderInput:
        order = self._get_editable(order_id)
        self._check_kind(order, OrderInputKind.CANVAS)
        if not canvas_data.get("strokes"):
            raise AppError(422, "EMPTY_CANVAS", "Canvas chưa có nét vẽ.")
        row = next((r for r in self.orders.inputs(order.id) if r.kind == OrderInputKind.CANVAS), None)
        if row is None:   # chk_input_payload: a CANVAS row must carry its data from the first INSERT
            row = self.orders.add_input(OrderInput(order_id=order.id, kind=OrderInputKind.CANVAS,
                                                   canvas_data=canvas_data))
        row.canvas_data = canvas_data
        self._touch_and_price(order)
        return row

    def request_upload(self, order_id: int, kind: OrderInputKind, mime_type: str, size_bytes: int) -> tuple[OrderInput, Any]:
        order = self._get_editable(order_id)
        self._check_kind(order, kind)
        max_bytes = int(self._setting("max_upload_mb")) * 1024 * 1024
        if size_bytes > max_bytes:
            raise AppError(422, "FILE_TOO_LARGE", f"File vượt quá {self._setting('max_upload_mb')} MB.")  # BR-04
        pages = sum(1 for r in self.orders.inputs(order.id) if r.kind in IMAGE_KINDS)
        if pages >= int(self._setting("max_pages_per_order")):
            raise AppError(422, "TOO_MANY_FILES", "Đã đạt số lượng ảnh tối đa cho mỗi đơn.")
        if self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        path = f"orders/{order.id}/{uuid.uuid4().hex}.{_EXT[mime_type]}"
        row = self.orders.add_input(OrderInput(order_id=order.id, kind=kind, file_url=path, mime_type=mime_type,
                                               file_size_bytes=size_bytes, sort_order=pages))
        return row, self.storage.create_upload_target(path)

    def _analyse_row(self, row: OrderInput, data: bytes) -> None:
        if row.mime_type == "application/pdf":  # PDF pages are stored but not analysed in this phase
            row.quality_result = {"analysed": False, "reason": "PDF_NOT_ANALYSED"}
            row.is_quality_warning = False
            return
        result = analyze_image(data, rotation_deg=row.rotation_deg or 0, crop_box=row.crop_box)
        row.quality_result = result.as_quality_result()
        row.is_quality_warning = result.warning  # MSG04: warn, but still allow submit (BR-04)

    def confirm_upload(self, order_id: int, input_id: int) -> OrderInput:
        order = self._get_editable(order_id)
        row = self.orders.input(order.id, input_id)
        if row is None or row.kind not in IMAGE_KINDS or not row.file_url:
            raise AppError(404, "INPUT_NOT_FOUND", "Không tìm thấy tệp.")
        data = self._read_object(row.file_url)
        if data is None:
            raise AppError(409, "UPLOAD_NOT_FOUND", "Chưa nhận được file. Vui lòng tải lên rồi xác nhận lại.")
        real_mime = sniff_mime(data)
        max_bytes = int(self._setting("max_upload_mb")) * 1024 * 1024
        if real_mime is None or len(data) > max_bytes:
            self._delete_object(row.file_url)
            self.orders.delete_input(row)
            raise AppError(422, "INVALID_FILE", "File phải là jpg, png hoặc pdf và không quá dung lượng cho phép.")
        row.mime_type, row.file_size_bytes = real_mime, len(data)
        self._analyse_row(row, data)
        self._touch_and_price(order)
        return row

    def patch_image(self, order_id: int, input_id: int, changes: dict[str, Any]) -> OrderInput:
        order = self._get_editable(order_id)
        row = self.orders.input(order.id, input_id)
        if row is None or row.kind not in IMAGE_KINDS:
            raise AppError(404, "INPUT_NOT_FOUND", "Không tìm thấy tệp.")
        if "rotation_deg" in changes and changes["rotation_deg"] is not None:
            row.rotation_deg = changes["rotation_deg"]
        if "crop_box" in changes:
            row.crop_box = changes["crop_box"]
        if row.quality_result is not None and row.file_url:   # already uploaded: re-run the analysis
            data = self._read_object(row.file_url)
            if data is not None:
                self._analyse_row(row, data)
        self._touch_and_price(order)
        return row

    def delete_input(self, order_id: int, input_id: int) -> None:
        order = self._get_editable(order_id)
        row = self.orders.input(order.id, input_id)
        if row is None:
            raise AppError(404, "INPUT_NOT_FOUND", "Không tìm thấy nội dung.")
        path = row.file_url
        self.orders.delete_input(row)
        if path:
            self._delete_object(path)
        self._touch_and_price(order)

    def _read_object(self, path: str) -> bytes | None:
        if self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        return self.storage.read(path)

    def _delete_object(self, path: str) -> None:
        if self.storage is not None:
            try:
                self.storage.delete(path)
            except Exception:  # best effort: an orphan object is harmless and purged by retention (BR-23)
                pass

    # ---- submit ----
    def _validate_complete(self, order: Order, inputs: list[OrderInput], confirm_right: bool) -> None:
        problems: list[dict[str, str]] = []
        kinds = {r.kind for r in inputs}
        pending = [r for r in inputs if r.kind in IMAGE_KINDS and r.quality_result is None]
        if pending:
            problems.append({"field": "inputs", "message": "Có tệp chưa tải lên hoàn tất."})
        t = order.order_type
        if t == OrderType.OT1_COPY_RESTORE and OrderInputKind.ORIGINAL_IMAGE not in kinds:
            problems.append({"field": "inputs", "message": "Vui lòng tải ảnh bản gốc."})
        if t == OrderType.OT2_LEARNED_STYLE:
            texts = [r for r in inputs if r.kind == OrderInputKind.TEXT_CONTENT]
            has_style = any(r.handwriting_style_id for r in texts)
            if OrderInputKind.HANDWRITING_SAMPLE not in kinds and not has_style:
                problems.append({"field": "inputs", "message": "Vui lòng tải mẫu chữ hoặc chọn bộ nét đã lưu."})
            if OrderInputKind.TEXT_CONTENT not in kinds:
                problems.append({"field": "inputs", "message": "Vui lòng nhập nội dung cần viết."})
            if not confirm_right:  # BR-23
                problems.append({"field": "confirm_right_to_use", "message": "Cần xác nhận quyền sử dụng nét chữ."})
        if t == OrderType.OT3_TEMPLATE and not ({OrderInputKind.TEXT_CONTENT, OrderInputKind.CANVAS} & kinds):
            problems.append({"field": "inputs", "message": "Vui lòng nhập nội dung hoặc vẽ canvas."})
        if not order.workshop_suggest_materials and not (order.paper_type_id and order.pen_type_id
                                                         and order.ink_color_id):
            problems.append({"field": "materials", "message": "Vui lòng chọn đủ giấy, bút và màu mực."})  # BR-07
        if problems:
            raise AppError(422, "ORDER_INCOMPLETE", "Vui lòng nhập đầy đủ thông tin bắt buộc.", problems)  # MSG01

    def submit(self, order_id: int, *, terms_accepted: bool, confirm_right_to_use: bool) -> Order:
        order = self._get_editable(order_id)
        if order.order_status != OrderStatus.DRAFT:
            raise AppError(409, "ORDER_NOT_DRAFT", "Đơn này đã được gửi.")
        if not terms_accepted:
            raise AppError(422, "TERMS_NOT_ACCEPTED", "Cần đồng ý điều khoản trước khi gửi đơn.")
        self._validate_complete(order, self.orders.inputs(order.id), confirm_right_to_use)
        self._touch_and_price(order)
        order.terms_accepted_at = datetime.now(timezone.utc)
        order.order_status = OrderStatus.SUBMITTED           # DB guard validates the transition
        self.session.flush()
        self.session.refresh(order)
        audit.record(self.session, actor_id=self.customer.id, action="ORDER_SUBMIT", entity_type="order",
                     entity_id=order.id, new={"code": order.code}, ip=self.ip)
        return order

    def provide_info(self, order_id: int, *, confirm_right_to_use: bool) -> Order:
        order = self._get_editable(order_id)
        if order.order_status != OrderStatus.NEED_INFO:
            raise AppError(409, "ORDER_NOT_NEED_INFO", "Đơn không ở trạng thái cần bổ sung.")
        self._validate_complete(order, self.orders.inputs(order.id), confirm_right_to_use)
        self._touch_and_price(order)
        order.order_status = OrderStatus.SUBMITTED
        self.session.flush()
        self.session.refresh(order)
        return order
