"""Quotations: UC-26, UC-15 (FR-15, FR-29, FR-31, FR-32, FR-52; BR-08, BR-09, BR-22, BR-25).

Workshop side: QuotationService (Staff and Manager). Customer side: CustomerQuoteService (privacy consent,
viewing the quote, asking for changes). Approving the quote and paying the deposit belong to the next phase.
Quotation statuses have no DB guard, so the rules are enforced here and covered by tests.
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.domain import quotation_rules as rules
from app.integrations.storage import ObjectStorage
from app.models.account import Account
from app.models.order import ComplexityLevel, Order, OrderStatus
from app.models.sketch import AdjustmentStatus, Quotation, QuotationStatus
from app.repositories.accounts import AccountRepository
from app.repositories.catalog import CatalogRepository
from app.repositories.orders import OrderRepository
from app.repositories.workshop import QuotationRepository, SketchRepository
from app.services import audit, notifications, quotation_pdf
from app.services.orders import DEFAULT_COMPLEXITY, PricingService
from app.services.pricing import MaterialPrices, compute_price
from app.services.workshop_access import WorkshopAccess

log = logging.getLogger("app")
DEFAULT_VALID_DAYS = 7
MAX_OPTIONS = 3
ADJUST_OK_TO_SEND = {AdjustmentStatus.NONE, AdjustmentStatus.WITHIN_THRESHOLD, AdjustmentStatus.APPROVED,
                     AdjustmentStatus.REJECTED}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------------------------
# expiry (BR-08): called lazily when an order is read; a scheduler runs the same functions later
# ---------------------------------------------------------------------------------------------
def _expire(session: Session, q: Quotation, order: Order) -> None:
    q.status = QuotationStatus.EXPIRED
    if order.order_status in (OrderStatus.AWAITING_PRIVACY, OrderStatus.QUOTED):
        set_actor(session, None, "Báo giá hết hạn (BR-08)")
        order.order_status = OrderStatus.CANCELLED
        order.cancel_reason = "Báo giá hết hạn"
    session.flush()
    audit.record(session, actor_id=None, action="QUOTATION_EXPIRE", entity_type="quotation", entity_id=q.id,
                 new={"order_id": order.id, "version": q.version})
    notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="MSG08", code=order.code)


def expire_if_overdue(session: Session, order: Order) -> bool:
    q = QuotationRepository(session).live(order.id)
    if q is not None and q.status == QuotationStatus.SENT and q.valid_until and q.valid_until < _now():
        _expire(session, q, order)
        return True
    return False


def expire_and_persist(session: Session, order: Order) -> bool:
    """Same as expire_if_overdue, but commits straight away. A request that then fails (409 ...) rolls its own
    transaction back; without this the expiry it just detected would be lost and found again next time."""
    if expire_if_overdue(session, order):
        session.commit()
        return True
    return False


def expire_all(session: Session, now: datetime | None = None) -> int:
    repo, orders = QuotationRepository(session), OrderRepository(session)
    count = 0
    for q in repo.overdue(now or _now()):
        order = orders.get(q.order_id, lock=True)
        if order is not None:
            _expire(session, q, order)
            count += 1
    return count


def _setting_int(catalog: CatalogRepository, key: str, default: int) -> int:
    try:
        return int(catalog.setting(key, default))
    except (TypeError, ValueError):
        return default


def current_privacy_policy(catalog: CatalogRepository) -> dict[str, Any]:
    policy = catalog.setting("privacy_policy")
    if not isinstance(policy, dict) or not policy.get("version") or not policy.get("body"):
        raise AppError(503, "PRIVACY_POLICY_NOT_CONFIGURED", "Chưa cấu hình chính sách riêng tư (system_settings).")
    return policy


# ---------------------------------------------------------------------------------------------
# workshop side
# ---------------------------------------------------------------------------------------------
class QuotationService:
    def __init__(self, session: Session, actor: Account, storage: ObjectStorage | None = None, ip: str | None = None):
        self.session, self.actor, self.storage, self.ip = session, actor, storage, ip
        self.access = WorkshopAccess(session, actor)
        self.quotes = QuotationRepository(session)
        self.sketches = SketchRepository(session)
        self.catalog = CatalogRepository(session)
        self.orders = OrderRepository(session)
        self.pricing = PricingService(session)

    @property
    def is_manager(self) -> bool:
        return self.access.is_manager

    def _quote(self, quotation_id: int, *, lock: bool = False) -> tuple[Quotation, Order]:
        q = self.quotes.get(quotation_id, lock=lock)
        if q is None:
            raise AppError(404, "QUOTATION_NOT_FOUND", "Không tìm thấy báo giá.")
        order = self.access.order(q.order_id, write=False, lock=lock)
        return q, order

    # ---- create (FR-15, FR-29) ----
    def create(self, order_id: int, *, complexity: str | None, char_count: int | None,
               options: list[dict[str, int | None]] | None, eta: date | None) -> Quotation:
        order = self.access.order(order_id, write=True, lock=True)
        if order.order_status != OrderStatus.ACCEPTED:
            raise AppError(409, "ORDER_NOT_ACCEPTED", "Chỉ lập báo giá khi đơn đã được tiếp nhận.")
        sketch = self.sketches.final(order.id)
        if sketch is None:                                           # BR-22
            raise AppError(409, "SKETCH_REQUIRED", "Cần lưu và chốt phác thảo trước khi lập báo giá (BR-22).")
        if self.quotes.live(order.id) is not None:
            raise AppError(409, "QUOTATION_ALREADY_OPEN", "Đơn đã có báo giá đang xử lý; hãy sửa hoặc hủy báo giá đó.")
        cfg = self.catalog.active_pricing()
        if cfg is None:
            raise AppError(503, "PRICING_NOT_CONFIGURED", "Chưa có bảng giá đang áp dụng.")
        params = self.pricing.params_for(cfg, order.order_type)
        inputs = self.orders.inputs(order.id)

        level = complexity or (sketch.suggested_complexity.value if sketch.suggested_complexity else None) \
            or (order.complexity.value if order.complexity else DEFAULT_COMPLEXITY[order.order_type])
        chars = char_count
        if chars is None:
            exact = self.pricing.exact_chars(order.order_type, inputs, params.canvas_mm_per_char)
            chars = exact or (order.char_count or 0)
        if chars < 0:
            raise AppError(422, "INVALID_CHAR_COUNT", "Số ký tự không hợp lệ.")

        picks = self._material_options(order, options)
        built, snap_options, line_items = [], [], []
        for n, (paper, pen, ink) in enumerate(picks, start=1):
            b = compute_price(params, chars=chars, quantity=order.quantity, complexity=level,
                              materials=MaterialPrices(paper.unit_price, pen.surcharge, ink.unit_price))
            built.append(b)
            line_items += rules.build_line_items(
                n, paper_id=paper.id, pen_id=pen.id, ink_id=ink.id, paper_name=paper.name, pen_name=pen.name,
                ink_name=ink.name, paper_price=paper.unit_price, pen_price=pen.surcharge, ink_price=ink.unit_price,
                params=params, breakdown=b, complexity=level)
            snap_options.append({
                "option": n, "paper": {"id": paper.id, "name": paper.name, "price": str(paper.unit_price)},
                "pen": {"id": pen.id, "name": pen.name, "price": str(pen.surcharge)},
                "ink": {"id": ink.id, "name": ink.name, "price": str(ink.unit_price)},
                "writing_fee": str(b.writing_fee), "unit_price": str(b.unit_price), "discount_pct": str(b.discount_pct),
                "total": str(b.total), "min_deposit": str(b.min_deposit)})
        snapshot = {
            "pricing_config": {"id": cfg.id, "version": cfg.version, "u_per_char": str(params.u_per_char),
                               "w_min": str(params.w_min), "setup_fee": str(params.setup_fee),
                               "k": {k: str(v) for k, v in params.k_by_complexity.items()},
                               "discount_tiers": [{"min_qty": m, "pct": str(p)} for m, p in params.discount_tiers],
                               "p_min_pct": str(params.p_min_pct),
                               "canvas_mm_per_char": str(params.canvas_mm_per_char)},
            "adjust_threshold_pct": str(cfg.adjust_threshold_pct), "chars": chars, "quantity": order.quantity,
            "complexity": level, "options": snap_options, "computed_at": _now().isoformat()}
        self.quotes.supersede_open_changes(order.id)
        row = self.quotes.add(Quotation(
            order_id=order.id, version=self.quotes.next_version(order.id), sketch_id=sketch.id,
            pricing_config_id=cfg.id, created_by=self.actor.id, status=QuotationStatus.DRAFT, line_items=line_items,
            char_count=chars, quantity=order.quantity, complexity=ComplexityLevel(level),
            computed_total=built[0].total, adjustment_status=AdjustmentStatus.NONE, min_deposit_pct=cfg.p_min_pct,
            price_snapshot=snapshot, eta=eta if eta and eta >= date.today() else None))
        audit.record(self.session, actor_id=self.actor.id, action="QUOTATION_CREATE", entity_type="quotation",
                     entity_id=row.id, new={"order_id": order.id, "version": row.version,
                                            "computed_total": str(row.computed_total), "options": len(picks)},
                     ip=self.ip)
        return row

    _FIELDS = (("paper_type_id", "giấy"), ("pen_type_id", "bút"), ("ink_color_id", "mực"))

    def _material_options(self, order: Order, options: list[dict[str, int | None]] | None):
        """'Let the workshop choose' keeps whatever the customer already picked: Staff may only fill in what is
        still empty (paper -> pen -> ink), and every option must still pass the compatibility rules."""
        fixed = {f: getattr(order, f) for f, _ in self._FIELDS}
        if order.workshop_suggest_materials:
            if all(fixed.values()):
                specs = [dict(fixed)]                              # nothing left for Staff to suggest
            elif not options or len(options) > MAX_OPTIONS:
                raise AppError(422, "OPTIONS_REQUIRED",
                               f"Khách chọn 'để xưởng đề xuất': cần 1–{MAX_OPTIONS} phương án vật tư.")
            else:
                specs = options
        else:
            if not all(fixed.values()):
                raise AppError(409, "MATERIALS_MISSING", "Đơn chưa chọn đủ giấy, bút, mực.")
            specs = [dict(fixed)]
        picks = []
        for i, spec in enumerate(specs, start=1):
            merged = {}
            for f, label in self._FIELDS:
                if spec.get(f) and fixed[f] and spec[f] != fixed[f]:
                    raise AppError(422, "MATERIAL_LOCKED_BY_CUSTOMER",
                                   f"Phương án {i}: khách đã chọn {label}, không được đổi.", {"option": i, "field": f})
                merged[f] = spec.get(f) or fixed[f]
            missing = [label for f, label in self._FIELDS if not merged[f]]
            if missing:
                raise AppError(422, "INVALID_MATERIALS", f"Phương án {i}: còn thiếu {', '.join(missing)}.", {"option": i})
            paper = self.catalog.paper(merged["paper_type_id"])
            pen = self.catalog.pen(merged["pen_type_id"])
            ink = self.catalog.ink(merged["ink_color_id"])
            problem = None
            if not (paper and paper.is_active):
                problem = "giấy không tồn tại hoặc đã ngừng"
            elif not (pen and pen.is_active):
                problem = "bút không tồn tại hoặc đã ngừng"
            elif not (ink and ink.is_active and ink.pen_type_id == pen.id):
                problem = "mực không thuộc bút đã chọn"
            elif not self.catalog.is_compatible(paper.id, pen.id):   # BR-05 / BR-06
                problem = "bút không tương thích với giấy"
            if problem:
                raise AppError(422, "INVALID_MATERIALS", f"Phương án {i}: {problem}.", {"option": i})
            picks.append((paper, pen, ink))
        return picks

    def material_candidates(self, order_id: int, limit: int = 60) -> dict:
        """What Staff may still offer: every paper / pen / ink combination that keeps the customer's choices and
        obeys the compatibility rules (customer's own picks are shown as `fixed`)."""
        order = self.access.order(order_id)
        fixed = {f: getattr(order, f) for f, _ in self._FIELDS}
        papers = [self.catalog.paper(fixed["paper_type_id"])] if fixed["paper_type_id"] else self.catalog.papers()
        combos: list[dict] = []
        for paper in papers:
            if paper is None or not paper.is_active:
                continue
            for pen in self.catalog.pens_for_paper(paper.id):
                if fixed["pen_type_id"] and pen.id != fixed["pen_type_id"]:
                    continue
                for ink in self.catalog.inks_for_pen(pen.id):
                    if fixed["ink_color_id"] and ink.id != fixed["ink_color_id"]:
                        continue
                    combos.append({"paper_type_id": paper.id, "pen_type_id": pen.id, "ink_color_id": ink.id,
                                   "paper": paper.name, "pen": pen.name, "ink": ink.name})
        names = {f: (getattr(self.catalog, k)(fixed[f]).name if fixed[f] else None)
                 for f, k in (("paper_type_id", "paper"), ("pen_type_id", "pen"), ("ink_color_id", "ink"))}
        return {"suggest_enabled": order.workshop_suggest_materials, "fixed": {**fixed, **{f"{k}_name": v for k, v in names.items()}},
                "total": len(combos), "combos": combos[:limit]}

    # ---- read ----
    def get(self, quotation_id: int) -> Quotation:
        return self._quote(quotation_id)[0]

    def list_for_order(self, order_id: int) -> list[Quotation]:
        return self.quotes.list(self.access.order(order_id).id)

    # ---- adjustment (FR-31, BR-09) ----
    def adjust(self, quotation_id: int, adjusted_total: Decimal, reason: str) -> Quotation:
        q, order = self._quote(quotation_id, lock=True)
        self.access.order(order.id, write=True)
        if q.status not in (QuotationStatus.DRAFT, QuotationStatus.PENDING_APPROVAL):
            raise AppError(409, "QUOTATION_LOCKED", "Báo giá đã gửi, không thể điều chỉnh.")
        if len(q.price_snapshot.get("options", [])) > 1:
            raise AppError(422, "ADJUST_NOT_ALLOWED_MULTI_OPTION",
                           "Báo giá có nhiều phương án vật tư chưa hỗ trợ điều chỉnh giá tổng.")
        if not reason.strip():
            raise AppError(422, "REASON_REQUIRED", "Vui lòng ghi lý do điều chỉnh giá.")
        try:
            rules.validate_adjusted_total(adjusted_total)
        except ValueError as exc:
            raise AppError(422, "INVALID_AMOUNT", "Giá điều chỉnh phải là số dương, làm tròn đến 100đ.") from exc
        old = {"adjusted_total": str(q.adjusted_total) if q.adjusted_total is not None else None,
               "adjustment_status": q.adjustment_status.value}
        if adjusted_total == q.computed_total:
            return self.clear_adjustment(quotation_id)
        threshold = Decimal(q.price_snapshot.get("adjust_threshold_pct", "15"))
        decision = rules.classify_adjustment(q.computed_total, adjusted_total, threshold)
        q.adjusted_total, q.adjustment_reason = adjusted_total, reason.strip()
        if not decision.needs_manager:
            q.adjustment_status, q.status = AdjustmentStatus.WITHIN_THRESHOLD, QuotationStatus.DRAFT
            q.approved_by = q.approved_at = None
        else:
            q.adjustment_status, q.status = AdjustmentStatus.PENDING_MANAGER, QuotationStatus.PENDING_APPROVAL
            q.approved_by = q.approved_at = None
        self.session.flush()
        self.session.refresh(q)
        audit.record(self.session, actor_id=self.actor.id, action="PRICE_ADJUST", entity_type="quotation",
                     entity_id=q.id, old=old, new={"adjusted_total": str(adjusted_total),
                                                   "adjustment_pct": str(decision.pct),
                                                   "adjustment_status": q.adjustment_status.value},
                     reason=reason.strip(), ip=self.ip)
        return q

    def clear_adjustment(self, quotation_id: int) -> Quotation:
        q, order = self._quote(quotation_id, lock=True)
        self.access.order(order.id, write=True)
        if q.status not in (QuotationStatus.DRAFT, QuotationStatus.PENDING_APPROVAL):
            raise AppError(409, "QUOTATION_LOCKED", "Báo giá đã gửi, không thể điều chỉnh.")
        old = {"adjusted_total": str(q.adjusted_total) if q.adjusted_total is not None else None}
        q.adjusted_total = q.adjustment_reason = q.approved_by = q.approved_at = None
        q.adjustment_status, q.status = AdjustmentStatus.NONE, QuotationStatus.DRAFT
        self.session.flush()
        self.session.refresh(q)
        audit.record(self.session, actor_id=self.actor.id, action="PRICE_ADJUST_CLEAR", entity_type="quotation",
                     entity_id=q.id, old=old, ip=self.ip)
        return q

    # ---- Manager decision (UC-44) ----
    def _pending(self, quotation_id: int) -> Quotation:
        if not self.is_manager:
            raise AppError(403, "FORBIDDEN", "Chỉ Manager được duyệt điều chỉnh giá.")
        q, _ = self._quote(quotation_id, lock=True)
        if q.adjustment_status != AdjustmentStatus.PENDING_MANAGER or q.status != QuotationStatus.PENDING_APPROVAL:
            raise AppError(409, "NOTHING_TO_APPROVE", "Báo giá không có điều chỉnh nào đang chờ duyệt.")
        return q

    def approve_adjustment(self, quotation_id: int) -> Quotation:
        q = self._pending(quotation_id)
        q.adjustment_status, q.status = AdjustmentStatus.APPROVED, QuotationStatus.DRAFT
        q.approved_by, q.approved_at = self.actor.id, _now()
        self.session.flush()
        self.session.refresh(q)
        audit.record(self.session, actor_id=self.actor.id, action="PRICE_ADJUST_APPROVE", entity_type="quotation",
                     entity_id=q.id, new={"adjusted_total": str(q.adjusted_total)}, ip=self.ip)
        return q

    def reject_adjustment(self, quotation_id: int, reason: str) -> Quotation:
        if not reason.strip():
            raise AppError(422, "REASON_REQUIRED", "Vui lòng ghi lý do từ chối.")
        q = self._pending(quotation_id)
        rejected = q.adjusted_total
        q.adjusted_total = q.adjustment_reason = None
        q.adjustment_status, q.status = AdjustmentStatus.REJECTED, QuotationStatus.DRAFT
        q.approved_by, q.approved_at = self.actor.id, _now()
        self.session.flush()
        self.session.refresh(q)
        audit.record(self.session, actor_id=self.actor.id, action="PRICE_ADJUST_REJECT", entity_type="quotation",
                     entity_id=q.id, old={"adjusted_total": str(rejected)}, reason=reason.strip(), ip=self.ip)
        return q

    def pending_approvals(self, page: int, page_size: int) -> tuple[list[Quotation], int]:
        if not self.is_manager:
            raise AppError(403, "FORBIDDEN", "Chỉ Manager xem được hàng chờ duyệt giá.")
        return self.quotes.pending_approval(offset=(page - 1) * page_size, limit=page_size)

    # ---- cancel draft / send ----
    def cancel(self, quotation_id: int) -> Quotation:
        q, order = self._quote(quotation_id, lock=True)
        self.access.order(order.id, write=True)
        if q.status not in (QuotationStatus.DRAFT, QuotationStatus.PENDING_APPROVAL):
            raise AppError(409, "QUOTATION_LOCKED", "Chỉ hủy được báo giá chưa gửi.")
        q.status = QuotationStatus.CANCELLED
        self.session.flush()
        audit.record(self.session, actor_id=self.actor.id, action="QUOTATION_CANCEL", entity_type="quotation",
                     entity_id=q.id, ip=self.ip)
        return q

    def send(self, quotation_id: int) -> Quotation:
        q, order = self._quote(quotation_id, lock=True)
        order = self.access.order(order.id, write=True, lock=True)
        if q.status != QuotationStatus.DRAFT:
            raise AppError(409, "QUOTATION_NOT_SENDABLE", "Báo giá không ở trạng thái nháp.")
        if q.adjustment_status not in ADJUST_OK_TO_SEND:
            raise AppError(409, "APPROVAL_PENDING", "Điều chỉnh giá đang chờ Manager duyệt.")
        if order.order_status != OrderStatus.ACCEPTED:
            raise AppError(409, "ORDER_NOT_ACCEPTED", "Chỉ gửi báo giá khi đơn đã được tiếp nhận.")
        sketch = self.sketches.final(order.id)
        if sketch is None:                                                   # BR-22
            raise AppError(409, "SKETCH_REQUIRED", "Cần có phác thảo đã chốt trước khi gửi báo giá (BR-22).")
        if sketch.id != q.sketch_id:
            raise AppError(409, "SKETCH_CHANGED", "Phác thảo đã đổi sau khi lập báo giá; hãy hủy và lập báo giá mới.")
        if self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        policy = current_privacy_policy(self.catalog)
        now = _now()
        valid_days = _setting_int(self.catalog, "quotation_valid_days", DEFAULT_VALID_DAYS)
        q.sent_at, q.valid_until = now, now + timedelta(days=valid_days)
        q.status = QuotationStatus.SENT
        self.session.flush()
        self.session.refresh(q)
        path = f"orders/{order.id}/quotations/v{q.version}.pdf"
        self.storage.write(path, self._pdf(q, order), "application/pdf")
        q.file_url = path

        if q.eta and q.eta != order.eta:
            set_actor(self.session, self.actor.id, "Cập nhật ETA theo báo giá")
            order.eta = q.eta
        order.complexity = q.complexity
        consented = (order.privacy_accepted_at is not None and order.privacy_policy_version == policy["version"])
        set_actor(self.session, self.actor.id, f"Gửi báo giá v{q.version}")
        order.order_status = OrderStatus.QUOTED if consented else OrderStatus.AWAITING_PRIVACY
        self.session.flush()
        audit.record(self.session, actor_id=self.actor.id, action="QUOTATION_SEND", entity_type="quotation",
                     entity_id=q.id, new={"order_id": order.id, "version": q.version,
                                          "final_total": str(q.final_total)}, ip=self.ip)
        notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="MSG10", code=order.code,
                             total=str(q.final_total))
        return q

    def _pdf(self, q: Quotation, order: Order) -> bytes:
        customer = AccountRepository(self.session).get(order.customer_id)
        snap = q.price_snapshot
        multi = len(snap["options"]) > 1
        opts = []
        for o in snap["options"]:
            n = o["option"]
            rows = [(r["item"], r["calc"], r["amount"]) for r in q.line_items if r["option"] == n]
            total = int(q.final_total) if not multi else int(Decimal(o["total"]))
            if not multi and q.adjusted_total is not None:
                rows = rows[:-1] + [("Tổng sau điều chỉnh (chưa gồm phí giao hàng)", "", total)]
            opts.append(quotation_pdf.PdfOption(
                n, f"Phương án {n}: {o['paper']['name']} – {o['pen']['name']} – {o['ink']['name']}" if multi
                else "Chi tiết báo giá", rows, total,
                int(rules.min_deposit(Decimal(total), q.min_deposit_pct))))
        return quotation_pdf.render(quotation_pdf.QuotationDoc(
            order_code=order.code, version=q.version, customer_name=customer.full_name if customer else "",
            issued_at=q.sent_at, valid_until=q.valid_until, eta=q.eta, options=opts,
            min_deposit_pct=q.min_deposit_pct, adjusted=q.adjusted_total is not None, multi_option=multi))

    def pdf_url(self, quotation_id: int) -> str:
        q, _ = self._quote(quotation_id)
        if not q.file_url or self.storage is None:
            raise AppError(404, "PDF_NOT_AVAILABLE", "Báo giá chưa có file PDF (chưa gửi).")
        return self.storage.create_download_url(q.file_url, 600)


# ---------------------------------------------------------------------------------------------
# customer side
# ---------------------------------------------------------------------------------------------
VISIBLE = (QuotationStatus.SENT, QuotationStatus.APPROVED, QuotationStatus.CHANGES_REQUESTED, QuotationStatus.EXPIRED)
QUOTE_STAGES = {OrderStatus.QUOTED, OrderStatus.AWAITING_DEPOSIT, OrderStatus.CONFIRMED, OrderStatus.AWAITING_ACCEPTANCE,
                OrderStatus.AWAITING_FINAL_PAYMENT, OrderStatus.READY_TO_DELIVER, OrderStatus.DELIVERING,
                OrderStatus.COMPLETED, OrderStatus.CANCELLED}


class CustomerQuoteService:
    def __init__(self, session: Session, customer: Account, storage: ObjectStorage | None = None,
                 ip: str | None = None):
        self.session, self.customer, self.storage, self.ip = session, customer, storage, ip
        self.orders = OrderRepository(session)
        self.quotes = QuotationRepository(session)
        self.sketches = SketchRepository(session)
        self.catalog = CatalogRepository(session)

    def _order(self, order_id: int, *, lock: bool = False) -> Order:
        order = self.orders.get_owned(order_id, self.customer.id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        if lock:
            order = self.orders.get(order.id, lock=True)
            self.session.refresh(order)                            # loaded before the lock: see what others committed meanwhile
        if expire_and_persist(self.session, order) and lock:
            order = self.orders.get(order.id, lock=True)           # the commit released the row lock
            self.session.refresh(order)
        return order

    def policy(self) -> dict[str, Any]:
        return current_privacy_policy(self.catalog)

    # ---- privacy consent (FR-52, BR-25) ----
    def decide_privacy(self, order_id: int, accept: bool) -> Order:
        order = self._order(order_id, lock=True)
        if order.order_status != OrderStatus.AWAITING_PRIVACY:
            raise AppError(409, "PRIVACY_NOT_PENDING", "Đơn không đang chờ xác nhận chính sách riêng tư.")
        version = self.policy()["version"]
        now = _now()
        if accept:
            order.privacy_policy_version, order.privacy_accepted_at, order.privacy_declined_at = version, now, None
            set_actor(self.session, self.customer.id, "Khách chấp nhận chính sách riêng tư")
            order.order_status = OrderStatus.QUOTED
            action = "PRIVACY_ACCEPT"
        else:
            order.privacy_declined_at = now
            order.cancel_reason = "Khách từ chối chính sách riêng tư"
            q = self.quotes.live(order.id)
            if q is not None:
                q.status = QuotationStatus.CANCELLED
            set_actor(self.session, self.customer.id, "Khách từ chối chính sách riêng tư")
            order.order_status = OrderStatus.CANCELLED
            action = "PRIVACY_DECLINE"
        self.session.flush()
        audit.record(self.session, actor_id=self.customer.id, action=action, entity_type="order", entity_id=order.id,
                     new={"policy_version": version}, ip=self.ip, policy_version=version)   # chk_audit_privacy
        return order

    # ---- view (UC-15) ----
    def view(self, order_id: int) -> dict[str, Any]:
        order = self._order(order_id)
        if order.order_status == OrderStatus.AWAITING_PRIVACY:
            raise AppError(403, "PRIVACY_REQUIRED", "Vui lòng xác nhận chính sách riêng tư để xem phác thảo và báo giá.")
        if order.order_status not in QUOTE_STAGES or order.privacy_accepted_at is None:
            raise AppError(404, "QUOTATION_NOT_FOUND", "Đơn chưa có báo giá.")
        q = self.quotes.latest(order.id, VISIBLE)
        if q is None:
            raise AppError(404, "QUOTATION_NOT_FOUND", "Đơn chưa có báo giá.")
        sketch = self.sketches.get_by_id(q.sketch_id)
        return {"order": order, "quotation": q, "sketch": sketch}

    def sketch_image_urls(self, sketch) -> list[str]:
        """Customer-facing JPEGs of the sketch (what the customer judges before paying the deposit)."""
        if self.storage is None or sketch is None or not sketch.image_urls:
            return []
        return [self.storage.create_download_url(p, 600) for p in sketch.image_urls]

    def asset_urls(self, quotation: Quotation, sketch) -> tuple[str | None, list[str]]:
        if self.storage is None:
            return None, []
        pdf = self.storage.create_download_url(quotation.file_url, 600) if quotation.file_url else None
        previews: list[str] = []
        raw = self.storage.read(sketch.trajectory_uri) if sketch else None
        if raw:
            previews = [self.storage.create_download_url(p["preview_path"], 600)
                        for p in json.loads(raw).get("pages", []) if p.get("preview_path")]
        return pdf, previews

    def request_changes(self, order_id: int, note: str) -> Order:
        if not note.strip():
            raise AppError(422, "NOTE_REQUIRED", "Vui lòng nêu nội dung cần chỉnh.")
        order = self._order(order_id, lock=True)
        q = self.quotes.latest(order.id, (QuotationStatus.SENT,))
        if order.order_status != OrderStatus.QUOTED or q is None:
            raise AppError(409, "QUOTATION_NOT_OPEN", "Không có báo giá nào đang chờ phản hồi.")
        q.status, q.customer_note, q.customer_responded_at = QuotationStatus.CHANGES_REQUESTED, note.strip(), _now()
        set_actor(self.session, self.customer.id, "Khách yêu cầu chỉnh phác thảo/báo giá")
        order.order_status = OrderStatus.ACCEPTED
        self.session.flush()
        audit.record(self.session, actor_id=self.customer.id, action="QUOTATION_CHANGES_REQUESTED",
                     entity_type="quotation", entity_id=q.id, reason=note.strip(), ip=self.ip)
        return order


def option_summaries(q: Quotation) -> list[dict[str, Any]]:
    """Per-option totals for the customer; a single-option quote shows the (possibly adjusted) final total."""
    snap = q.price_snapshot.get("options", [])
    out = []
    for o in snap:
        total = q.final_total if len(snap) == 1 else Decimal(o["total"])
        out.append({"option": o["option"], "paper": o["paper"]["name"], "pen": o["pen"]["name"],
                    "ink": o["ink"]["name"], "total": int(total),
                    "min_deposit": int(rules.min_deposit(total, q.min_deposit_pct))})
    return out
