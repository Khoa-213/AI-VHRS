"""Technical Staff, step after writing: product photos and QC (UC-38, FR-49, BR-17, BR-21).

The job is WRITTEN. The technician uploads photos straight to storage (signed URL), registers each one with its kind
(OVERALL / CLOSE_UP / OTHER) and marks QC PASS or FAIL. `submit` hands the order to the customer (job and order production
PHOTO_UPLOADED, order AWAITING_ACCEPTANCE); `qc_fail` sends the job back to the Manager's queue (REWRITE_REQUIRED).

A photo is registered only after the server has read the uploaded object back and checked it, so an upload that never
finished leaves nothing in the table. The photo trigger `fn_photo_uploaded_guard` is the database's last word on BR-21.
"""
from __future__ import annotations

import uuid
from typing import Any

import cv2
import numpy as np

from app.core.errors import AppError
from app.db.session import set_actor
from app.domain import photo_rules as pr
from app.models.ops import JobStatus, PhotoKind, ProductionJob, ProductPhoto, QcResult
from app.models.order import Order, OrderStatus, ProductionStatus
from app.repositories.ops import PhotoRepository
from app.services import audit, notifications
from app.services.handwriting_image import sniff_mime
from app.services.technician import TechnicianJobService

PHOTO_URL_TTL = 1800                                  # seconds a signed photo link stays valid
_CONFLICT = {"REWRITE_LIMIT_REACHED", "PHOTO_REQUIREMENTS_NOT_MET"}


def rule_error(exc: pr.PhotoRuleError) -> AppError:
    return AppError(409 if exc.code in _CONFLICT else 422, exc.code, exc.message, exc.details)


def advance_after_writing(session, actor_id: int | None, job: ProductionJob, order: Order, dst: JobStatus, *,
                          order_status: OrderStatus | None, reason: str) -> None:
    """Job and order production status change together (BR-17, FR-25). The caller may set other order columns first:
    they are written by the same UPDATE, which the trigger judges as a whole (e.g. WRITTEN -> PHOTO_UPLOADED together
    with CONFIRMED -> AWAITING_ACCEPTANCE)."""
    if not pr.can_step(job.status, dst):
        raise AppError(409, "JOB_STATE_CONFLICT", f"Không chuyển job từ {job.status.value} sang {dst.value}.",
                       {"job_status": job.status.value})
    if order.production_status != ProductionStatus(job.status.value):
        raise AppError(409, "STATE_CONFLICT", "Trạng thái sản xuất của đơn không khớp job.",
                       {"job": job.status.value, "order_production": order.production_status.value})
    job.status = dst
    session.flush()
    set_actor(session, actor_id, reason)
    order.production_status = ProductionStatus(pr.production_name(dst))
    if order_status is not None:
        order.order_status = order_status
    session.flush()


def _dimensions(data: bytes) -> tuple[int | None, int | None]:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None, None
    return int(img.shape[1]), int(img.shape[0])


class ProductPhotoService(TechnicianJobService):
    def __init__(self, *args: Any, **kw: Any):
        super().__init__(*args, **kw)
        self.photos = PhotoRepository(self.session)

    # ------------------------------------------------------------------ guards
    def _photo_step(self, job_id: int) -> tuple[ProductionJob, Order]:
        """The job (own, locked) is WRITTEN and its order still waits for the photos."""
        job = self._job(job_id, lock=True)
        order = self._order(job)
        if order.order_status != OrderStatus.CONFIRMED:
            raise AppError(409, "ORDER_NOT_ACTIVE", "Đơn không còn ở trạng thái sản xuất.",
                           {"order_status": order.order_status.value})
        if job.status != JobStatus.WRITTEN:
            raise AppError(409, "JOB_STATE_CONFLICT", f"Chỉ thao tác ảnh sản phẩm khi job đang WRITTEN (hiện {job.status.value}).",
                           {"job_status": job.status.value, "allowed": [JobStatus.WRITTEN.value]})
        return job, order

    def _max_bytes(self) -> int:
        return int(self.catalog.setting("max_upload_mb", 20)) * 1024 * 1024

    # ------------------------------------------------------------------ reads
    def list_photos(self, job_id: int) -> list[ProductPhoto]:
        return self.photos.live(self._job(job_id).id)

    def to_out(self, row: ProductPhoto) -> dict[str, Any]:
        url = None
        if self.storage is not None:
            try:
                url = self.storage.create_download_url(row.url, PHOTO_URL_TTL)
            except AppError:
                url = None                       # a link is a convenience; the record is still valid
        return {"id": row.id, "job_id": row.job_id, "kind": row.kind, "qc_result": row.qc_result, "qc_note": row.qc_note,
                "created_at": row.created_at, "url": url, "url_expires_in": PHOTO_URL_TTL}

    # ------------------------------------------------------------------ upload
    def request_upload(self, job_id: int, mime_type: str, size_bytes: int):
        job, order = self._photo_step(job_id)
        try:
            pr.check_upload_request(mime_type, size_bytes, self._max_bytes(), len(self.photos.live(job.id)))
        except pr.PhotoRuleError as exc:
            raise rule_error(exc) from exc
        key = f"{uuid.uuid4().hex}.{pr.extension(mime_type)}"
        return key, self._storage().create_upload_target(pr.object_path(order.id, job.id, key))

    def register(self, job_id: int, key: str, kind: PhotoKind, qc_result: QcResult | None,
                 qc_note: str | None) -> ProductPhoto:
        job, order = self._photo_step(job_id)
        if not pr.is_valid_key(key):
            raise AppError(422, "INVALID_PHOTO_KEY", "photo_key không hợp lệ.")
        path = pr.object_path(order.id, job.id, key)
        existing = self.photos.by_path(job.id, path)
        if existing is not None:                                   # the same call twice is harmless
            if existing.deleted_at is not None:
                raise AppError(409, "PHOTO_REMOVED", "Ảnh này đã bị xoá, hãy tải lên lại.")
            return existing
        if len(self.photos.live(job.id)) >= pr.MAX_PHOTOS_PER_JOB:
            raise rule_error(pr.PhotoRuleError("TOO_MANY_PHOTOS", f"Mỗi job tối đa {pr.MAX_PHOTOS_PER_JOB} ảnh."))
        if qc_result is not None:
            try:
                pr.check_qc_note(qc_result.value, qc_note)
            except pr.PhotoRuleError as exc:
                raise rule_error(exc) from exc
        store = self._storage()
        data = store.read(path)
        if data is None:
            raise AppError(409, "UPLOAD_NOT_FOUND", "Chưa nhận được ảnh. Hãy tải lên rồi xác nhận lại.")
        width, height = _dimensions(data)
        try:
            pr.check_image(sniff_mime(data), len(data), self._max_bytes(), width, height)
        except pr.PhotoRuleError as exc:
            self._drop_object(path)
            raise rule_error(exc) from exc                         # nothing was registered, the bad object is gone
        row = self.photos.add(ProductPhoto(order_id=order.id, job_id=job.id, uploaded_by=self.tech.id, kind=kind, url=path,
                                           qc_result=qc_result, qc_note=(qc_note or None)))
        audit.record(self.session, actor_id=self.tech.id, action="JOB_PHOTO_ADD", entity_type="production_job",
                     entity_id=job.id, new={"photo_id": row.id, "kind": kind.value, "width": width, "height": height}, ip=self.ip)
        return row

    def set_qc(self, job_id: int, photo_id: int, result: QcResult, note: str | None) -> ProductPhoto:
        job, _ = self._photo_step(job_id)
        row = self.photos.get(job.id, photo_id)
        if row is None:
            raise AppError(404, "PHOTO_NOT_FOUND", "Không tìm thấy ảnh.")
        try:
            pr.check_qc_note(result.value, note)
        except pr.PhotoRuleError as exc:
            raise rule_error(exc) from exc
        row.qc_result, row.qc_note = result, (note or None)
        self.session.flush()
        return row

    def remove(self, job_id: int, photo_id: int) -> None:
        job, _ = self._photo_step(job_id)
        row = self.photos.get(job.id, photo_id)
        if row is None:
            raise AppError(404, "PHOTO_NOT_FOUND", "Không tìm thấy ảnh.")
        self.photos.soft_delete(row)
        self._drop_object(row.url)
        audit.record(self.session, actor_id=self.tech.id, action="JOB_PHOTO_REMOVE", entity_type="production_job",
                     entity_id=job.id, new={"photo_id": photo_id}, ip=self.ip)

    def _drop_object(self, path: str) -> None:
        if self.storage is not None:
            try:
                self.storage.delete(path)
            except Exception:                                      # an orphan object is harmless; retention purges it (BR-23)
                pass

    # ------------------------------------------------------------------ hand over to the customer / back to the queue
    def submit(self, job_id: int) -> ProductionJob:
        job, order = self._photo_step(job_id)
        live = self.photos.live(job.id)
        try:
            pr.check_ready_for_submission([pr.PhotoView(p.kind.value, p.qc_result.value if p.qc_result else None) for p in live])
        except pr.PhotoRuleError as exc:
            raise rule_error(exc) from exc
        advance_after_writing(self.session, self.tech.id, job, order, JobStatus.PHOTO_UPLOADED,
                              order_status=OrderStatus.AWAITING_ACCEPTANCE, reason="Đã tải ảnh sản phẩm, QC đạt")
        audit.record(self.session, actor_id=self.tech.id, action="JOB_PHOTOS_SUBMIT", entity_type="production_job",
                     entity_id=job.id, new={"order_id": order.id, "photos": len(live)}, ip=self.ip)
        notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="MSG12", code=order.code)
        return job

    def qc_fail(self, job_id: int, note: str) -> ProductionJob:
        job, order = self._photo_step(job_id)
        try:
            pr.check_qc_note("FAIL", note)
        except pr.PhotoRuleError as exc:
            raise rule_error(exc) from exc
        advance_after_writing(self.session, self.tech.id, job, order, JobStatus.REWRITE_REQUIRED, order_status=None,
                              reason=f"QC không đạt: {note}"[:200])
        audit.record(self.session, actor_id=self.tech.id, action="JOB_QC_FAIL", entity_type="production_job",
                     entity_id=job.id, new={"order_id": order.id}, reason=note, ip=self.ip)
        notifications.notify(account_id=job.scheduled_by, order_id=order.id, msg_code="QC_FAILED", code=order.code)
        return job
