"""Upgrade U5 (Q2 = A): the customer's studio, a draft that comes BEFORE an order.

* A draft holds what an order would hold (text + template + layout, or photographed originals; materials; quantity; options),
  as a JSON `content`. Every change - by the customer through the forms or by the AI assistant through its tools - is a new
  `studio_revisions` row; nothing is edited in place. Undo moves the cursor to the parent revision, redo to the newest child.
* The checks, the price estimate and the preview reuse the code the order and the workshop already use (text layout rules,
  catalog compatibility, PricingService, the stroke engine, the U2 visible AI mark and the U8 physical line), so what the
  studio says is what the order will get. The preview is AN ESTIMATE: the Staff still make the official sketch.
* "Send to the workshop" creates the order through OrderService (create, materials, text / images, submit), so every rule of
  the order (BR-03, BR-05, BR-07, order types switched off, MSG01) applies unchanged. From there the order state machine is
  untouched; the draft keeps the link (`order_id`) and the Staff can read its history and flags.
"""
from __future__ import annotations

import copy
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.domain import text_layout
from app.integrations.storage import ObjectStorage
from app.models.account import Account
from app.models.order import OrderInput, OrderInputKind, OrderType
from app.models.studio import StudioDraft, StudioRevision
from app.repositories.catalog import CatalogRepository
from app.repositories.orders import OrderRepository
from app.services import audit
from app.services.handwriting_image import analyze_image, sniff_mime
from app.services.orders import DEFAULTS as ORDER_DEFAULTS, OrderService, PricingService
from app.services.pricing import count_text_chars
from app.services.stroke_ai import engine, physical_mark, regions as rg, render_image, trajectory as tj, watermark

MODES = {"TEXT": OrderType.OT3_TEMPLATE, "RESTORE": OrderType.OT1_COPY_RESTORE}
MAX_REVISIONS = 300                       # per draft: the history is kept whole; past this the customer starts a new draft
MAX_TEXT = 20000                          # as TextInputIn
MAX_OPEN_DRAFTS = 20                      # per customer
PREVIEW_CODE = "XXXX-XXXX"                # U8 line on a preview: the real code is issued only when the Staff save a sketch
ALIGNMENTS = ("LEFT", "CENTER", "RIGHT", "JUSTIFY")
_EXT = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}
_IMAGE_ID = re.compile(r"^[0-9a-f]{32}\.(jpg|png|pdf)$")
EDITABLE_FIELDS = ("text", "template_id", "font_size_mm", "alignment", "layout", "canvas", "paper_type_id", "pen_type_id",
                   "ink_color_id", "workshop_suggest_materials", "quantity", "physical_watermark", "restoration_mode",
                   "customer_note", "title")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def empty_content(mode: str) -> dict[str, Any]:
    ot1 = mode == "RESTORE"
    return {"order_type": MODES[mode].value, "quantity": 1, "text": "", "template_id": None, "font_size_mm": None,
            "alignment": None, "layout": None, "canvas": None, "paper_type_id": None, "pen_type_id": None,
            "ink_color_id": None, "workshop_suggest_materials": False, "physical_watermark": ot1,
            "restoration_mode": None, "customer_note": None, "images": [], "region_edits": []}


class StudioService:
    def __init__(self, session: Session, customer: Account, storage: ObjectStorage | None, ip: str | None = None):
        self.session, self.customer, self.storage, self.ip = session, customer, storage, ip
        self.catalog = CatalogRepository(session)

    # ------------------------------------------------------------------ access
    def get(self, draft_id: int, *, lock: bool = False) -> StudioDraft:
        q = select(StudioDraft).where(StudioDraft.id == draft_id, StudioDraft.customer_id == self.customer.id)
        draft = self.session.scalar(q.with_for_update() if lock else q)
        if draft is None:                                   # another customer's draft answers 404 (BR-02)
            raise AppError(404, "DRAFT_NOT_FOUND", "Không tìm thấy bản nháp.")
        return draft

    def get_open(self, draft_id: int) -> StudioDraft:
        draft = self.get(draft_id, lock=True)
        if draft.status != "OPEN":
            raise AppError(409, "DRAFT_CLOSED", "Bản nháp đã gửi xưởng hoặc đã bỏ, không sửa được nữa.")
        return draft

    def list(self, status: str | None) -> list[StudioDraft]:
        q = select(StudioDraft).where(StudioDraft.customer_id == self.customer.id)
        if status:
            q = q.where(StudioDraft.status == status)
        return list(self.session.scalars(q.order_by(StudioDraft.updated_at.desc()).limit(100)))

    def revision(self, draft: StudioDraft) -> StudioRevision:
        return self.session.get(StudioRevision, draft.current_revision_id)

    def content(self, draft: StudioDraft) -> dict[str, Any]:
        return copy.deepcopy(self.revision(draft).content)

    def revisions(self, draft: StudioDraft) -> list[StudioRevision]:
        return list(self.session.scalars(select(StudioRevision).where(StudioRevision.draft_id == draft.id)
                                         .order_by(StudioRevision.seq)))

    def _redo_target(self, draft: StudioDraft) -> StudioRevision | None:
        return self.session.scalar(select(StudioRevision).where(
            StudioRevision.draft_id == draft.id, StudioRevision.parent_id == draft.current_revision_id)
            .order_by(StudioRevision.seq.desc()).limit(1))

    def can_undo(self, draft: StudioDraft) -> bool:
        return self.revision(draft).parent_id is not None

    def can_redo(self, draft: StudioDraft) -> bool:
        return self._redo_target(draft) is not None

    # ------------------------------------------------------------------ create / revise
    def create(self, mode: str, title: str | None = None) -> StudioDraft:
        if mode not in MODES:
            raise AppError(422, "INVALID_MODE", "Chế độ phải là TEXT (soạn chữ) hoặc RESTORE (phục dựng ảnh).")
        enabled = self.catalog.setting("order_types_enabled")
        if enabled is not None and MODES[mode].value not in enabled:          # MSG03: same rule as creating an order
            raise AppError(409, "ORDER_TYPE_SUSPENDED", "Loại dịch vụ này đang tạm ngừng nhận đơn.")
        open_count = self.session.scalar(select(func.count()).select_from(StudioDraft).where(
            StudioDraft.customer_id == self.customer.id, StudioDraft.status == "OPEN"))
        if open_count >= MAX_OPEN_DRAFTS:
            raise AppError(409, "TOO_MANY_DRAFTS", f"Bạn đang có {MAX_OPEN_DRAFTS} bản nháp mở; hãy gửi hoặc bỏ bớt.")
        draft = StudioDraft(customer_id=self.customer.id, mode=mode, status="OPEN", title=(title or None), flags=[])
        self.session.add(draft)
        self.session.flush()
        self._add_revision(draft, empty_content(mode), author="CUSTOMER", tool=None, note="Tạo bản nháp", parent=None)
        return draft

    def _add_revision(self, draft: StudioDraft, content: dict[str, Any], *, author: str, tool: str | None,
                      note: str | None, parent: int | None | str = "current") -> StudioRevision:
        seq = (self.session.scalar(select(func.max(StudioRevision.seq)).where(StudioRevision.draft_id == draft.id)) or 0) + 1
        if seq > MAX_REVISIONS:
            raise AppError(409, "DRAFT_HISTORY_FULL", f"Bản nháp đã có {MAX_REVISIONS} lần sửa; hãy gửi xưởng hoặc tạo bản nháp mới.")
        rev = StudioRevision(draft_id=draft.id, parent_id=draft.current_revision_id if parent == "current" else parent,
                             seq=seq, content=content, author=author, tool_name=tool, note=(note or None)[:200] if note else None)
        self.session.add(rev)
        self.session.flush()
        draft.current_revision_id = rev.id
        draft.updated_at = _now()
        self.session.flush()
        return rev

    def revise(self, draft: StudioDraft, changes: dict[str, Any], *, author: str = "CUSTOMER", tool: str | None = None,
               note: str | None = None) -> tuple[StudioRevision | None, list[str]]:
        """Applies `changes` (only the keys present) on the current content; a change that changes nothing makes no revision."""
        unknown = set(changes) - set(EDITABLE_FIELDS)
        if unknown:
            raise AppError(422, "UNKNOWN_FIELD", "Trường không sửa được.", sorted(unknown))
        if "title" in changes:
            draft.title = (changes.pop("title") or None)
        old = self.content(draft)
        new, warnings = self.apply_changes(draft, old, changes)
        if new == old:
            return None, warnings
        return self._add_revision(draft, new, author=author, tool=tool, note=note), warnings

    def undo(self, draft: StudioDraft) -> StudioRevision:
        cur = self.revision(draft)
        if cur.parent_id is None:
            raise AppError(409, "NOTHING_TO_UNDO", "Không còn thao tác nào để hoàn tác.")
        draft.current_revision_id, draft.updated_at = cur.parent_id, _now()
        self.session.flush()
        return self.revision(draft)

    def redo(self, draft: StudioDraft) -> StudioRevision:
        target = self._redo_target(draft)
        if target is None:
            raise AppError(409, "NOTHING_TO_REDO", "Không có thao tác nào để làm lại.")
        draft.current_revision_id, draft.updated_at = target.id, _now()
        self.session.flush()
        return target

    # ------------------------------------------------------------------ validation of a change
    def apply_changes(self, draft: StudioDraft, content: dict[str, Any], ch: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        c, warnings = copy.deepcopy(content), []
        text_mode = draft.mode == "TEXT"
        if not text_mode and ({"text", "template_id", "font_size_mm", "alignment", "layout", "canvas"} & ch.keys()):
            raise AppError(422, "FIELD_NOT_FOR_MODE", "Bản nháp phục dựng ảnh không có nội dung chữ / mẫu chữ / canvas.")
        if "text" in ch:
            text = unicodedata.normalize("NFC", ch["text"] or "")
            if len(text) > MAX_TEXT:
                raise AppError(422, "TEXT_TOO_LONG", f"Nội dung tối đa {MAX_TEXT} ký tự.")
            c["text"] = text
        if "template_id" in ch:
            tid = ch["template_id"]
            if tid is not None:
                tpl = self.catalog.template(int(tid))
                if tpl is None or not tpl.is_active:
                    raise AppError(422, "INVALID_TEMPLATE", "Mẫu chữ không tồn tại hoặc đang tắt.")
                tid = tpl.id
            c["template_id"] = tid
        if "font_size_mm" in ch:
            size = ch["font_size_mm"]
            if size is not None:
                size = float(size)
                if not text_layout.MIN_FONT_SIZE_MM <= size <= text_layout.MAX_FONT_SIZE_MM:
                    raise AppError(422, "INVALID_FONT_SIZE",
                                   f"Cỡ chữ từ {text_layout.MIN_FONT_SIZE_MM:g} đến {text_layout.MAX_FONT_SIZE_MM:g} mm.")
            c["font_size_mm"] = size
        if "alignment" in ch:
            if ch["alignment"] is not None and ch["alignment"] not in ALIGNMENTS:
                raise AppError(422, "INVALID_ALIGNMENT", f"Căn lề phải là một trong {list(ALIGNMENTS)}.")
            c["alignment"] = ch["alignment"]
        if "layout" in ch:
            c["layout"] = ch["layout"]
        if text_mode and c.get("layout") and ({"text", "layout"} & ch.keys()):
            try:
                parsed = text_layout.parse(c["layout"], len(c["text"]))
                c["layout"] = text_layout.to_json(parsed.with_defaults())
            except text_layout.TextLayoutError as exc:
                if "layout" in ch:                          # the layout itself was sent: the customer must fix it
                    raise AppError(422, "INVALID_LAYOUT", exc.message, exc.details) from exc
                c["layout"] = None                          # the text changed under its styled parts: drop them
                warnings.append("LAYOUT_RESET")
        if "canvas" in ch:
            cv = ch["canvas"]
            if cv is not None and (not isinstance(cv, dict) or not isinstance(cv.get("strokes"), list)):
                raise AppError(422, "INVALID_CANVAS", 'Canvas phải có dạng {"strokes": [...]}.')
            c["canvas"] = cv if cv and cv.get("strokes") else None
        if {"paper_type_id", "pen_type_id", "ink_color_id"} & ch.keys():
            self._materials(c, ch, warnings)
        if "workshop_suggest_materials" in ch:
            c["workshop_suggest_materials"] = bool(ch["workshop_suggest_materials"])
        if "quantity" in ch:
            q = ch["quantity"]
            if isinstance(q, bool) or not isinstance(q, int) or not 1 <= q <= 10000:
                raise AppError(422, "INVALID_QUANTITY", "Số bản từ 1 đến 10000.")
            c["quantity"] = q
        if "physical_watermark" in ch:
            if not text_mode and not ch["physical_watermark"]:
                raise AppError(422, "WATERMARK_MANDATORY_OT1",
                               "Đơn sao chép / phục dựng luôn có dòng xác thực trên tờ giấy; không tắt được.")
            c["physical_watermark"] = bool(ch["physical_watermark"])
        if "restoration_mode" in ch:
            if text_mode and ch["restoration_mode"] is not None:
                raise AppError(422, "RESTORATION_MODE_OT1_ONLY", "Chế độ phục dựng chỉ áp dụng cho bản phục dựng ảnh.")
            if ch["restoration_mode"] not in (None, "FAITHFUL", "ASSISTED"):
                raise AppError(422, "INVALID_RESTORATION_MODE", "Chế độ phục dựng là FAITHFUL hoặc ASSISTED.")
            texts = [e["region"] for e in c.get("region_edits") or [] if e.get("action") == "TEXT"]
            if texts and ch["restoration_mode"] != "ASSISTED":
                raise AppError(409, "INFERRED_NOT_ALLOWED",
                               "Bản nháp có vùng viết chữ suy đoán; bỏ các vùng đó trước khi chuyển sang phục dựng trung thành.",
                               {"regions": texts})
            c["restoration_mode"] = ch["restoration_mode"]
        if "customer_note" in ch:
            note = ch["customer_note"]
            if note is not None and len(note) > 2000:
                raise AppError(422, "NOTE_TOO_LONG", "Ghi chú tối đa 2000 ký tự.")
            c["customer_note"] = note or None
        return c, warnings

    def _materials(self, c: dict[str, Any], ch: dict[str, Any], warnings: list[str]) -> None:
        """Same rules and messages as the order (BR-05, MSG05); the order service checks them again when the draft is sent."""
        paper_id = ch["paper_type_id"] if "paper_type_id" in ch else c.get("paper_type_id")
        pen_id = ch["pen_type_id"] if "pen_type_id" in ch else c.get("pen_type_id")
        ink_id = ch["ink_color_id"] if "ink_color_id" in ch else c.get("ink_color_id")
        if paper_id is not None:
            paper = self.catalog.paper(int(paper_id))
            if paper is None or not paper.is_active:
                raise AppError(422, "INVALID_PAPER", "Loại giấy không tồn tại hoặc đã ngừng cung cấp.")
        if pen_id is not None:
            pen = self.catalog.pen(int(pen_id))
            if pen is None or not pen.is_active:
                raise AppError(422, "INVALID_PEN", "Loại bút không tồn tại hoặc đã ngừng cung cấp.")
            if paper_id is not None and not self.catalog.is_compatible(int(paper_id), int(pen_id)):
                if "pen_type_id" in ch:
                    raise AppError(422, "PEN_INCOMPATIBLE", "Bút đã chọn không dùng được với loại giấy này. Vui lòng chọn lại bút.")
                pen_id, ink_id = None, None
                warnings.append("PEN_RESET")
        elif ink_id is not None:
            raise AppError(422, "INK_REQUIRES_PEN", "Cần chọn bút trước khi chọn màu mực.")
        if ink_id is not None:
            ink = self.catalog.ink(int(ink_id))
            if ink is None or not ink.is_active or ink.pen_type_id != (int(pen_id) if pen_id is not None else None):
                if "ink_color_id" in ch:
                    raise AppError(422, "INVALID_INK", "Màu mực không thuộc bút đã chọn.")
                ink_id = None
                warnings.append("INK_RESET")
        c["paper_type_id"] = int(paper_id) if paper_id is not None else None
        c["pen_type_id"] = int(pen_id) if pen_id is not None else None
        c["ink_color_id"] = int(ink_id) if ink_id is not None else None

    # ------------------------------------------------------------------ images (RESTORE)
    def _storage(self) -> ObjectStorage:
        if self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        return self.storage

    def _setting(self, key: str) -> Any:
        return self.catalog.setting(key, ORDER_DEFAULTS[key])

    def request_image_upload(self, draft: StudioDraft, mime_type: str, size_bytes: int) -> tuple[str, Any]:
        if draft.mode != "RESTORE":
            raise AppError(422, "FIELD_NOT_FOR_MODE", "Chỉ bản nháp phục dựng ảnh mới tải ảnh bản gốc.")
        if mime_type not in _EXT:
            raise AppError(422, "INVALID_FILE", "File phải là jpg, png hoặc pdf.")
        if size_bytes > int(self._setting("max_upload_mb")) * 1024 * 1024:
            raise AppError(422, "FILE_TOO_LARGE", f"File vượt quá {self._setting('max_upload_mb')} MB.")
        if len(self.content(draft)["images"]) >= int(self._setting("max_pages_per_order")):
            raise AppError(422, "TOO_MANY_FILES", "Đã đạt số lượng ảnh tối đa cho mỗi đơn.")
        image_id = f"{uuid.uuid4().hex}.{_EXT[mime_type]}"
        return image_id, self._storage().create_upload_target(f"studio/{draft.id}/{image_id}")

    def _analyse(self, img: dict[str, Any], data: bytes) -> None:
        if img["mime_type"] == "application/pdf":
            img["quality_result"], img["is_quality_warning"] = {"analysed": False, "reason": "PDF_NOT_ANALYSED"}, False
            return
        result = analyze_image(data, rotation_deg=img.get("rotation_deg") or 0, crop_box=img.get("crop_box"))
        img["quality_result"], img["is_quality_warning"] = result.as_quality_result(), result.warning

    def confirm_image(self, draft: StudioDraft, image_id: str) -> tuple[StudioRevision, dict[str, Any]]:
        if not _IMAGE_ID.match(image_id or ""):
            raise AppError(404, "IMAGE_NOT_FOUND", "Không tìm thấy ảnh.")
        content = self.content(draft)
        if any(i["id"] == image_id for i in content["images"]):
            raise AppError(409, "IMAGE_ALREADY_CONFIRMED", "Ảnh này đã được xác nhận.")
        path = f"studio/{draft.id}/{image_id}"
        store = self._storage()
        data = store.read(path)
        if data is None:
            raise AppError(409, "UPLOAD_NOT_FOUND", "Chưa nhận được file. Vui lòng tải lên rồi xác nhận lại.")
        mime = sniff_mime(data)
        if mime is None or len(data) > int(self._setting("max_upload_mb")) * 1024 * 1024:
            try:
                store.delete(path)
            except Exception:
                pass
            raise AppError(422, "INVALID_FILE", "File phải là jpg, png hoặc pdf và không quá dung lượng cho phép.")
        img = {"id": image_id, "path": path, "mime_type": mime, "size_bytes": len(data), "rotation_deg": 0, "crop_box": None}
        self._analyse(img, data)
        content["images"].append(img)
        rev = self._add_revision(draft, content, author="CUSTOMER", tool=None, note=self._reset_regions(content, "Thêm ảnh bản gốc"))
        return rev, img

    def patch_image(self, draft: StudioDraft, image_id: str, changes: dict[str, Any]) -> StudioRevision:
        content = self.content(draft)
        img = next((i for i in content["images"] if i["id"] == image_id), None)
        if img is None:
            raise AppError(404, "IMAGE_NOT_FOUND", "Không tìm thấy ảnh.")
        if changes.get("rotation_deg") is not None:
            img["rotation_deg"] = changes["rotation_deg"]
        if "crop_box" in changes:
            img["crop_box"] = changes["crop_box"]
        data = self._storage().read(img["path"])
        if data is not None:
            self._analyse(img, data)
        return self._add_revision(draft, content, author="CUSTOMER", tool=None, note=self._reset_regions(content, "Xoay / cắt ảnh"))

    def remove_image(self, draft: StudioDraft, image_id: str) -> StudioRevision:
        """The object stays in storage while the draft is open (undo can bring the image back); it goes with the draft."""
        content = self.content(draft)
        kept = [i for i in content["images"] if i["id"] != image_id]
        if len(kept) == len(content["images"]):
            raise AppError(404, "IMAGE_NOT_FOUND", "Không tìm thấy ảnh.")
        content["images"] = kept
        return self._add_revision(draft, content, author="CUSTOMER", tool=None, note=self._reset_regions(content, "Bỏ ảnh"))

    # ------------------------------------------------------------------ regions (RESTORE, U4 in the studio)
    @staticmethod
    def _reset_regions(content: dict[str, Any], note: str) -> str:
        """Regions are numbered from the images: once the images change, the old numbers point at other words."""
        if content.get("region_edits"):
            content["region_edits"] = []
            return f"{note}; bỏ chỉnh sửa vùng"
        return note

    def regions(self, draft: StudioDraft) -> dict[str, Any]:
        """The word regions of the restored preview with the customer's edits applied, and the edits themselves."""
        if draft.mode != "RESTORE":
            raise AppError(422, "FIELD_NOT_FOR_MODE", "Chỉ bản nháp phục dựng ảnh mới có vùng.")
        c = self.content(draft)
        gen = self.generate(draft, c, 0)
        return {"restoration_mode": c.get("restoration_mode") or "FAITHFUL", "edits": c.get("region_edits") or [],
                "regions": [{"page_no": r.page_no, "region_no": r.region_no, "bbox_mm": list(r.bbox), "label": r.label,
                             "confidence": r.confidence, "source": r.source, "text": r.text, "note": r.note}
                            for r in gen.regions]}

    def set_region_edit(self, draft: StudioDraft, page: int, region: int, action: str, *, text: str | None = None,
                        font: str | None = None, note: str | None = None) -> StudioRevision:
        if draft.mode != "RESTORE":
            raise AppError(422, "FIELD_NOT_FOR_MODE", "Chỉ bản nháp phục dựng ảnh mới có vùng.")
        if action not in rg.CUSTOMER_ACTIONS:
            raise AppError(422, "INVALID_REGION_EDIT", "Thao tác vùng phải là REMOVE hoặc TEXT.")
        if note is not None and len(note) > 500:
            raise AppError(422, "NOTE_TOO_LONG", "Ghi chú tối đa 500 ký tự.")
        c = copy.deepcopy(self.content(draft))
        edits = [e for e in c.get("region_edits") or [] if (e["page"], e["region"]) != (page, region)]
        if len(edits) >= rg.MAX_CUSTOMER_EDITS:
            raise AppError(422, "TOO_MANY_REGION_EDITS", f"Tối đa {rg.MAX_CUSTOMER_EDITS} vùng được chỉnh trong một bản nháp.")
        entry: dict[str, Any] = {"page": page, "region": region, "action": action, "note": (note or "").strip() or None}
        if action == "TEXT":
            entry["text"] = unicodedata.normalize("NFC", (text or "").strip())
            entry["font"] = font
        c["region_edits"] = [*edits, entry]
        self.generate(draft, c, 0)                  # strict: the region must exist, TEXT needs ASSISTED and must fit
        label = "Bỏ vùng" if action == "REMOVE" else "Viết chữ vào vùng"
        return self._add_revision(draft, c, author="CUSTOMER", tool=None, note=f"{label} {region} trang {page}")

    def remove_region_edit(self, draft: StudioDraft, page: int, region: int) -> StudioRevision:
        c = copy.deepcopy(self.content(draft))
        edits = c.get("region_edits") or []
        kept = [e for e in edits if (e["page"], e["region"]) != (page, region)]
        if len(kept) == len(edits):
            raise AppError(404, "REGION_EDIT_NOT_FOUND", "Vùng này chưa được chỉnh.")
        c["region_edits"] = kept
        return self._add_revision(draft, c, author="CUSTOMER", tool=None, note=f"Bỏ chỉnh sửa vùng {region} trang {page}")

    # ------------------------------------------------------------------ checks, price, preview
    def _transient_inputs(self, draft: StudioDraft, c: dict[str, Any]) -> list[OrderInput]:
        """OrderInput objects that are never added to the session: PricingService reads them like an order's inputs."""
        rows: list[OrderInput] = []
        if draft.mode == "TEXT":
            if c.get("text"):
                rows.append(OrderInput(kind=OrderInputKind.TEXT_CONTENT, text_content=c["text"], template_id=c.get("template_id")))
            if c.get("canvas"):
                rows.append(OrderInput(kind=OrderInputKind.CANVAS, canvas_data=c["canvas"]))
        else:
            for img in c.get("images") or []:
                rows.append(OrderInput(kind=OrderInputKind.ORIGINAL_IMAGE, quality_result=img.get("quality_result"),
                                       mime_type=img.get("mime_type")))
        return rows

    def _paper_size(self, c: dict[str, Any]) -> str:
        paper = self.catalog.paper(c["paper_type_id"]) if c.get("paper_type_id") else None
        return paper.size.value if paper else "A4"                 # as the workshop's sketch when no paper is chosen

    def _pen(self, c: dict[str, Any]) -> tuple[float, str | None]:
        pen = self.catalog.pen(c["pen_type_id"]) if c.get("pen_type_id") else None
        return (float(pen.v_max_mm_s) if pen else 30.0), (pen.category if pen else None)

    def generate(self, draft: StudioDraft, c: dict[str, Any], chars: int) -> engine.Generated:
        """The same engine the Staff run (sketches.py), on the draft's content. Raises AppError with the engine's own code."""
        v_max, category = self._pen(c)
        size = self._paper_size(c)
        if draft.mode == "TEXT":
            tpl = self.catalog.template(c["template_id"]) if c.get("template_id") else None
            # exactly what submit() -> OrderService.set_text will store, so the Staff's sketch is this preview: NFC text and
            # the canonical layout (vertical MIDDLE by default). Before, a draft without a layout was drawn from the top.
            text = unicodedata.normalize("NFC", c.get("text") or "")
            layout = OrderService._check_layout(c.get("layout"), text) if text.strip() else c.get("layout")
            return engine.generate_ot3(
                text or None, c.get("canvas"), font_uri=tpl.font_uri if tpl else None,
                font_size_mm=c.get("font_size_mm"), alignment=c.get("alignment") or text_layout.DEFAULT_ALIGNMENT,
                paper_size=size, seed=None, v_max_mm_s=v_max, pen_category=category, chars=chars,
                font_loader=self.storage.read if self.storage else None, layout=layout)
        store = self._storage()
        sources = []
        for img in c.get("images") or []:
            if img.get("mime_type") == "application/pdf":
                raise AppError(422, "PDF_NOT_SUPPORTED_AI", "Chưa xem trước được từ file PDF; xưởng sẽ xử lý sau khi nhận đơn.")
            data = store.read(img["path"])
            if data is None:
                raise AppError(409, "FILE_MISSING", "Không đọc được ảnh gốc từ kho lưu trữ.")
            sources.append(engine.ImageSource(data, img.get("rotation_deg") or 0, img.get("crop_box")))
        gen = engine.generate_ot1(sources, paper_size=size, v_max_mm_s=v_max, pen_category=category, chars=chars)
        if c.get("region_edits"):
            gen.regions, _, _ = rg.apply_edits(gen.pages, gen.regions, c["region_edits"],
                                               assisted=c.get("restoration_mode") == "ASSISTED", strict=True)
            if not any(p.strokes for p in gen.pages):
                raise AppError(422, "NO_CONTENT", "Bản xem trước không còn nét nào.")
            gen.metrics = tj.compute_metrics(gen.pages, v_max)
        return gen

    def check(self, draft: StudioDraft, c: dict[str, Any] | None = None, *, render: bool = True) -> dict[str, Any]:
        """What would stop the draft from being sent, the price estimate and (when `render`) whether the content fits the paper.
        Never raises for a content problem: each one is a {field, code, message} entry."""
        c = c if c is not None else self.content(draft)
        problems: list[dict[str, str]] = []

        def add(field: str, code: str, message: str) -> None:
            problems.append({"field": field, "code": code, "message": message})

        if draft.mode == "TEXT":
            has_text = bool(count_text_chars(c.get("text") or ""))
            if not has_text and not c.get("canvas"):
                add("text", "NO_CONTENT", "Chưa có nội dung chữ hoặc hình vẽ.")
            if has_text and not c.get("template_id"):
                add("template_id", "TEMPLATE_REQUIRED", "Vui lòng chọn mẫu chữ.")
        else:
            if not c.get("images"):
                add("images", "NO_ORIGINAL_IMAGE", "Vui lòng tải ảnh bản gốc.")
        if not c.get("workshop_suggest_materials") and not (c.get("paper_type_id") and c.get("pen_type_id") and c.get("ink_color_id")):
            add("materials", "MATERIALS_INCOMPLETE", "Vui lòng chọn đủ giấy, bút và màu mực (hoặc để xưởng đề xuất).")
        rows = self._transient_inputs(draft, c)
        estimate = None
        try:
            est = PricingService(self.session).estimate(
                order_type=MODES[draft.mode], quantity=c.get("quantity") or 1, paper_id=c.get("paper_type_id"),
                pen_id=c.get("pen_type_id"), ink_id=c.get("ink_color_id"), inputs=rows)
            estimate = {"chars_min": est.chars_min, "chars_max": est.chars_max, "price_min": est.price_min,
                        "price_max": est.price_max, "basis": est.basis, "materials_priced": est.materials_priced}
        except AppError as exc:
            add("pricing", exc.code, exc.message)
        pages = None
        if render and not any(p["code"] in ("NO_CONTENT", "TEMPLATE_REQUIRED", "NO_ORIGINAL_IMAGE") for p in problems):
            try:
                gen = self.generate(draft, c, estimate["chars_max"] if estimate else 0)
                pages = len(gen.pages)
                if physical_mark.required(MODES[draft.mode].value, c.get("physical_watermark")):
                    physical_mark.apply(gen.pages, PREVIEW_CODE)            # WATERMARK_NO_SPACE when the margins are full
            except AppError as exc:
                add("content", exc.code, exc.message)
        return {"ready": not problems, "problems": problems, "estimate": estimate, "pages": pages}

    def preview(self, draft: StudioDraft, page_no: int) -> bytes:
        """JPEG of one page as the robot would write it, with the visible AI mark (U2) and, when the line is required or chosen,
        the U8 line with a placeholder code. An estimate for the customer: the Staff still make the official sketch."""
        c = self.content(draft)
        rows = self._transient_inputs(draft, c)
        chars = sum(count_text_chars(r.text_content or "") for r in rows if r.text_content)
        gen = self.generate(draft, c, chars)
        if physical_mark.required(MODES[draft.mode].value, c.get("physical_watermark")):
            physical_mark.apply(gen.pages, PREVIEW_CODE)
        if not 1 <= page_no <= len(gen.pages):
            raise AppError(404, "PAGE_NOT_FOUND", f"Bản xem trước có {len(gen.pages)} trang.")
        page = gen.pages[page_no - 1]
        paper = self.catalog.paper(c["paper_type_id"]) if c.get("paper_type_id") else None
        pen = self.catalog.pen(c["pen_type_id"]) if c.get("pen_type_id") else None
        ink = self.catalog.ink(c["ink_color_id"]) if c.get("ink_color_id") else None
        img = render_image.render_jpeg(page, ink_hex=ink.hex_code if ink else None,
                                       stroke_width_mm=float(pen.stroke_width_mm) if pen and pen.stroke_width_mm else None,
                                       paper_surface=paper.surface if paper else None)
        return watermark.apply_bytes(img, None, fmt="jpg")

    # ------------------------------------------------------------------ flags
    def flag(self, draft: StudioDraft, kind: str, note: str, by: str) -> dict[str, Any]:
        entry = {"kind": kind, "note": (note or "")[:500], "by": by, "at": _now().isoformat()}
        draft.flags = [*(draft.flags or []), entry]
        self.session.flush()
        return entry

    # ------------------------------------------------------------------ submit / abandon
    def submit(self, draft: StudioDraft, *, terms_accepted: bool, confirm_right_to_use: bool) -> int:
        if not terms_accepted:
            raise AppError(422, "TERMS_NOT_ACCEPTED", "Cần đồng ý điều khoản trước khi gửi đơn.")
        c = self.content(draft)
        result = self.check(draft, c, render=False)            # the engine runs again when the Staff generate the sketch
        if result["problems"]:
            raise AppError(422, "ORDER_INCOMPLETE", "Vui lòng nhập đầy đủ thông tin bắt buộc.", result["problems"])
        svc = OrderService(self.session, self.customer, self.storage, self.ip)
        order = svc.create(MODES[draft.mode], c.get("quantity") or 1)
        changes: dict[str, Any] = {"workshop_suggest_materials": bool(c.get("workshop_suggest_materials")),
                                   "customer_note": c.get("customer_note")}
        for k in ("paper_type_id", "pen_type_id", "ink_color_id"):
            if c.get(k) is not None:
                changes[k] = c[k]
        if draft.mode == "TEXT":
            changes["physical_watermark"] = bool(c.get("physical_watermark"))
        elif c.get("restoration_mode"):
            changes["restoration_mode"] = c["restoration_mode"]
        svc.update(order.id, changes)
        if draft.mode == "TEXT":
            if count_text_chars(c.get("text") or ""):
                svc.set_text(order.id, {"text_content": c["text"], "template_id": c.get("template_id"),
                                        "handwriting_style_id": None,
                                        "font_size_mm": Decimal(str(c["font_size_mm"])) if c.get("font_size_mm") else None,
                                        "alignment": c.get("alignment"), "layout": c.get("layout")})
            if c.get("canvas"):
                svc.set_canvas(order.id, c["canvas"])
        else:
            store = self._storage()
            repo = OrderRepository(self.session)
            for n, img in enumerate(c["images"]):
                data = store.read(img["path"])
                if data is None:
                    raise AppError(409, "FILE_MISSING", "Không đọc được ảnh gốc từ kho lưu trữ; hãy tải lại ảnh.")
                path = f"orders/{order.id}/{uuid.uuid4().hex}.{_EXT[img['mime_type']]}"
                store.write(path, data, img["mime_type"])
                repo.add_input(OrderInput(order_id=order.id, kind=OrderInputKind.ORIGINAL_IMAGE, file_url=path,
                                          mime_type=img["mime_type"], file_size_bytes=img["size_bytes"], sort_order=n,
                                          rotation_deg=img.get("rotation_deg") or 0, crop_box=img.get("crop_box"),
                                          quality_result=img.get("quality_result"),
                                          is_quality_warning=bool(img.get("is_quality_warning"))))
        order = svc.submit(order.id, terms_accepted=True, confirm_right_to_use=confirm_right_to_use)
        draft.status, draft.order_id, draft.submitted_at, draft.updated_at = "SUBMITTED", order.id, _now(), _now()
        self.session.flush()
        audit.record(self.session, actor_id=self.customer.id, action="STUDIO_SUBMIT", entity_type="order", entity_id=order.id,
                     new={"draft_id": draft.id, "revision_id": draft.current_revision_id, "flags": len(draft.flags or [])},
                     ip=self.ip)
        return order.id

    def abandon(self, draft: StudioDraft) -> None:
        set_actor(self.session, self.customer.id)
        paths = {i["path"] for r in self.revisions(draft) for i in (r.content.get("images") or [])}
        draft.status, draft.updated_at = "ABANDONED", _now()
        self.session.flush()
        if self.storage is not None:
            for p in paths:
                try:
                    self.storage.delete(p)
                except Exception:          # best effort: an orphan object is harmless and purged by retention (BR-23)
                    pass


def studio_for_order(session: Session, order_id: int) -> dict[str, Any]:
    """U5, for the Staff: the draft an order came from, its flags, its history and the assistant's conversation."""
    from app.models.studio import AiMessage, AiSession, AiToolCall
    draft = session.scalar(select(StudioDraft).where(StudioDraft.order_id == order_id))
    if draft is None:
        raise AppError(404, "STUDIO_DRAFT_NOT_FOUND", "Đơn này không tạo từ studio.")
    revs = list(session.scalars(select(StudioRevision).where(StudioRevision.draft_id == draft.id).order_by(StudioRevision.seq)))
    sess = session.scalar(select(AiSession).where(AiSession.draft_id == draft.id))
    messages: list[dict[str, Any]] = []
    if sess is not None:
        rows = list(session.scalars(select(AiMessage).where(AiMessage.session_id == sess.id).order_by(AiMessage.id)))
        calls: dict[int, list[str]] = {}
        if rows:
            for c in session.scalars(select(AiToolCall).where(AiToolCall.message_id.in_([r.id for r in rows])).order_by(AiToolCall.id)):
                calls.setdefault(c.message_id, []).append(c.name if c.ok else f"{c.name} (bị từ chối)")
        messages = [{"role": r.role, "content": r.content, "status": r.status, "provider": r.provider,
                     "tools": calls.get(r.id, []), "created_at": r.created_at} for r in rows]
    return {"draft_id": draft.id, "mode": draft.mode, "flags": draft.flags or [], "submitted_at": draft.submitted_at,
            "submitted_revision_id": draft.current_revision_id,
            "revisions": [{"seq": r.seq, "author": r.author, "tool_name": r.tool_name, "note": r.note,
                           "created_at": r.created_at} for r in revs],
            "ai_consented_at": sess.consented_at if sess else None, "messages": messages}
