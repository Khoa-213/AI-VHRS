"""V2 Phase E2b (owner approved 2026-11-19): text hints for the word regions of an OT-1 order.

The customer asks for it on the order DRAFT and agrees to send the photos out (every time; the wording names who gets them
and, for Gemini's free tier the owner chose to use, that Google may use them). Each photo, as rotated / cropped, is read
once per order (`htr_readings`, migration 0027); the hints are computed on the fly from that transcript and the regions of
whatever revision is shown (`stroke_ai.htr_align`), so they follow redraws, edits and undo. A hint is READ (a word) or
UNREAD; it never changes a stroke, the price or what the customer approves. Off unless the Admin turns `htr_enabled` on;
`htr_daily_pages` caps the pages read per day for the whole system.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.integrations.storage import ObjectStorage
from app.models.account import Account
from app.models.order import Order, OrderInput, OrderInputKind, OrderType
from app.models.sketch import HtrReading
from app.repositories.catalog import CatalogRepository
from app.repositories.orders import OrderRepository
from app.services import audit
from app.services.ai import htr
from app.services.stroke_ai import htr_align

SETTINGS_DEFAULTS = {"htr_enabled": False, "htr_daily_pages": 100}
VN = ZoneInfo("Asia/Ho_Chi_Minh")
PROVIDER_LABEL = {"gemini": "Google (Gemini)", "anthropic": "Anthropic (Claude)"}


def consent_text(providers: list[str]) -> str:
    names = [PROVIDER_LABEL.get(p, p) for p in providers]
    who = names[0] if len(names) == 1 else (", ".join(names[:-1]) + " hoặc " + names[-1] if names else "dịch vụ AI")
    parts = [f"Để gợi ý chữ trên thư, ảnh bản gốc của bạn sẽ được gửi tới {who}."]
    if "gemini" in providers:
        parts.append("Google có thể lưu và dùng ảnh này để cải thiện dịch vụ của họ.")
    if "anthropic" in providers:
        parts.append("Anthropic xử lý ảnh theo chính sách dữ liệu của họ.")
    parts.append("Chữ gợi ý có thể sai và không thay đổi nét, giá hay nội dung bạn duyệt. Nếu thư có thông tin riêng tư, "
                 "bạn có thể bỏ qua bước này; xưởng vẫn xử lý đơn như thường.")
    return " ".join(parts)


def ot1_sources(session: Session, order: Order) -> list[OrderInput]:
    """The photos the engine draws from, in page order (same filter as `sketches.run_engine`)."""
    return [r for r in OrderRepository(session).inputs(order.id)
            if r.kind == OrderInputKind.ORIGINAL_IMAGE and r.quality_result is not None and r.mime_type != "application/pdf"]


def source_key(row: OrderInput) -> str:
    ident = json.dumps([row.id, row.file_url, row.rotation_deg or 0, row.crop_box], sort_keys=True, default=str)
    return hashlib.sha256(ident.encode()).hexdigest()


def latest_readings(session: Session, order_id: int) -> dict[str, HtrReading]:
    """Per photo: the newest READ row, else the newest FAILED one."""
    out: dict[str, HtrReading] = {}
    for r in session.scalars(select(HtrReading).where(HtrReading.order_id == order_id).order_by(HtrReading.id)):
        if r.status == "READ" or out.get(r.source_key) is None or out[r.source_key].status != "READ":
            out[r.source_key] = r
    return out


def hints_for(session: Session, order: Order, doc: dict[str, Any], *, outdated: bool) -> dict[str, Any] | None:
    """{"state", "pages": [{no, status, provider, check}], "words": {word id: {"text", "status"}}} for an OT-1 document."""
    if order.order_type != OrderType.OT1_COPY_RESTORE:
        return None
    if outdated:            # the photos changed after this drawing: page n may no longer be photo n
        return {"state": "SKETCH_OUTDATED", "pages": [], "words": {}}
    sources = ot1_sources(session, order)
    readings = latest_readings(session, order.id)
    pages, words = [], {}
    for i, p in enumerate(doc["pages"]):
        src = sources[i] if i < len(sources) else None
        rd = readings.get(source_key(src)) if src is not None else None
        status = rd.status if rd is not None else "NOT_READ"
        pages.append({"no": p["no"], "status": status, "provider": rd.provider if rd is not None else None, "check": None})
        if status != "READ":
            continue
        regs = [SimpleNamespace(region_no=k, bbox=tuple(w["bbox"]), wid=w["id"])
                for k, w in enumerate(p["words"], start=1) if w.get("bbox")]
        res = htr_align.match(regs, rd.transcript or "")
        pages[-1]["check"] = res.get("refused")          # TOO_MANY_WORDS: the reading has words with no ink, no hint at all
        for r in regs:
            v = res["regions"][r.region_no]
            words[r.wid] = {"text": v["text"] if v["status"] == "READ" else None, "status": v["status"]}
    states = {pg["status"] for pg in pages}
    state = ("READY" if states == {"READ"} else "NOT_READ" if states <= {"NOT_READ"} else
             "FAILED" if states == {"FAILED"} else "PARTIAL")
    return {"state": state, "pages": pages, "words": words}


class HtrService:
    def __init__(self, session: Session, customer: Account, storage: ObjectStorage | None, *, readers: list[Any] | None = None,
                 ip: str | None = None):
        self.session, self.customer, self.storage, self.ip = session, customer, storage, ip
        self._readers = readers
        self.catalog = CatalogRepository(session)

    def setting(self, key: str) -> Any:
        return self.catalog.setting(key, SETTINGS_DEFAULTS[key])

    def readers(self) -> list[Any]:
        return self._readers if self._readers is not None else htr.configured_readers()

    def _order(self, order_id: int) -> Order:
        order = self.session.scalar(select(Order).where(Order.id == order_id, Order.customer_id == self.customer.id))
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        if order.order_type != OrderType.OT1_COPY_RESTORE:
            raise AppError(422, "HTR_NOT_OT1", "Chỉ đơn chép / phục dựng từ ảnh mới đọc chữ trên ảnh.")
        return order

    def _used_today(self) -> int:
        start = datetime.now(VN).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        return int(self.session.scalar(select(func.count()).select_from(HtrReading)
                                       .where(HtrReading.created_at >= start)) or 0)

    def status(self, order_id: int) -> dict[str, Any]:
        order = self._order(order_id)
        names = [r.name for r in self.readers()]
        readings = latest_readings(self.session, order.id)
        pages = []
        for n, src in enumerate(ot1_sources(self.session, order), start=1):
            rd = readings.get(source_key(src))
            pages.append({"page_no": n, "input_id": src.id, "status": rd.status if rd is not None else "NOT_READ",
                          "provider": rd.provider if rd is not None else None,
                          "read_at": rd.created_at if rd is not None else None})
        cap = int(self.setting("htr_daily_pages"))
        used = self._used_today()
        enabled = bool(self.setting("htr_enabled"))
        return {"enabled": enabled, "available": enabled and bool(names), "providers": names,
                "consent_text": consent_text(names), "daily_cap": cap, "used_today": used, "pages": pages}

    def read(self, order_id: int, *, consent: bool) -> dict[str, Any]:
        order = self._order(order_id)
        from app.services.orders import EDITABLE
        if order.order_status not in EDITABLE:
            raise AppError(409, "ORDER_NOT_EDITABLE", "Đơn đã gửi, phác thảo chỉ còn xem được.")
        if not self.setting("htr_enabled"):
            raise AppError(409, "HTR_DISABLED", "Tính năng đọc chữ trên ảnh đang tắt.")
        readers = self.readers()
        if not readers:
            raise AppError(503, "HTR_UNAVAILABLE", "Chưa cấu hình dịch vụ đọc chữ trên ảnh.")
        names = [r.name for r in readers]
        if not consent:
            raise AppError(400, "HTR_CONSENT_REQUIRED", "Cần bạn đồng ý gửi ảnh trước khi đọc chữ.",
                           {"consent_text": consent_text(names)})
        sources = ot1_sources(self.session, order)
        if not sources:
            raise AppError(422, "NO_ORIGINAL_IMAGE", "Đơn chưa có ảnh bản gốc để đọc chữ.")
        done = {k for k, r in latest_readings(self.session, order.id).items() if r.status == "READ"}
        todo = [s for s in sources if source_key(s) not in done]
        cap, used = int(self.setting("htr_daily_pages")), self._used_today()
        if todo and used + len(todo) > cap:
            raise AppError(429, "HTR_DAILY_CAP", "Hôm nay đã đọc đủ số trang cho phép; vui lòng thử lại ngày mai.",
                           {"daily_cap": cap, "used_today": used, "pages_needed": len(todo)})
        if todo and self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        text_shown = consent_text(names)
        results = []
        for src in todo:
            data = self.storage.read(src.file_url) if src.file_url else None
            if data is None:
                raise AppError(409, "FILE_MISSING", "Không đọc được ảnh gốc từ kho lưu trữ.")
            reading = htr.read_page(htr.page_jpeg(data, src.rotation_deg or 0, src.crop_box), readers)
            t = reading.transcript
            row = HtrReading(order_id=order.id, input_id=src.id, source_key=source_key(src),
                             status="READ" if t is not None else "FAILED", provider=t.provider if t else None,
                             model=t.model if t else None, transcript=t.text if t else None,
                             input_tokens=t.input_tokens if t else None, output_tokens=t.output_tokens if t else None,
                             attempts=reading.attempts, consent_by=self.customer.id, consent_text=text_shown)
            self.session.add(row)
            self.session.flush()
            results.append({"input_id": src.id, "status": row.status, "provider": row.provider})
        audit.record(self.session, actor_id=self.customer.id, action="HTR_READ", entity_type="order", entity_id=order.id,
                     new={"pages": results, "consent_text": text_shown}, ip=self.ip)
        out = self.status(order_id)
        out["read_now"] = results
        return out
