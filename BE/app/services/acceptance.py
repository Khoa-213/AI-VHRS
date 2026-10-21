"""Customer acceptance of the written product (UC-18, FR-28, BR-13) and the workshop's read of the photos.

AWAITING_ACCEPTANCE: the customer looks at the QC-passed photos and either
  * accepts  -> job DONE, production FINISHED, order AWAITING_FINAL_PAYMENT (BR-17), or
  * asks for a rewrite -> job REWRITE_REQUIRED, production REWRITE_REQUIRED, order back to CONFIRMED and into the
    Manager's scheduling queue. Only ONE rewrite is free (BR-13); the second request is refused with "contact the workshop".
Without an answer the order is accepted by itself after `system_settings.auto_accept_days` (default 7, FR-28). That is
evaluated lazily whenever the customer reads or acts on the order, like quotation expiry; the proactive scheduler (and
the reminder after 3 days) belong to Phase 5.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain import photo_rules as pr
from app.integrations.storage import ObjectStorage
from app.models.account import Account
from app.models.ops import JobStatus, ProductionJob, ProductPhoto, QcResult
from app.models.order import Order, OrderStatus
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import JobRepository, PhotoRepository
from app.repositories.orders import OrderRepository
from app.repositories.workshop import SketchRepository
from app.services import audit, notifications
from app.services.product_photos import PHOTO_URL_TTL, advance_after_writing, rule_error

# From the moment the photos exist the customer may look at them.
VISIBLE = (OrderStatus.AWAITING_ACCEPTANCE, OrderStatus.AWAITING_FINAL_PAYMENT, OrderStatus.READY_TO_DELIVER,
           OrderStatus.DELIVERING, OrderStatus.COMPLETED)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def signed(storage: ObjectStorage | None, path: str | None) -> str | None:
    if storage is None or not path:
        return None
    try:
        return storage.create_download_url(path, PHOTO_URL_TTL)
    except AppError:
        return None


class AcceptanceService:
    def __init__(self, session: Session, customer: Account, storage: ObjectStorage | None, ip: str | None = None):
        self.session, self.customer, self.storage, self.ip = session, customer, storage, ip
        self.orders = OrderRepository(session)
        self.jobs = JobRepository(session)
        self.photos = PhotoRepository(session)
        self.catalog = CatalogRepository(session)
        self.sketches = SketchRepository(session)

    # ------------------------------------------------------------------ helpers
    def _get(self, order_id: int) -> Order:
        order = self.orders.get_owned(order_id, self.customer.id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        return order

    def _lock(self, order_id: int) -> Order:
        """Row lock, then re-read: the object may already be in the session with values from before the lock."""
        order = self.orders.get(order_id, lock=True)
        self.session.refresh(order)
        return order

    def _days(self) -> int:
        return int(self.catalog.setting("auto_accept_days", pr.DEFAULT_AUTO_ACCEPT_DAYS))

    def _job_to_close(self, order: Order) -> ProductionJob:
        job = self.jobs.latest_in(order.id, (JobStatus.PHOTO_UPLOADED,), lock=True)
        if job is None:
            raise AppError(409, "STATE_CONFLICT", "Không tìm thấy job đã có ảnh cho đơn này.")
        return job

    def _close_accepted(self, order: Order, actor_id: int | None, *, auto: bool) -> None:
        job = self._job_to_close(order)
        order.accepted_product_at = _now()
        advance_after_writing(self.session, actor_id, job, order, JobStatus.DONE,
                              order_status=OrderStatus.AWAITING_FINAL_PAYMENT,
                              reason="Tự nghiệm thu do quá hạn" if auto else "Khách nghiệm thu sản phẩm")
        audit.record(self.session, actor_id=actor_id, action="ORDER_AUTO_ACCEPT" if auto else "ORDER_ACCEPT_PRODUCT",
                     entity_type="order", entity_id=order.id, new={"job_id": job.id}, ip=self.ip)
        if order.assigned_staff_id:
            notifications.notify(account_id=order.assigned_staff_id, order_id=order.id,
                                 msg_code="PRODUCT_AUTO_ACCEPTED" if auto else "PRODUCT_ACCEPTED", code=order.code)

    def settle_overdue(self, order: Order) -> bool:
        """Accept the order by itself when the customer let the deadline pass. True when it did (and committed)."""
        if order.order_status != OrderStatus.AWAITING_ACCEPTANCE:
            return False
        days = self._days()
        if not pr.is_overdue(order.awaiting_acceptance_at, _now(), days):
            return False
        locked = self._lock(order.id)
        if locked.order_status != OrderStatus.AWAITING_ACCEPTANCE or not pr.is_overdue(
                locked.awaiting_acceptance_at, _now(), days):
            return False                                   # someone answered meanwhile
        self._close_accepted(locked, None, auto=True)
        self.session.commit()                              # keep it even if this request goes on to answer 409 (S03)
        self.session.refresh(order)
        return True

    # ------------------------------------------------------------------ reads
    def view(self, order_id: int) -> dict[str, Any]:
        order = self._get(order_id)
        self.settle_overdue(order)
        if order.order_status not in VISIBLE:
            raise AppError(409, "PHOTOS_NOT_AVAILABLE", "Sản phẩm chưa có ảnh để xem.",
                           {"order_status": order.order_status.value})
        job = self.jobs.latest_in(order.id, (JobStatus.PHOTO_UPLOADED, JobStatus.DONE))
        rows = [p for p in self.photos.live(job.id) if p.qc_result == QcResult.PASS] if job else []
        sketch = self.sketches.final(order.id)
        awaiting = order.order_status == OrderStatus.AWAITING_ACCEPTANCE
        due = pr.acceptance_deadline(order.awaiting_acceptance_at, self._days()) if awaiting and order.awaiting_acceptance_at else None
        return {"order": order, "photos": [{"id": p.id, "kind": p.kind, "url": signed(self.storage, p.url),
                                            "url_expires_in": PHOTO_URL_TTL} for p in rows],
                "sketch_preview_url": signed(self.storage, sketch.preview_url) if sketch else None,
                "acceptance_due_at": due, "can_accept": awaiting,
                "can_request_rewrite": awaiting and not order.free_rewrite_used}

    # ------------------------------------------------------------------ UC-18
    def _awaiting(self, order_id: int) -> Order:
        order = self._get(order_id)
        if self.settle_overdue(order):
            raise AppError(409, "ACCEPTANCE_CLOSED", "Đã quá hạn nghiệm thu; đơn đã được tự nghiệm thu.")
        order = self._lock(order.id)
        if order.order_status != OrderStatus.AWAITING_ACCEPTANCE:
            raise AppError(409, "ORDER_NOT_AWAITING_ACCEPTANCE", "Đơn không ở bước chờ nghiệm thu.",
                           {"order_status": order.order_status.value})
        return order

    def accept(self, order_id: int) -> Order:
        order = self._awaiting(order_id)
        self._close_accepted(order, self.customer.id, auto=False)
        self.session.refresh(order)
        return order

    def request_rewrite(self, order_id: int, reason_code: str, note: str) -> Order:
        try:
            pr.check_rewrite_reason(reason_code, note)
        except pr.PhotoRuleError as exc:
            raise rule_error(exc) from exc
        order = self._awaiting(order_id)
        try:
            pr.check_rewrite_allowed(order.free_rewrite_used)           # BR-13: one free rewrite
        except pr.PhotoRuleError as exc:
            raise rule_error(exc) from exc
        job = self._job_to_close(order)
        order.free_rewrite_used = True
        advance_after_writing(self.session, self.customer.id, job, order, JobStatus.REWRITE_REQUIRED,
                              order_status=OrderStatus.CONFIRMED, reason=f"Khách yêu cầu viết lại: {note}"[:200])
        audit.record(self.session, actor_id=self.customer.id, action="ORDER_REWRITE_REQUEST", entity_type="order",
                     entity_id=order.id, new={"job_id": job.id, "reason_code": reason_code}, reason=note, ip=self.ip)
        for account_id in {job.scheduled_by, order.assigned_staff_id} - {None}:
            notifications.notify(account_id=account_id, order_id=order.id, msg_code="REWRITE_REQUESTED",
                                 code=order.code, reason_code=reason_code)
        self.session.refresh(order)
        return order


def workshop_photos(session: Session, order: Order, storage: ObjectStorage | None) -> list[dict[str, Any]]:
    """Every live photo of the order's jobs with its QC verdict, newest job first (Staff / Manager, read only)."""
    out: list[dict[str, Any]] = []
    for job in reversed(JobRepository(session).for_order(order.id)):
        for p in PhotoRepository(session).live(job.id):
            out.append({"id": p.id, "job_id": job.id, "job_status": job.status, "kind": p.kind, "qc_result": p.qc_result,
                        "qc_note": p.qc_note, "created_at": p.created_at, "url": signed(storage, p.url),
                        "url_expires_in": PHOTO_URL_TTL})
    return out
