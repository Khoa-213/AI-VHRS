"""Service G for a job's product photos: compare a photo of the written sheet with the approved sketch and keep the result.

The result is a second opinion with numbers (see `quality_eval`); the technician's QC verdict on the photo is not touched.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from app.core.errors import AppError
from app.models.account import RoleCode
from app.models.ops import ProductionJob, ProductPhoto, QualityEvaluation
from app.repositories.ops import PhotoRepository
from app.services import audit, quality_eval
from app.services.stroke_ai import trajectory as tj
from app.services.technician import TechnicianJobService

OVERLAY_TTL = 1800
ADVISORY = ("Chỉ để tham khảo: số đo mm giả định tờ giấy phẳng và chưa hiệu chuẩn bằng thước; ngưỡng đạt/không đạt là mặc định chưa kiểm chứng. "
            "Quyết định chất lượng vẫn là của kỹ thuật viên.")


class QualityService(TechnicianJobService):
    def __init__(self, *args: Any, **kw: Any):
        super().__init__(*args, **kw)
        self.photos = PhotoRepository(self.session)

    def _store(self):
        if self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        return self.storage

    def evaluate(self, job_id: int, photo_id: int, page_no: int) -> QualityEvaluation:
        job = self._job(job_id, lock=True)
        photo: ProductPhoto | None = self.photos.get(job.id, photo_id)
        if photo is None:
            raise AppError(404, "PHOTO_NOT_FOUND", "Không tìm thấy ảnh.")
        if not job.package_uri:
            raise AppError(409, "NO_APPROVED_SKETCH", "Job chưa có gói phác thảo đã duyệt để so sánh.")
        store = self._store()
        raw = store.read(job.package_uri)
        data = store.read(photo.url)
        if raw is None or data is None:
            raise AppError(409, "FILE_MISSING", "Không đọc được ảnh hoặc file phác thảo từ kho lưu trữ.")
        pages = tj.parse(json.loads(raw))
        if not 1 <= page_no <= len(pages):
            raise AppError(422, "PAGE_OUT_OF_RANGE", f"Phác thảo có {len(pages)} trang.", {"pages": len(pages)})
        order = self._order(job, lock=False)
        pen = self.catalog.pen(order.pen_type_id) if order.pen_type_id else None
        width = float(pen.stroke_width_mm) if pen and pen.stroke_width_mm else 0.5
        res = quality_eval.evaluate(data, pages[page_no - 1], stroke_width_mm=width)            # raises AppError (422) when it cannot measure
        overlay = None
        if res.overlay_jpeg:
            overlay = f"{photo.url.rsplit('.', 1)[0]}_overlay_p{page_no}.jpg"
            store.write(overlay, res.overlay_jpeg, "image/jpeg")
            photo.overlay_url = overlay
        row = QualityEvaluation(photo_id=photo.id, job_id=job.id, order_id=order.id, sketch_id=job.sketch_id, page_no=page_no,
                                method=quality_eval.METHOD, verdict=res.code, metrics=res.as_dict(), overlay_path=overlay,
                                created_by=self.tech.id)
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        audit.record(self.session, actor_id=self.tech.id, action="QUALITY_EVALUATE", entity_type="production_job", entity_id=job.id,
                     new={"photo_id": photo.id, "verdict": res.code, "coverage_pct": res.metrics["coverage_pct"],
                          "chamfer_mm": res.metrics["chamfer_mm"]}, ip=self.ip)
        return row

    def list(self, job_id: int) -> list[QualityEvaluation]:
        if self.tech.role.code == RoleCode.MANAGER.value:           # the Manager reads any job; the technician only their own (BR-19)
            job = self.session.get(ProductionJob, job_id)
            if job is None:
                raise AppError(404, "JOB_NOT_FOUND", "Không tìm thấy job.")
        else:
            job = self._job(job_id)
        return list(self.session.scalars(select(QualityEvaluation).where(QualityEvaluation.job_id == job.id)
                                         .order_by(QualityEvaluation.id.desc())))

    def to_out(self, row: QualityEvaluation) -> dict[str, Any]:
        url = None
        if self.storage is not None and row.overlay_path:
            try:
                url = self.storage.create_download_url(row.overlay_path, OVERLAY_TTL)
            except AppError:
                url = None
        return {"id": row.id, "photo_id": row.photo_id, "job_id": row.job_id, "page": row.page_no, "method": row.method,
                "verdict": row.verdict, "metrics": row.metrics, "overlay_url": url, "created_at": row.created_at, "advisory": ADVISORY}
