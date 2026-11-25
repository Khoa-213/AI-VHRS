"""Quotation PDF (FR-32, BR-12), laid out like the Manager report PDF (report_pdf.py) so the two documents look alike.

Layout: logo and workshop on the right, a rule with the accent mark, a small eyebrow, the title and the customer, a
metadata band (order, issue date, valid until, ETA), KPI tiles with the total(s) and the minimum deposit, then one table
per material option (column titles repeat on page breaks, the "Tổng" row is the table's total row), the notes, and the
re-quote block. Running header from page 2, footer on every page with "Trang x/y". Fonts, colours and building blocks
come from report_pdf / report_theme; nothing in the figures is recomputed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.domain.quotation_rules import fmt_vnd
from app.services import report_theme as T
from app.services.report_pdf import MARGIN, FOOT_SPACE, Column, _Pdf, _ellipsis, _section, _table, _tiles
from app.services.report_theme import C, rgb

VN = timezone(timedelta(hours=7))


@dataclass(frozen=True)
class PdfOption:
    option: int
    title: str
    rows: list[tuple[str, str, int]]       # (item, calc, amount); the last row is the total
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
    revision_reason: str | None = None       # U2: shown to the customer on a re-quote
    previous_version: int | None = None
    previous_total: Decimal | None = None


AI_NOTICE = ("Phác thảo và thành phẩm là bản tái tạo nét chữ bằng AI-VHRS, không phải văn bản gốc; "
             "ảnh xem trước có dấu nhận diện AI-VHRS.")


def _vn(v: datetime) -> datetime:
    return v.astimezone(VN) if v.tzinfo else v


def _header(pdf: _Pdf, doc: QuotationDoc) -> None:
    top = 13
    if T.LOGO.exists():
        pdf.image(str(T.LOGO), x=MARGIN, y=top, h=13)
    pdf.set_xy(MARGIN, top + 1)
    pdf.set_font("dv", "B", 9)
    pdf.set_text_color(*rgb(C.ink))
    pdf.cell(0, 5, T.WORKSHOP, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 8)
    pdf.set_text_color(*rgb(C.ink3))
    pdf.cell(0, 4.5, "Dịch vụ viết tay tiếng Việt bằng robot", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4.5, "Báo giá gửi khách hàng", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(top + 19)
    pdf.set_draw_color(*rgb(C.line))
    pdf.set_line_width(0.3)
    pdf.line(MARGIN, pdf.get_y(), pdf.w - MARGIN, pdf.get_y())
    pdf.set_fill_color(*rgb(C.accent))
    pdf.rect(MARGIN, pdf.get_y() - 0.6, 24, 1.2, style="F")

    pdf.ln(6)
    pdf.set_font("dv", "", 8)
    pdf.set_text_color(*rgb(C.accent))
    pdf.cell(0, 4.5, f"BÁO GIÁ · PHIÊN BẢN {doc.version}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "B", 19)
    pdf.set_text_color(*rgb(C.ink))
    pdf.cell(0, 10, _ellipsis(pdf, f"Báo giá đơn {doc.order_code}", pdf.body_w), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 10)
    pdf.set_text_color(*rgb(C.ink2))
    who = f"Kính gửi {doc.customer_name}" if doc.customer_name else "Kính gửi Quý khách"
    pdf.cell(0, 6, _ellipsis(pdf, who, pdf.body_w), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    meta = [("Mã đơn", doc.order_code, 1.0),
            ("Ngày lập", _vn(doc.issued_at).strftime("%d/%m/%Y"), 0.8),
            ("Hiệu lực đến", _vn(doc.valid_until).strftime("%d/%m/%Y"), 0.8),
            ("Giao dự kiến (ETA)", doc.eta.strftime("%d/%m/%Y") if doc.eta else "Sẽ thông báo sau", 1.0)]
    unit = pdf.body_w / sum(m[2] for m in meta)
    y = pdf.get_y()
    pdf.set_fill_color(*rgb(C.field))
    pdf.rect(MARGIN, y, pdf.body_w, 13, style="F")
    x = MARGIN + 4
    for label, value, share in meta:
        w = share * unit
        pdf.set_xy(x, y + 2)
        pdf.set_font("dv", "", 7)
        pdf.set_text_color(*rgb(C.ink3))
        pdf.cell(w - 6, 4, label.upper())
        pdf.set_xy(x, y + 6.5)
        pdf.set_font("dv", "B", 9)
        pdf.set_text_color(*rgb(C.ink))
        pdf.cell(w - 6, 5, _ellipsis(pdf, value, w - 6))
        x += w
    pdf.set_y(y + 13 + 6)


def _notes(pdf: _Pdf, doc: QuotationDoc) -> None:
    notes = ["Giá chưa bao gồm phí giao hàng; phí giao hàng được tính riêng theo địa chỉ nhận."]
    if doc.multi_option:
        notes.append("Vui lòng chọn một phương án vật tư khi xác nhận báo giá.")
    if doc.adjusted:
        notes.append("Giá đã được xưởng điều chỉnh so với bảng giá tiêu chuẩn.")
    notes.append(f"Báo giá có hiệu lực đến ngày {_vn(doc.valid_until).strftime('%d/%m/%Y')}.")
    notes.append(AI_NOTICE)
    _section(pdf, "Lưu ý", None, 6 * len(notes))
    for n in notes:
        y = pdf.get_y()
        pdf.set_fill_color(*rgb(C.accent))
        pdf.rect(MARGIN + 1, y + 1.6, 1.4, 1.4, style="F")
        pdf.set_xy(MARGIN + 5, y)
        pdf.set_font("dv", "", 8.8)
        pdf.set_text_color(*rgb(C.ink2))
        pdf.multi_cell(pdf.body_w - 5, 4.6, n, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    pdf.set_text_color(*rgb(C.ink))


def _revision(pdf: _Pdf, doc: QuotationDoc) -> None:
    head = f"Báo giá lại so với phiên bản {doc.previous_version}" if doc.previous_version else "Báo giá lại"
    if doc.previous_total is not None:
        head += f" · tổng trước đây {fmt_vnd(doc.previous_total)} đ"
    text = f"Lý do: {doc.revision_reason}"
    pdf.set_font("dv", "", 8.8)
    h = 6 + len(pdf.multi_cell(pdf.body_w - 10, 4.6, text, dry_run=True, output="LINES")) * 4.6 + 3.5
    if pdf.space_left() < h + 4:
        pdf.add_page()
    pdf.ln(3)
    y = pdf.get_y()
    pdf.set_fill_color(*rgb(C.accent_soft))
    pdf.rect(MARGIN, y, pdf.body_w, h, style="F")
    pdf.set_fill_color(*rgb(C.accent))
    pdf.rect(MARGIN, y, 1.2, h, style="F")
    pdf.set_xy(MARGIN + 5, y + 2)
    pdf.set_font("dv", "B", 9)
    pdf.set_text_color(*rgb(C.ink))
    pdf.cell(pdf.body_w - 10, 4.6, _ellipsis(pdf, head, pdf.body_w - 10), new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(MARGIN + 5, y + 6.8)
    pdf.set_font("dv", "", 8.8)
    pdf.set_text_color(*rgb(C.ink2))
    pdf.multi_cell(pdf.body_w - 10, 4.6, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(y + h + 4)
    pdf.set_text_color(*rgb(C.ink))


def render(doc: QuotationDoc) -> bytes:
    issued = _vn(doc.issued_at)
    pdf = _Pdf(format="A4", unit="mm")
    pdf.generated = issued.strftime("%H:%M %d/%m/%Y")
    pdf.running = f"Báo giá {doc.order_code} · phiên bản {doc.version}"
    pdf.kind = f"Báo giá phiên bản {doc.version}"
    pdf.source = "Giá tính theo bảng giá và vật tư tại thời điểm lập báo giá; chưa gồm phí giao hàng."
    pdf.set_margins(MARGIN, 20, MARGIN)
    pdf.set_auto_page_break(True, margin=FOOT_SPACE)
    pdf.add_font("dv", "", str(T.ASSETS / "fonts" / "DejaVuSans.ttf"))
    pdf.add_font("dv", "B", str(T.ASSETS / "fonts" / "DejaVuSans-Bold.ttf"))
    pdf.set_title(f"Báo giá {doc.order_code} phiên bản {doc.version}")
    pdf.set_author(f"{T.BRAND} · {T.WORKSHOP}")
    pdf.set_subject("Báo giá (FR-32)")
    pdf.set_creator(T.BRAND)
    pdf.add_page()
    _header(pdf, doc)

    pct = f"{doc.min_deposit_pct.normalize():f}%"
    if doc.options:
        _section(pdf, "Tổng quan", None, 30)
        if len(doc.options) == 1:
            o = doc.options[0]
            _tiles(pdf, [("Tổng báo giá", T.money(o.total, unit=True), "Chưa gồm phí giao hàng", None),
                         (f"Cọc tối thiểu ({pct})", T.money(o.min_deposit, unit=True), "Trả trước khi xưởng bắt đầu viết", None),
                         ("Hiệu lực đến", _vn(doc.valid_until).strftime("%d/%m/%Y"), "Sau ngày này cần báo giá lại", None)],
                   accent=True)
        else:
            _tiles(pdf, [(f"Phương án {o.option}", T.money(o.total, unit=True),
                          f"Cọc tối thiểu ({pct}): {T.money(o.min_deposit, unit=True)}", None) for o in doc.options],
                   accent=True)
        pdf.ln(4)

    cols = [Column("Khoản", 34, bold=True), Column("Cách tính", 50), Column("Thành tiền (đ)", 24, "R")]
    for o in doc.options:
        body = [(item, calc, T.money(amount)) for item, calc, amount in o.rows]
        total = None
        if body and o.rows[-1][0].startswith("Tổng"):
            total = body.pop()
        _section(pdf, o.title, f"Cọc tối thiểu ({pct}): {T.money(o.min_deposit, unit=True)}.", 40)
        _table(pdf, cols, body, total, "Chưa có khoản nào trong phương án này.")

    _notes(pdf, doc)
    if doc.revision_reason:
        _revision(pdf, doc)
    return bytes(pdf.output())
