"""Quotation PDF with the workshop header (FR-32, BR-12). DejaVu Sans is bundled because the built-in PDF
fonts cannot draw Vietnamese. A logo file at app/assets/logo.png is used when present; until the workshop
provides one the header is text only."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from app.domain.quotation_rules import fmt_vnd

ASSETS = Path(__file__).resolve().parents[1] / "assets"
WORKSHOP = "XƯỞNG NÉT VIỆT"


@dataclass(frozen=True)
class PdfOption:
    option: int
    title: str
    rows: list[tuple[str, str, int]]       # (item, calc, amount)
    total: int
    min_deposit: int


@dataclass(frozen=True)
class QuotationDoc:
    order_code: str
    version: int
    customer_name: str
    issued_at: datetime
    valid_until: datetime
    eta: date | None
    options: list[PdfOption]
    min_deposit_pct: Decimal
    adjusted: bool            # the reason stays internal (audit log), the customer only sees that a discount/adjustment applied
    multi_option: bool


def render(doc: QuotationDoc) -> bytes:
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_font("dv", "", str(ASSETS / "fonts" / "DejaVuSans.ttf"))
    pdf.add_font("dv", "B", str(ASSETS / "fonts" / "DejaVuSans-Bold.ttf"))
    pdf.add_page()
    x0 = 15
    logo = ASSETS / "logo.png"
    if logo.exists():
        pdf.image(str(logo), x=x0, y=12, h=16)
        x0 = 36
    pdf.set_xy(x0, 12)
    pdf.set_font("dv", "B", 15)
    pdf.cell(0, 8, WORKSHOP, new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(x0)
    pdf.set_font("dv", "", 9)
    pdf.cell(0, 5, "Dịch vụ viết tay tiếng Việt bằng robot", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font("dv", "B", 16)
    pdf.cell(0, 9, "BÁO GIÁ", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("dv", "", 10)
    for label, value in (("Mã đơn", f"{doc.order_code}  (báo giá v{doc.version})"), ("Khách hàng", doc.customer_name),
                         ("Ngày lập", doc.issued_at.strftime("%d/%m/%Y")),
                         ("Hiệu lực đến", doc.valid_until.strftime("%d/%m/%Y")),
                         ("Thời gian giao dự kiến (ETA)", doc.eta.strftime("%d/%m/%Y") if doc.eta else "Sẽ thông báo sau")):
        pdf.cell(60, 6, label)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    widths = (62, 78, 40)
    for opt in doc.options:
        pdf.ln(5)
        pdf.set_font("dv", "B", 11)
        pdf.cell(0, 7, opt.title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("dv", "B", 9)
        pdf.set_fill_color(240, 240, 240)
        for w, h in zip(widths, ("Khoản", "Cách tính", "Thành tiền (đ)")):
            pdf.cell(w, 7, h, border=1, fill=True, align="R" if h.startswith("Thành") else "L")
        pdf.ln()
        pdf.set_font("dv", "", 9)
        for item, calc, amount in opt.rows:
            last = item.startswith("Tổng")
            pdf.set_font("dv", "B" if last else "", 9)
            pdf.cell(widths[0], 7, item, border=1)
            pdf.cell(widths[1], 7, calc, border=1)
            pdf.cell(widths[2], 7, fmt_vnd(amount), border=1, align="R")
            pdf.ln()
        pdf.set_font("dv", "", 9)
        pdf.cell(0, 6, f"Cọc tối thiểu ({doc.min_deposit_pct.normalize():f}%): {fmt_vnd(opt.min_deposit)} đ",
                 new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("dv", "B", 10)
    pdf.multi_cell(0, 6, "Giá chưa bao gồm phí giao hàng.", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 9)
    if doc.multi_option:
        pdf.multi_cell(0, 5, "Vui lòng chọn một phương án vật tư khi xác nhận báo giá.", new_x="LMARGIN", new_y="NEXT")
    if doc.adjusted:
        pdf.multi_cell(0, 5, "Giá đã được xưởng điều chỉnh so với bảng giá tiêu chuẩn.", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 5, "Phí giao hàng được tính riêng theo địa chỉ nhận. Báo giá có hiệu lực đến ngày nêu trên.",
                   new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
