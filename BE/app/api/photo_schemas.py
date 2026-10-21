"""Schemas for product photos, QC and the customer's acceptance (Phase 4b)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.ops import JobStatus, PhotoKind, QcResult


class PhotoUploadIn(BaseModel):
    mime_type: Literal["image/jpeg", "image/png"]
    size_bytes: int = Field(gt=0)


class PhotoUploadOut(BaseModel):
    photo_key: str = Field(description="Gửi lại ở bước đăng ký ảnh (`POST /technician/jobs/{id}/photos`).")
    upload_url: str
    method: str
    expires_in: int


class PhotoRegisterIn(BaseModel):
    photo_key: str = Field(min_length=36, max_length=40)
    kind: PhotoKind
    qc_result: QcResult | None = Field(default=None, description="Có thể đánh dấu QC ngay, hoặc dùng PATCH sau.")
    qc_note: str | None = Field(default=None, max_length=500)


class PhotoQcIn(BaseModel):
    qc_result: QcResult
    qc_note: str | None = Field(default=None, max_length=500, description="Bắt buộc khi FAIL.")


class QcFailIn(BaseModel):
    note: str = Field(min_length=3, max_length=500, description="Vì sao sản phẩm không đạt; job quay về hàng đợi xếp lại.")


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    job_id: int
    kind: PhotoKind
    qc_result: QcResult | None
    qc_note: str | None
    created_at: datetime
    url: str | None = None
    url_expires_in: int = 0


class WorkshopPhotoOut(PhotoOut):
    job_status: JobStatus


class CustomerPhotoOut(BaseModel):
    id: int
    kind: PhotoKind
    url: str | None
    url_expires_in: int


class ProductPhotosOut(BaseModel):
    order_status: str
    photos: list[CustomerPhotoOut]
    sketch_preview_url: str | None = Field(default=None, description="Ảnh phác thảo đã duyệt, để khách đối chiếu.")
    acceptance_due_at: datetime | None = Field(default=None, description="Hạn tự nghiệm thu (FR-28).")
    can_accept: bool
    can_request_rewrite: bool = Field(description="False khi đã dùng lượt viết lại miễn phí (BR-13).")
    free_rewrite_used: bool


class RewriteIn(BaseModel):
    reason_code: Literal["WORKSHOP_ERROR", "DIFFERS_FROM_SKETCH"] = Field(
        description="WORKSHOP_ERROR: lỗi do xưởng · DIFFERS_FROM_SKETCH: khác phác thảo đã duyệt (BR-13).")
    note: str = Field(min_length=5, max_length=1000, description="Mô tả điểm chưa đạt.")
