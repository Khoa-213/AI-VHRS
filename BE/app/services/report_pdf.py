"""Manager report as PDF (FR-50, UC-46): the same numbers as the Excel export, laid out on A4 for printing or
sending. Tables only (no charts). DejaVu Sans is bundled because the built-in PDF fonts cannot draw Vietnamese."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from fpdf import FPDF

from app.domain.quotation_rules import fmt_vnd
from app.services.quotation_pdf import ASSETS, WORKSHOP

GROUP_LABEL = {"day": "ngày", "week": "tuần", "month": "tháng"}
ROW_H = 6.5


def _d(v: Any) -> str:
    return v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else ("" if v is None else str(v))


def _pct(v: float | None) -> str:
    return "–" if v is None else f"{v * 100:.1f}%".replace(".", ",")


def _money(v: Any) -> str:
    return fmt_vnd(v or 0)


class _Pdf(FPDF):
    generated: str = ""

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("dv", "", 8)
        self.set_text_color(110, 110, 110)
        self.cell(0, 5, f"Xuất lúc {self.generated}", align="L")
        self.set_x(self.l_margin)
        self.cell(0, 5, f"Trang {self.page_no()}/{{nb}}", align="R")
        self.set_text_color(0, 0, 0)


def _table(pdf: _Pdf, title: str, header: Sequence[str], widths: Sequence[float], rows: list[Sequence[str]],
           right: set[int], empty: str = "Không có dữ liệu trong kỳ.") -> None:
    if pdf.will_page_break(9 + ROW_H * 3):
        pdf.add_page()
    pdf.ln(3)
    pdf.set_font("dv", "B", 11)
    pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")

    def head() -> None:
        pdf.set_font("dv", "B", 9)
        pdf.set_fill_color(235, 235, 235)
        for i, (w, h) in enumerate(zip(widths, header)):
            pdf.cell(w, ROW_H + 0.5, h, border=1, fill=True, align="R" if i in right else "L")
        pdf.ln()
        pdf.set_font("dv", "", 9)

    head()
    if not rows:
        pdf.set_font("dv", "", 9)
        pdf.cell(sum(widths), ROW_H, empty, border=1, new_x="LMARGIN", new_y="NEXT")
        return
    for row in rows:
        if pdf.will_page_break(ROW_H):
            pdf.add_page()
            head()                                   # repeat the column titles on every page of a long table
        for i, (w, v) in enumerate(zip(widths, row)):
            pdf.cell(w, ROW_H, v, border=1, align="R" if i in right else "L")
        pdf.ln()


def render(rep: dict[str, Any], generated_at: datetime) -> bytes:
    pdf = _Pdf(format="A4", unit="mm")
    pdf.generated = generated_at.strftime("%H:%M %d/%m/%Y")
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_font("dv", "", str(ASSETS / "fonts" / "DejaVuSans.ttf"))
    pdf.add_font("dv", "B", str(ASSETS / "fonts" / "DejaVuSans-Bold.ttf"))
    pdf.set_title(f"Báo cáo {_d(rep['from'])} – {_d(rep['to'])}")
    pdf.add_page()

    pdf.set_font("dv", "B", 13)
    pdf.cell(0, 7, WORKSHOP, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("dv", "B", 16)
    pdf.cell(0, 9, "BÁO CÁO HOẠT ĐỘNG", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 10)
    pdf.cell(0, 6, f"Từ {_d(rep['from'])} đến {_d(rep['to'])} · gom theo {GROUP_LABEL.get(rep['group'], rep['group'])}",
             align="C", new_x="LMARGIN", new_y="NEXT")

    r, rev, late = rep["rates"], rep["revenue"], rep["late_completed"]
    _table(pdf, "Tổng quan", ["Chỉ số", "Giá trị"], (120, 60), [
        ("Tiền nhận (đ)", _money(rev["received"])), ("Tiền hoàn (đ)", _money(rev["refunded"])),
        ("Doanh thu thuần (đ)", _money(rev["net"])),
        ("Đơn gửi", str(r["submitted"])), ("Đơn bị từ chối", str(r["rejected"])), ("Tỷ lệ từ chối", _pct(r["reject_rate"])),
        ("Job viết (lần đầu)", str(r["jobs_written"])), ("Job viết lại", str(r["rewrites"])),
        ("Tỷ lệ viết lại", _pct(r["rewrite_rate"])),
        ("Đơn hoàn tất trễ ETA", f"{late['count']} / {late['of_completed']}"), ("Tỷ lệ trễ", _pct(late["late_rate"])),
    ], right={1})
    _table(pdf, "Doanh thu", ["Kỳ", "Tiền nhận (đ)", "Tiền hoàn (đ)", "Thuần (đ)", "Giao dịch"], (36, 40, 40, 40, 24),
           [(_d(x["bucket"]), _money(x["received"]), _money(x["refunded"]), _money(x["net"]), str(x["payments"]))
            for x in rev["series"]], right={1, 2, 3, 4})
    _table(pdf, "Sản lượng (đơn hoàn tất)", ["Loại đơn", "Số đơn", "Số bản", "Giá trị (đ)"], (60, 35, 35, 50),
           [(x["order_type"], str(x["orders"]), str(x["quantity"]), _money(x["total_amount"])) for x in rep["output_by_type"]],
           right={1, 2, 3})
    _table(pdf, "Robot", ["Robot", "Job đã viết", "Phút viết", "Sự cố"], (60, 40, 40, 40),
           [(x["robot_code"], str(x["jobs_written"]), str(x["writing_minutes"]), str(x["incidents"])) for x in rep["robots"]],
           right={1, 2, 3}, empty="Chưa có robot.")
    _table(pdf, "Đơn hoàn tất trễ ETA", ["Mã đơn", "ETA", "Hoàn tất", "Trễ (ngày)", "Đã dời (ngày)"], (50, 32, 32, 33, 33),
           [(x["code"], _d(x["eta"]), _d(x["completed_on"]), str(x["days_late"]), str(x["eta_postponed_days"] or 0))
            for x in late["orders"]], right={3, 4}, empty="Không có đơn trễ.")
    return bytes(pdf.output())
