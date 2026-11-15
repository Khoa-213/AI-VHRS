"""Upgrade U8: verification code, public verification page and the printed certificate card (Q3 = A).

* The code is created the first time a sketch of a watermarked order is saved (the robot writes it on the sheet, so it
  must exist before the strokes). One code per order; every copy of the order carries the same code.
* The public page (`GET /verify/{code}`, no login) tells whoever holds the sheet that it is an AI reconstruction and
  whether it was really produced by the workshop. It shows NO customer data and NO content (a letter may be private):
  only the kind of product, paper size, page count, quantity and dates. The status is derived at read time.
* The card is a PDF the Staff print and put in the parcel: the same statement, the code, and a QR code to the page.
  The QR is drawn as vector squares from OpenCV's encoder (no new dependency); it is never written by the robot
  (ink spread makes a pen-drawn QR unreliable, docs/UPGRADE_AI_ROBOT_PLAN.md 3.5).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import cv2
from fpdf import FPDF
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.order import Order, OrderStatus, OrderType
from app.models.ops import JobStatus, ProductCertificate, ProductionJob, ProductionSnapshot
from app.models.sketch import Sketch
from app.repositories.catalog import CatalogRepository
from app.services.stroke_ai import physical_mark

ASSETS = Path(__file__).resolve().parents[1] / "assets"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
WRITTEN_STATES = (JobStatus.WRITTEN, JobStatus.PHOTO_UPLOADED, JobStatus.DONE)
TYPE_LABEL = {OrderType.OT1_COPY_RESTORE: "Sao chép / phục dựng chữ viết tay",
              OrderType.OT2_LEARNED_STYLE: "Viết theo nét chữ đã học",
              OrderType.OT3_TEMPLATE: "Viết theo mẫu chữ"}
STATEMENT = ("Tờ giấy này do robot của xưởng AI-VHRS viết lại bằng bút mực từ bản phác thảo tái tạo bằng AI. "
             "Đây là bản tái tạo, không phải bản gốc và không có giá trị thay thế giấy tờ gốc.")
STATUS_TEXT = {
    "VALID": "Sản phẩm đã được xưởng sản xuất với mã này.",
    "NOT_PRODUCED": "Mã đã cấp nhưng sản phẩm chưa được viết xong.",
    "REVOKED": "Đơn hàng của mã này đã huỷ: mã không còn giá trị.",
}


def verify_url(code: str) -> str:
    return f"{get_settings().public_verify_url.rstrip('/')}/{code}"


class CertificateService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ code
    def of_order(self, order_id: int) -> ProductCertificate | None:
        return self.session.scalar(select(ProductCertificate).where(ProductCertificate.order_id == order_id))

    def ensure(self, order: Order) -> ProductCertificate:
        row = self.of_order(order.id)
        if row is not None:
            return row
        while True:                                   # 31^8 codes: a clash is ~1e-12 per try, the loop is a formality
            code = physical_mark.new_code()
            if self.session.scalar(select(ProductCertificate.id).where(ProductCertificate.code == code)) is None:
                break
        row = ProductCertificate(order_id=order.id, code=code)
        self.session.add(row)
        self.session.flush()
        return row

    # ------------------------------------------------------------------ facts (read time)
    def _facts(self, cert: ProductCertificate) -> dict[str, Any]:
        order = self.session.get(Order, cert.order_id)
        written_at = self.session.scalar(select(func.max(ProductionJob.finished_at)).where(
            ProductionJob.order_id == order.id, ProductionJob.status.in_(WRITTEN_STATES)))
        locked = self.session.scalar(select(ProductionSnapshot).where(
            ProductionSnapshot.order_id == order.id, ProductionSnapshot.revoked_at.is_(None)))
        sketch = self.session.scalar(select(Sketch).where(Sketch.order_id == order.id, Sketch.is_final.is_(True)))
        paper = CatalogRepository(self.session).paper(order.paper_type_id) if order.paper_type_id else None
        if order.order_status == OrderStatus.CANCELLED:
            status = "REVOKED"
        elif written_at is not None:
            status = "VALID"
        else:
            status = "NOT_PRODUCED"
        wm = (sketch.watermark if sketch is not None else None) or {}
        return {"order": order, "status": status, "written_at": written_at, "locked_at": locked.created_at if locked else None,
                "paper_size": paper.size.value if paper else None, "pages": len(wm.get("pages") or []) or None,
                "watermark_text": wm.get("text") or physical_mark.line_text(cert.code)}

    def public_view(self, raw_code: str) -> dict[str, Any]:
        code = physical_mark.normalise_code(raw_code)
        cert = (self.session.scalar(select(ProductCertificate).where(ProductCertificate.code == code))
                if physical_mark.is_code(code) else None)
        if cert is None:
            raise AppError(404, "CERTIFICATE_NOT_FOUND",
                           "Không có sản phẩm nào mang mã này. Kiểm tra lại mã trên tờ giấy hoặc thẻ chứng nhận.")
        f = self._facts(cert)
        order: Order = f["order"]
        return {"code": cert.code, "status": f["status"], "status_text": STATUS_TEXT[f["status"]],
                "statement": STATEMENT, "watermark_text": f["watermark_text"],
                "order_type": order.order_type.value, "order_type_label": TYPE_LABEL[order.order_type],
                "paper_size": f["paper_size"], "pages": f["pages"], "quantity": order.quantity,
                "issued_at": cert.created_at, "production_locked_at": f["locked_at"], "written_at": f["written_at"]}

    # ------------------------------------------------------------------ card
    def card_pdf(self, order: Order) -> tuple[bytes, str]:
        cert = self.of_order(order.id)
        if cert is None:
            raise AppError(409, "CERTIFICATE_NOT_READY",
                           "Đơn chưa có mã xác thực: mã được cấp khi lưu phác thảo của đơn có dòng xác thực.")
        f = self._facts(cert)
        if f["status"] == "REVOKED":
            raise AppError(409, "CERTIFICATE_REVOKED", "Đơn đã huỷ nên không in thẻ chứng nhận.")
        if f["locked_at"] is None and f["written_at"] is None:
            raise AppError(409, "CERTIFICATE_NOT_READY",
                           "Thẻ chứng nhận chỉ in sau khi đơn đã khoá gói sản xuất (khách đã duyệt và đặt cọc).")
        return render_card(cert.code, order_type=order.order_type, paper_size=f["paper_size"], pages=f["pages"],
                           quantity=order.quantity, written_at=f["written_at"], watermark_text=f["watermark_text"]), \
            f"chung-nhan-{cert.code}.pdf"


def _qr_modules(text: str) -> list[list[bool]]:
    matrix = cv2.QRCodeEncoder.create().encode(text)          # uint8, 0 = dark, 255 = light, quiet zone included
    return [[v < 128 for v in row] for row in matrix]


def _date(value: datetime | None) -> str:
    return value.astimezone(VN).strftime("%d/%m/%Y") if value else "chưa viết xong"


def render_card(code: str, *, order_type: OrderType, paper_size: str | None, pages: int | None, quantity: int,
                written_at: datetime | None, watermark_text: str) -> bytes:
    """A6 landscape card (148 x 105 mm)."""
    url = verify_url(code)
    pdf = FPDF(orientation="L", format=(105, 148), unit="mm")       # A6 (fpdf2 has no A6 name)
    pdf.set_auto_page_break(False)
    pdf.add_font("dv", "", str(ASSETS / "fonts" / "DejaVuSans.ttf"))
    pdf.add_font("dv", "B", str(ASSETS / "fonts" / "DejaVuSans-Bold.ttf"))
    pdf.add_page()
    pdf.set_draw_color(120, 120, 120)
    pdf.rect(4, 4, 140, 97)
    pdf.set_xy(8, 8)
    pdf.set_font("dv", "B", 12)
    pdf.cell(88, 7, "CHỨNG NHẬN TÁI TẠO BẰNG AI", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(8)
    pdf.set_font("dv", "", 7.5)
    pdf.multi_cell(88, 3.8, STATEMENT, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_x(8)
    pdf.set_font("dv", "", 8)
    pdf.cell(88, 4.5, "Mã xác thực", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(8)
    pdf.set_font("dv", "B", 18)
    pdf.cell(88, 9, code, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 7.5)
    rows = [("Loại", TYPE_LABEL[order_type]),
            ("Khổ giấy", f"{paper_size or '-'}, {pages or '-'} trang / bản, {quantity} bản"),
            ("Ngày viết", _date(written_at)),
            ("Dòng trên tờ giấy", watermark_text)]
    for label, value in rows:
        pdf.set_x(8)
        pdf.multi_cell(88, 3.8, f"{label}: {value}", new_x="LMARGIN", new_y="NEXT")
    # QR code on the right, 36 mm wide, then the address under it
    modules = _qr_modules(url)
    size = 36.0
    cell = size / len(modules)
    x0, y0 = 102.0, 14.0
    pdf.set_fill_color(0, 0, 0)
    for r, row in enumerate(modules):
        for c, dark in enumerate(row):
            if dark:
                pdf.rect(x0 + c * cell, y0 + r * cell, cell + 0.01, cell + 0.01, style="F")
    pdf.set_xy(98, y0 + size + 1.5)
    pdf.set_font("dv", "", 6.5)
    pdf.multi_cell(44, 3.2, "Quét mã hoặc mở:\n" + url, align="C")
    pdf.set_xy(8, 94)
    pdf.set_font("dv", "", 6)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(132, 3, f"In ngày {datetime.now(timezone.utc).astimezone(VN).strftime('%d/%m/%Y')} · AI-VHRS")
    return bytes(pdf.output())
