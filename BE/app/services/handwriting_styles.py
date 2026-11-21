"""OT-2 Phase O2 (owner approved 2026-11-20, docs/OT2_LEARNED_STYLE_PLAN.md section 9): a customer's handwriting style built
from the fixed sample sheet (`stroke_ai/sample_sheet.py`).

Customer: create a style (name, right to use the handwriting confirmed: BR-23, keep consent: NFR-12) -> DRAFT; download the
sheet; upload a photo of each page (signed upload URL, then confirm: the page is read on the server, the photo never goes to
an AI provider) -> coverage and the boxes with problems; submit -> PENDING_REVIEW. A page can be photographed again while the
style is DRAFT (its row is replaced, the old photo deleted). Deleting a style marks it DELETED and removes its photos.
Manager (FR-42, the existing review of styles): sees every box (traced strokes, its photo on request), drops bad samples,
approves (the glyph set is written to storage: `glyph_set_uri`, `coverage_pct`) or rejects with a reason.
The style API stays open while OT-2 is switched off (O2-c): it only stores the person's own handwriting; an OT-2 order is still
refused until the owner turns the order type on.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.integrations.storage import ObjectStorage
from app.models.account import Account
from app.models.order import HandwritingStyle, HandwritingStylePage, StyleStatus
from app.repositories.catalog import CatalogRepository
from app.services import audit
from app.services.handwriting_image import sniff_mime
from app.services.stroke_ai import sample_sheet as sheet

_EXT = {"image/jpeg": "jpg", "image/png": "png"}
_UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
MAX_STYLES_IN_PROGRESS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _path(style_id: int, page_no: int, upload_id: str, mime: str) -> str:
    return f"styles/{style_id}/p{page_no}-{upload_id}.{_EXT[mime]}"


def page_results(session: Session, style_id: int) -> list[HandwritingStylePage]:
    return list(session.scalars(select(HandwritingStylePage).where(HandwritingStylePage.style_id == style_id)
                                .order_by(HandwritingStylePage.page_no)))


def describe(session: Session, row: HandwritingStyle, *, with_strokes: bool = False) -> dict[str, Any]:
    pages = page_results(session, row.id)
    rejected = set(row.rejected_samples or [])
    s = sheet.summary([p.read_result for p in pages], rejected)
    out = {"id": row.id, "owner_id": row.owner_id, "name": row.name, "status": row.status, "sheet_version": row.sheet_version,
           "right_to_use_confirmed": row.right_to_use_confirmed, "keep_consent": row.keep_consent,
           "coverage_pct": float(row.coverage_pct) if row.coverage_pct is not None else s["coverage_pct"],
           "missing": s["missing"], "issues": s["issues"], "review_note": row.review_note,
           "rejected_samples": sorted(rejected), "submitted_at": row.submitted_at, "approved_at": row.approved_at,
           "created_at": row.created_at, "pages_total": sheet.pages(),
           "pages": [{"page_no": p.page_no, "uploaded_at": p.uploaded_at,
                      "cells": {k: sum(1 for c in p.read_result["cells"] if c["status"] == k)
                                for k in ("OK", "EMPTY", "OVERFLOW", "NOISY", "MARKS_UNCLEAR")}} for p in pages]}
    if with_strokes:
        out["cells"] = [{**{k: v for k, v in c.items()}, "page_no": p.page_no, "rejected": c["cell"] in rejected}
                        for p in pages for c in p.read_result["cells"]]
    return out


class StyleService:
    def __init__(self, session: Session, customer: Account, storage: ObjectStorage | None, ip: str | None = None):
        self.s, self.customer, self.storage, self.ip = session, customer, storage, ip
        self.catalog = CatalogRepository(session)

    def _audit(self, action: str, style_id: int, old: dict | None = None, new: dict | None = None) -> None:
        audit.record(self.s, actor_id=self.customer.id, action=action, entity_type="handwriting_style", entity_id=style_id,
                     old=old, new=new, ip=self.ip)

    def _store(self) -> ObjectStorage:
        if self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        return self.storage

    def _own(self, style_id: int, *, lock: bool = False) -> HandwritingStyle:
        q = select(HandwritingStyle).where(HandwritingStyle.id == style_id, HandwritingStyle.owner_id == self.customer.id,
                                           HandwritingStyle.status != StyleStatus.DELETED)
        row = self.s.scalar(q.with_for_update() if lock else q)
        if row is None:
            raise AppError(404, "STYLE_NOT_FOUND", "Không tìm thấy bộ nét.")
        return row

    def _draft(self, style_id: int) -> HandwritingStyle:
        row = self._own(style_id, lock=True)
        if row.status != StyleStatus.DRAFT:
            raise AppError(409, "STYLE_NOT_DRAFT", "Bộ nét đã gửi duyệt; không sửa được nữa.")
        return row

    # ---------------------------------------------------------------------------------------------------------------
    def create(self, name: str, right_to_use_confirmed: bool, keep_consent: bool) -> HandwritingStyle:
        if not right_to_use_confirmed:                                                    # BR-23
            raise AppError(422, "RIGHT_TO_USE_REQUIRED", "Cần xác nhận bạn có quyền sử dụng nét chữ này.")
        drafts = self.s.scalar(select(func.count()).select_from(HandwritingStyle).where(
            HandwritingStyle.owner_id == self.customer.id, HandwritingStyle.status == StyleStatus.DRAFT))
        if (drafts or 0) >= MAX_STYLES_IN_PROGRESS:
            raise AppError(422, "TOO_MANY_DRAFT_STYLES", f"Đã có {MAX_STYLES_IN_PROGRESS} bộ nét đang làm dở.")
        row = HandwritingStyle(owner_id=self.customer.id, name=name.strip(), status=StyleStatus.DRAFT,
                               right_to_use_confirmed=True, keep_consent=keep_consent, sheet_version=sheet.SHEET_VERSION,
                               rejected_samples=[])
        self.s.add(row)
        self.s.flush()
        self._audit("STYLE_CREATE", row.id, new={"name": row.name, "keep_consent": keep_consent})
        return row

    def mine(self) -> list[HandwritingStyle]:
        return list(self.s.scalars(select(HandwritingStyle).where(
            HandwritingStyle.owner_id == self.customer.id, HandwritingStyle.status != StyleStatus.DELETED)
            .order_by(HandwritingStyle.created_at.desc(), HandwritingStyle.id.desc())))

    def get(self, style_id: int) -> HandwritingStyle:
        return self._own(style_id)

    def request_upload(self, style_id: int, page_no: int, mime_type: str, size_bytes: int) -> tuple[str, Any]:
        row = self._draft(style_id)
        if not 1 <= page_no <= sheet.pages():
            raise AppError(422, "SHEET_PAGE_INVALID", f"Phiếu có {sheet.pages()} trang.")
        if mime_type not in _EXT:
            raise AppError(422, "INVALID_FILE", "Ảnh phiếu phải là jpg hoặc png.")
        max_mb = int(self.catalog.setting("max_upload_mb"))
        if size_bytes > max_mb * 1024 * 1024:
            raise AppError(422, "FILE_TOO_LARGE", f"File vượt quá {max_mb} MB.")
        upload_id = uuid.uuid4().hex
        return upload_id, self._store().create_upload_target(_path(row.id, page_no, upload_id, mime_type))

    def confirm_upload(self, style_id: int, page_no: int, upload_id: str, mime_type: str) -> HandwritingStylePage:
        row = self._draft(style_id)
        if not _UPLOAD_ID.match(upload_id or "") or mime_type not in _EXT or not 1 <= page_no <= sheet.pages():
            raise AppError(422, "INVALID_UPLOAD", "Mã tải lên không hợp lệ.")
        store, path = self._store(), _path(row.id, page_no, upload_id, mime_type)
        data = store.read(path)
        if data is None:
            raise AppError(409, "UPLOAD_NOT_FOUND", "Chưa nhận được file. Vui lòng tải lên rồi xác nhận lại.")
        max_mb = int(self.catalog.setting("max_upload_mb"))
        if sniff_mime(data) not in _EXT or len(data) > max_mb * 1024 * 1024:
            store.delete(path)
            raise AppError(422, "INVALID_FILE", "Ảnh phiếu phải là jpg hoặc png và không quá dung lượng cho phép.")
        try:
            result = sheet.read_page(data, page_no)
        except AppError:
            store.delete(path)                     # a photo that is not a readable page of the sheet is not kept
            raise
        old = self.s.scalar(select(HandwritingStylePage).where(HandwritingStylePage.style_id == row.id,
                                                               HandwritingStylePage.page_no == page_no))
        if old is not None:
            old_path = old.file_url
            old.file_url, old.mime_type, old.read_result, old.uploaded_at = path, sniff_mime(data), result, _now()
            page = old
        else:
            old_path = None
            page = HandwritingStylePage(style_id=row.id, page_no=page_no, file_url=path, mime_type=sniff_mime(data),
                                        read_result=result)
            self.s.add(page)
        row.updated_at = _now()
        self.s.flush()
        if old_path and old_path != path:
            store.delete(old_path)
        counts = {k: sum(1 for c in result["cells"] if c["status"] == k) for k in ("OK", "EMPTY", "OVERFLOW", "NOISY",
                                                                                    "MARKS_UNCLEAR")}
        self._audit("STYLE_PAGE_UPLOAD", row.id, new={"page_no": page_no, "cells": counts})
        return page

    def submit(self, style_id: int) -> HandwritingStyle:
        row = self._draft(style_id)
        have = {p.page_no for p in page_results(self.s, row.id)}
        missing = [n for n in range(1, sheet.pages() + 1) if n not in have]
        if missing:
            raise AppError(422, "SHEET_PAGES_MISSING", f"Còn thiếu trang {', '.join(map(str, missing))} của phiếu.",
                           details={"missing_pages": missing})
        s = sheet.summary([p.read_result for p in page_results(self.s, row.id)])
        row.status, row.submitted_at, row.updated_at = StyleStatus.PENDING_REVIEW, _now(), _now()
        row.coverage_pct = s["coverage_pct"]
        self.s.flush()
        self._audit("STYLE_SUBMIT", row.id, {"status": "DRAFT"}, {"status": "PENDING_REVIEW", "coverage_pct": s["coverage_pct"]})
        return row

    def delete(self, style_id: int) -> None:
        row = self._own(style_id, lock=True)
        old = row.status.value
        store = self.storage
        for p in page_results(self.s, row.id):
            if store is not None:
                store.delete(p.file_url)
            self.s.delete(p)
        if row.glyph_set_uri and store is not None:
            store.delete(row.glyph_set_uri)
        row.status, row.glyph_set_uri, row.updated_at = StyleStatus.DELETED, None, _now()
        self.s.flush()
        self._audit("STYLE_DELETE", row.id, {"status": old}, {"status": "DELETED"})


# -------------------------------------------------------------------------------------------------------------------
# Manager review (FR-42): used by manager_catalog
# -------------------------------------------------------------------------------------------------------------------
def toggle_sample(session: Session, row: HandwritingStyle, sample_id: str, rejected: bool) -> list[str]:
    cells = {c["cell"]: c for p in page_results(session, row.id) for c in p.read_result["cells"]}
    cell_id, _, mark = sample_id.partition(":")
    c = cells.get(cell_id)
    if c is None or (mark and mark not in {m["mark"] for m in c.get("marks", [])}):
        raise AppError(404, "SAMPLE_NOT_FOUND", "Không có mẫu này trong bộ nét.")
    cur = set(row.rejected_samples or [])
    (cur.add if rejected else cur.discard)(sample_id)
    row.rejected_samples = sorted(cur)
    row.updated_at = _now()
    return row.rejected_samples


def write_glyph_set(session: Session, row: HandwritingStyle, storage: ObjectStorage | None) -> dict:
    pages = page_results(session, row.id)
    if not pages:                                   # a style from before O2 (no sheet): nothing to build
        return {}
    if storage is None:
        raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
    gs = sheet.glyph_set([p.read_result for p in pages], set(row.rejected_samples or []))
    path = f"styles/{row.id}/glyphs-{uuid.uuid4().hex[:12]}.json"
    storage.write(path, json.dumps(gs, ensure_ascii=False).encode("utf-8"), "application/json")
    row.glyph_set_uri, row.coverage_pct = path, gs["coverage_pct"]
    return gs


def cell_image(session: Session, storage: ObjectStorage | None, row: HandwritingStyle, cell_id: str) -> bytes:
    m = re.match(r"^p(\d+)c\d{2}$", cell_id or "")
    page = next((p for p in page_results(session, row.id) if m and p.page_no == int(m.group(1))), None)
    if page is None:
        raise AppError(404, "CELL_NOT_FOUND", "Không có ô này trong bộ nét.")
    if storage is None:
        raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
    data = storage.read(page.file_url)
    if data is None:
        raise AppError(410, "PHOTO_PURGED", "Ảnh phiếu đã bị xoá theo chính sách lưu trữ.")
    return sheet.cell_png(data, page.page_no, cell_id)
