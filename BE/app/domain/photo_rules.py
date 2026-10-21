"""Pure rules for the product-photo step and the customer's acceptance (UC-18, UC-38, FR-28, FR-49, BR-13, BR-21). No DB, no I/O.

After the robot has written (job WRITTEN) the Technical Staff uploads photos of the real product and marks each one
QC PASS / FAIL. With at least two photos (one OVERALL, one CLOSE_UP) all passing, the job moves to PHOTO_UPLOADED and the
order to AWAITING_ACCEPTANCE (BR-17, BR-21). The customer then accepts, or asks for ONE free rewrite (BR-13); with no answer
the order is accepted by itself after `auto_accept_days` (FR-28).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.models.ops import JobStatus


class PhotoRuleError(ValueError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


# ---------------------------------------------------------------------------------------------- limits
# ASSUMPTIONS (the SRS only says ">= 2 photos, overall + close-up, QC passed"): kept here so the workshop can change them.
ALLOWED_MIMES = ("image/jpeg", "image/png")
MAX_PHOTOS_PER_JOB = 10
MIN_LONG_SIDE_PX = 1280                 # a close-up of ink lines that is smaller than this cannot be judged
DEFAULT_AUTO_ACCEPT_DAYS = 7            # FR-28 / SRS 5.2 (system_settings.auto_accept_days)
REWRITE_REASONS = ("WORKSHOP_ERROR", "DIFFERS_FROM_SKETCH")   # BR-13: the two causes that earn the free rewrite
_EXT = {"image/jpeg": "jpg", "image/png": "png"}
_KEY = re.compile(r"^[0-9a-f]{32}\.(jpg|png)$")

# ---------------------------------------------------------------------------------------------- job transitions of this step
# Not the Technician's own moves (those are in job_rules.TECH_TRANSITIONS): handing the job to the customer, and back.
STEP_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.WRITTEN: frozenset({JobStatus.PHOTO_UPLOADED, JobStatus.REWRITE_REQUIRED}),     # submit photos / QC failed
    JobStatus.PHOTO_UPLOADED: frozenset({JobStatus.DONE, JobStatus.REWRITE_REQUIRED}),        # accepted / customer rewrite
}


def can_step(src: JobStatus, dst: JobStatus) -> bool:
    return dst in STEP_TRANSITIONS.get(src, frozenset())


def production_name(job_status: JobStatus) -> str:
    """The order's production status that mirrors a job status (BR-17); only DONE is named differently."""
    return "FINISHED" if job_status == JobStatus.DONE else job_status.value


# ---------------------------------------------------------------------------------------------- upload
def extension(mime: str) -> str:
    return _EXT[mime]


def is_valid_key(key: str) -> bool:
    return bool(_KEY.match(key))


def object_path(order_id: int, job_id: int, key: str) -> str:
    """Where a product photo lives in storage. Built on the server so a client can never point at another object."""
    return f"orders/{order_id}/product/{job_id}/{key}"


def check_upload_request(mime: str, size_bytes: int, max_bytes: int, live_count: int) -> None:
    if mime not in ALLOWED_MIMES:
        raise PhotoRuleError("INVALID_PHOTO", "Ảnh sản phẩm phải là jpg hoặc png.")
    if size_bytes <= 0 or size_bytes > max_bytes:
        raise PhotoRuleError("FILE_TOO_LARGE", f"Ảnh không được quá {max_bytes // (1024 * 1024)} MB.")
    if live_count >= MAX_PHOTOS_PER_JOB:
        raise PhotoRuleError("TOO_MANY_PHOTOS", f"Mỗi job tối đa {MAX_PHOTOS_PER_JOB} ảnh.")


def check_image(real_mime: str | None, size_bytes: int, max_bytes: int, width: int | None, height: int | None) -> None:
    """The uploaded object itself: real type from its bytes (never the client's word), size, and a readable resolution."""
    if real_mime not in ALLOWED_MIMES or not width or not height:
        raise PhotoRuleError("INVALID_PHOTO", "Tệp không phải ảnh jpg/png hợp lệ.")
    if size_bytes > max_bytes:
        raise PhotoRuleError("FILE_TOO_LARGE", f"Ảnh không được quá {max_bytes // (1024 * 1024)} MB.")
    if max(width, height) < MIN_LONG_SIDE_PX:
        raise PhotoRuleError("PHOTO_TOO_SMALL", f"Ảnh quá nhỏ ({width}x{height}); cạnh dài cần ít nhất {MIN_LONG_SIDE_PX}px.",
                             {"width": width, "height": height, "min_long_side": MIN_LONG_SIDE_PX})


# ---------------------------------------------------------------------------------------------- BR-21
@dataclass(frozen=True)
class PhotoView:
    kind: str                 # OVERALL | CLOSE_UP | OTHER
    qc_result: str | None     # PASS | FAIL | None (not checked yet)


def check_ready_for_submission(photos: list[PhotoView]) -> None:
    """BR-21: at least two photos, an OVERALL and a CLOSE_UP among them, every live photo checked and passed."""
    missing = [k for k in ("OVERALL", "CLOSE_UP") if not any(p.kind == k for p in photos)]
    failed = sum(1 for p in photos if p.qc_result == "FAIL")
    unchecked = sum(1 for p in photos if p.qc_result is None)
    if len(photos) < 2 or missing or failed or unchecked:
        raise PhotoRuleError(
            "PHOTO_REQUIREMENTS_NOT_MET",
            "Cần ít nhất 2 ảnh (toàn cảnh và cận cảnh) và mọi ảnh phải được đánh dấu QC đạt (BR-21).",
            {"photos": len(photos), "missing_kinds": missing, "failed": failed, "unchecked": unchecked})


def check_qc_note(result: str, note: str | None) -> None:
    if result == "FAIL" and len((note or "").strip()) < 3:
        raise PhotoRuleError("QC_NOTE_REQUIRED", "Ảnh không đạt QC cần ghi chú lý do.")


# ---------------------------------------------------------------------------------------------- acceptance (FR-28, BR-13)
def acceptance_deadline(awaiting_since: datetime, auto_accept_days: int) -> datetime:
    return awaiting_since + timedelta(days=auto_accept_days)


def is_overdue(awaiting_since: datetime | None, now: datetime, auto_accept_days: int) -> bool:
    return awaiting_since is not None and now >= acceptance_deadline(awaiting_since, auto_accept_days)


def check_rewrite_allowed(free_rewrite_used: bool) -> None:
    """Only ONE free rewrite per order (project owner, 2026-10-18); asking again is refused with a clear message."""
    if free_rewrite_used:
        raise PhotoRuleError("REWRITE_LIMIT_REACHED",
                             "Đơn đã dùng lượt viết lại miễn phí. Vui lòng liên hệ xưởng để được báo giá viết lại.")


def check_rewrite_reason(code: str, note: str | None) -> None:
    if code not in REWRITE_REASONS:
        raise PhotoRuleError("INVALID_REWRITE_REASON", "Lý do viết lại không hợp lệ.", {"allowed": list(REWRITE_REASONS)})
    if len((note or "").strip()) < 5:
        raise PhotoRuleError("REWRITE_NOTE_REQUIRED", "Hãy mô tả điểm chưa đạt (ít nhất 5 ký tự).")
