"""FR-50 export layout (Excel + PDF of the Manager report). Unit tests on report dicts, no database: the figures come from
`ReportService.report()`, covered by test_api_admin_reports.py; here we check that the files keep them exactly, with the
right Excel types, formulas, filters, print setup, Vietnamese text, empty reports and long tables."""
import io
import re
import zlib
from datetime import date, datetime

import pytest
from openpyxl import load_workbook

from app.services import report_pdf, report_theme as T, report_xlsx

WHEN = datetime(2026, 11, 15, 9, 30)


def _rep(n_days=3, late=2, robots=("FR3-01",), empty=False, code_prefix="ORD-"):
    day = date(2026, 11, 1)
    series = [] if empty else [
        {"bucket": date(2026, 11, 1 + i), "received": 1_500_000 * (i + 1), "refunded": 3_500_000 if i == 1 else 0,
         "net": 1_500_000 * (i + 1) - (3_500_000 if i == 1 else 0), "payments": i + 1} for i in range(n_days)]
    rec, ref = sum(x["received"] for x in series), sum(x["refunded"] for x in series)
    out = [] if empty else [{"order_type": "OT3_TEMPLATE", "orders": 3, "quantity": 30, "total_amount": 900_000},
                            {"order_type": "OT1_COPY_RESTORE", "orders": 2, "quantity": 4, "total_amount": 12_345_678_900}]
    orders = [] if empty else [{"order_id": i, "code": f"{code_prefix}{i:05d}", "eta": day, "completed_on": date(2026, 11, 3),
                                "days_late": 2, "eta_postponed_days": None} for i in range(late)]
    return {"from": day, "to": date(2026, 11, max(n_days, 1)), "group": "day",
            "revenue": {"series": series, "received": rec, "refunded": ref, "net": rec - ref},
            "output_by_type": out,
            "rates": {"submitted": 0 if empty else 5, "rejected": 0 if empty else 1, "reject_rate": None if empty else 0.2,
                      "jobs_written": 0 if empty else 3, "rewrites": 0, "rewrite_rate": None if empty else 0.0},
            "robots": [{"robot_id": i, "robot_code": c, "jobs_written": 4, "writing_minutes": 95, "incidents": i}
                       for i, c in enumerate(robots)],
            "late_completed": {"count": len(orders), "of_completed": 0 if empty else 5,
                               "late_rate": None if empty else len(orders) / 5, "orders": orders}}


def _wb(rep, who="Nguyễn Văn Quản Lý"):
    return load_workbook(io.BytesIO(report_xlsx.render(rep, WHEN, who)))


def _row_of(ws, text):
    return next(r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == text)


def test_excel_keeps_the_figures_as_typed_values():
    rep = _rep()
    wb = _wb(rep)
    assert wb.sheetnames == ["Tổng quan", "Doanh thu", "Sản lượng", "Robot", "Trễ ETA"]
    ov = wb["Tổng quan"]
    vals = {ov.cell(row=r, column=1).value: ov.cell(row=r, column=2) for r in range(1, ov.max_row + 1)}
    assert vals["Tiền đã nhận"].value == rep["revenue"]["received"] and vals["Tiền đã nhận"].number_format == T.XL_MONEY
    assert vals["Doanh thu thuần"].value == rep["revenue"]["net"]
    assert vals["Tỷ lệ từ chối"].value == 0.2 and vals["Tỷ lệ từ chối"].number_format == T.XL_PCT
    assert vals["Kỳ báo cáo, từ ngày"].value.date() == rep["from"] and vals["Kỳ báo cáo, từ ngày"].number_format == T.XL_DATE
    assert vals["Người xuất"].value == "Nguyễn Văn Quản Lý"

    ws = wb["Doanh thu"]
    hr = report_xlsx.HEAD_ROW
    assert [c.value for c in ws[hr]][:5] == ["Ngày", "Tiền đã nhận (đ)", "Tiền đã hoàn (đ)", "Doanh thu thuần (đ)",
                                            "Số giao dịch thu"]
    first = ws.cell(row=hr + 1, column=1)
    assert first.value.date() == date(2026, 11, 1) and first.number_format == T.XL_DATE
    assert isinstance(ws.cell(row=hr + 1, column=2).value, int)              # numbers stay numbers, not text
    assert ws.cell(row=hr + 2, column=4).value == -500_000                   # a negative net is kept (red by format)
    assert ws.freeze_panes == f"A{hr + 1}" and ws.auto_filter.ref == f"A{hr}:E{hr + 3}"
    total = _row_of(ws, "Tổng cộng")
    assert total == hr + 4 and ws.cell(row=total, column=2).value == f"=SUM(B{hr + 1}:B{hr + 3})"
    assert ws.print_title_rows == f"${hr}:${hr}" and int(ws.page_setup.paperSize) == 9
    assert len(ws._charts) == 1


def test_excel_output_share_and_large_amounts():
    ws = _wb(_rep())["Sản lượng"]
    hr = report_xlsx.HEAD_ROW
    assert ws.cell(row=hr + 1, column=1).value == "Viết theo mẫu chữ" and ws.cell(row=hr + 1, column=2).value == "OT3_TEMPLATE"
    assert ws.cell(row=hr + 2, column=5).value == 12_345_678_900
    assert ws.cell(row=hr + 1, column=6).value == f"=IFERROR(E{hr + 1}/SUM(E${hr + 1}:E${hr + 2}),0)"
    assert ws.cell(row=hr + 1, column=6).data_type == "f"


def test_excel_never_turns_database_text_into_a_formula():
    ws = _wb(_rep(code_prefix='=HYPERLINK("http://x","'), who="=cmd|' /C calc'!A0")["Trễ ETA"]
    c = ws.cell(row=report_xlsx.HEAD_ROW + 1, column=1)
    assert c.data_type == "s" and c.value.startswith("=HYPERLINK")
    ov = _wb(_rep(), who="@SUM(1)")["Tổng quan"]
    who = ov.cell(row=_row_of(ov, "Người xuất"), column=2)
    assert who.data_type == "s" and who.value == "@SUM(1)"


def test_excel_empty_report_has_no_filter_no_total_and_says_so():
    wb = _wb(_rep(empty=True, robots=()))
    for name in ("Doanh thu", "Sản lượng", "Robot", "Trễ ETA"):
        ws = wb[name]
        assert ws.auto_filter.ref is None and not ws._charts
        assert "Không có" in str(ws.cell(row=report_xlsx.HEAD_ROW + 1, column=1).value) or \
               "Chưa có" in str(ws.cell(row=report_xlsx.HEAD_ROW + 1, column=1).value)
        assert all(ws.cell(row=r, column=1).value != "Tổng cộng" for r in range(1, ws.max_row + 1))
    ov = wb["Tổng quan"]
    assert ov.cell(row=_row_of(ov, "Tỷ lệ từ chối"), column=2).value == "–"


def test_excel_long_daily_period_charts_by_month():
    rep = _rep()
    rep["revenue"]["series"] = [{"bucket": date.fromordinal(date(2026, 1, 1).toordinal() + i), "received": 1000, "refunded": 0,
                                 "net": 1000, "payments": 1} for i in range(90)]
    ws = _wb(rep)["Doanh thu"]
    assert len(ws._charts) == 1
    assert any(ws.cell(row=r, column=7).value == "Cộng dồn theo tháng (nguồn của biểu đồ)" for r in range(1, 40))


def _pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", pdf))


def _text(pdf: bytes) -> bytes:
    """Decompressed content streams (good enough to find the glyph runs fpdf writes)."""
    out = b""
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            out += zlib.decompress(m.group(1))
        except zlib.error:
            pass
    return out


def test_pdf_small_report_fits_two_pages_and_embeds_the_unicode_font():
    pdf = report_pdf.render(_rep(), WHEN, "Nguyễn Văn Quản Lý")
    assert pdf[:5] == b"%PDF-" and _pages(pdf) <= 2
    assert b"DejaVuSans" in pdf and b"/FontFile2" in pdf                 # embedded TrueType, so Vietnamese renders anywhere
    assert b"/Title" in pdf


def test_pdf_empty_report_renders_without_blank_pages():
    pdf = report_pdf.render(_rep(empty=True, robots=()), WHEN)
    assert pdf[:5] == b"%PDF-" and _pages(pdf) <= 2


@pytest.mark.parametrize("late", [0, 40, 600])
def test_pdf_long_tables_paginate_and_every_page_has_content(late):
    rep = _rep(late=late, robots=("FR3-XUONG-NET-VIET-CHI-NHANH-THU-DUC-ROBOT-SO-01-DU-PHONG", "FR3-02"))
    pdf = report_pdf.render(rep, WHEN)
    n = _pages(pdf)
    assert n >= (1 + late // 40)
    streams = [s for s in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S)]
    page_streams = [zlib.decompress(s) for s in streams if s[:2] == b"x\x9c" and b"BT" in zlib.decompress(s)]
    assert len([s for s in page_streams if s.count(b"BT") > 3]) >= n     # no page holds only the footer


def test_chart_points_roll_up_long_series_by_month():
    series = [{"bucket": date.fromordinal(date(2026, 1, 1).toordinal() + i), "received": 10, "refunded": 1}
              for i in range(100)]
    labels, rec, ref = report_pdf._chart_points(series, "day")
    assert labels == ["01/2026", "02/2026", "03/2026", "04/2026"] and sum(rec) == 1000 and sum(ref) == 100
    labels, rec, _ = report_pdf._chart_points(series[:7], "day")
    assert labels[0] == "01/01" and len(rec) == 7
