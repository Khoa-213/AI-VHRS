"""Manager report as an Excel workbook (FR-50, UC-46).

Five sheets with the same names as before (Tổng quan, Doanh thu, Sản lượng, Robot, Trễ ETA). Every figure is the value
`ReportService.report()` returned: numbers stay Excel numbers, dates stay Excel dates, only the display format changes.
Detail sheets have a title band, a frozen header with AutoFilter, light zebra rows and a total row computed by formula from
the rows above it (the overview keeps the database figures as values). Text from the database is always written as text,
never as a formula (formula injection).
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any, Callable, Sequence

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.services import report_theme as T
from app.services.report_theme import C

FONT = "Calibri"
HEAD_ROW = 5                     # detail sheets: rows 1-3 title band, 4 spacer, 5 column titles
THIN = Side(style="thin", color=C.line)
INK_SIDE = Side(style="thin", color=C.ink)


def _fill(hex6: str) -> PatternFill:
    return PatternFill("solid", start_color=hex6, end_color=hex6)


def _font(size: float = 10, bold: bool = False, color: str = C.ink2, italic: bool = False) -> Font:
    return Font(name=FONT, size=size, bold=bold, color=color, italic=italic)


def _put(ws: Worksheet, row: int, col: int, value: Any):
    """Write one cell. Strings that look like formulas stay text (openpyxl would otherwise store '=...' as a formula)."""
    cell = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        cell.data_type = "s"
        cell.quotePrefix = True
    return cell


def _text_len(v: Any, fmt: str | None) -> int:
    if v is None:
        return 0
    if isinstance(v, datetime):
        return 16
    if isinstance(v, date):
        return 10
    if isinstance(v, float) and fmt == T.XL_PCT:
        return 7
    if isinstance(v, (int, float)):
        return len(f"{v:,.0f}") + 1
    return max(len(line) for line in str(v).split("\n"))


class Col:
    def __init__(self, title: str, key: Callable[[dict], Any], fmt: str | None = None, total: str | None = None,
                 align: str | None = None, min_w: float = 10, max_w: float = 48, emphasis: bool = False,
                 row_formula: Callable[[int], str] | None = None):
        self.title, self.key, self.fmt, self.total = title, key, fmt, total   # total: 'sum' | 'label' | '=...' | None
        self.row_formula = row_formula            # built by the code from the row number, never from data
        self.align = align or ("right" if fmt in (T.XL_MONEY, T.XL_INT, T.XL_PCT) else
                               "center" if fmt in (T.XL_DATE, T.XL_MONTH) else "left")
        self.min_w, self.max_w, self.emphasis = min_w, max_w, emphasis


def _indent(col: "Col") -> int:
    return 0 if col.align == "center" else 1


def _title_band(ws: Worksheet, rep: dict, title: str, note: str, width: int) -> None:
    _put(ws, 1, 1, title).font = _font(15, True, C.ink)
    _put(ws, 2, 1, f"{T.BRAND} · {T.WORKSHOP} · Báo cáo hoạt động · {T.period_text(rep)} · {T.group_text(rep)}"
         ).font = _font(9, color=C.ink3)
    _put(ws, 3, 1, note).font = _font(9, color=C.ink3, italic=True)
    ws.row_dimensions[1].height = 24
    for r in (1, 2, 3):
        ws.cell(row=r, column=1).alignment = Alignment(vertical="center")
    for c in range(1, width + 1):                                       # accent rule under the title band
        ws.cell(row=3, column=c).border = Border(bottom=Side(style="medium", color=C.accent))


def _page_setup(ws: Worksheet, last_col: int, last_row: int, landscape: bool, title_rows: str | None) -> None:
    ws.sheet_view.showGridLines = False
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.5
    ws.page_margins.top, ws.page_margins.bottom = 0.6, 0.6
    ws.print_options.horizontalCentered = True
    ws.print_area = f"A1:{get_column_letter(last_col)}{max(last_row, 1)}"
    if title_rows:
        ws.print_title_rows = title_rows
    ws.oddFooter.left.text = f"{T.BRAND} · Báo cáo hoạt động"
    ws.oddFooter.left.size = 8
    ws.oddFooter.right.text = "Trang &P / &N"
    ws.oddFooter.right.size = 8


def _table(ws: Worksheet, rep: dict, title: str, note: str, cols: Sequence[Col], rows: list[dict], empty: str,
           landscape: bool = False) -> tuple[int, int]:
    """Detail sheet; returns (first data row, last data row) or (0, 0) when empty."""
    n = len(cols)
    _title_band(ws, rep, title, note, n)
    for i, col in enumerate(cols, 1):
        c = _put(ws, HEAD_ROW, i, col.title)
        c.font = _font(10, True, "FFFFFF")
        c.fill = _fill(C.ink)
        c.alignment = Alignment(horizontal=col.align, vertical="center", wrap_text=True, indent=_indent(col))
        c.border = Border(left=INK_SIDE, right=INK_SIDE, top=INK_SIDE, bottom=INK_SIDE)
    ws.row_dimensions[HEAD_ROW].height = 30
    widths = [max(col.min_w, min(len(col.title) + 3, 22)) for col in cols]   # titles fit on one line when possible

    if not rows:
        r = HEAD_ROW + 1
        _put(ws, r, 1, empty).font = _font(10, color=C.muted, italic=True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=n)
        ws.cell(row=r, column=1).alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[r].height = 26
        for i in range(1, n + 1):
            ws.cell(row=r, column=i).border = Border(bottom=THIN)
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = max(w, 14)
        ws.freeze_panes = f"A{HEAD_ROW + 1}"
        _page_setup(ws, n, r, landscape, f"{HEAD_ROW}:{HEAD_ROW}")
        return 0, 0

    first = HEAD_ROW + 1
    for k, row in enumerate(rows):
        r = first + k
        band = _fill(C.zebra) if k % 2 else None
        for i, col in enumerate(cols, 1):
            if col.row_formula:
                v = None
                c = ws.cell(row=r, column=i, value=col.row_formula(r))
            else:
                v = col.key(row)
                c = _put(ws, r, i, v)
            c.font = _font(10, col.emphasis, C.ink if col.emphasis else C.ink2)
            c.alignment = Alignment(horizontal=col.align, vertical="center", indent=_indent(col))
            c.border = Border(bottom=THIN)
            if col.fmt and (col.row_formula or not isinstance(v, str)):
                c.number_format = col.fmt
            if band:
                c.fill = band
            widths[i - 1] = max(widths[i - 1], _text_len(v, col.fmt) + 2)
        ws.row_dimensions[r].height = 18
    last = first + len(rows) - 1

    tr = last + 1                                                    # total row: formulas over the rows above
    has_total = any(col.total for col in cols)
    if has_total:
        for i, col in enumerate(cols, 1):
            L = get_column_letter(i)
            if col.total == "label":
                c = _put(ws, tr, i, "Tổng cộng")
            elif col.total == "sum":
                c = ws.cell(row=tr, column=i, value=f"=SUM({L}{first}:{L}{last})")
                c.number_format = col.fmt or T.XL_INT
            elif col.total and col.total.startswith("="):            # a custom formula, {r} is the total row
                c = ws.cell(row=tr, column=i, value=col.total.format(r=tr, first=first, last=last))
                c.number_format = col.fmt or T.XL_INT
            else:
                c = ws.cell(row=tr, column=i)
            c.font = _font(10, True, C.ink)
            c.fill = _fill(C.field)
            c.alignment = Alignment(horizontal=col.align, vertical="center", indent=_indent(col))
            c.border = Border(top=Side(style="thin", color=C.ink), bottom=Side(style="double", color=C.ink))
        ws.row_dimensions[tr].height = 20

    for i, (w, col) in enumerate(zip(widths, cols), 1):
        ws.column_dimensions[get_column_letter(i)].width = min(col.max_w, w)
    ws.freeze_panes = f"A{first}"
    ws.auto_filter.ref = f"A{HEAD_ROW}:{get_column_letter(n)}{last}"
    _page_setup(ws, n, tr if has_total else last, landscape, f"{HEAD_ROW}:{HEAD_ROW}")
    return first, last


# ---------------------------------------------------------------------------------------------------------- overview
def _overview(ws: Worksheet, rep: dict, generated_at: datetime, exported_by: str | None) -> None:
    ws.title = "Tổng quan"
    rev, r_, late = rep["revenue"], rep["rates"], rep["late_completed"]
    widths = {"A": 34, "B": 22, "C": 62}
    for k, w in widths.items():
        ws.column_dimensions[k].width = w

    _put(ws, 1, 1, f"{T.BRAND} · {T.WORKSHOP}").font = _font(10, True, C.accent)
    _put(ws, 2, 1, "BÁO CÁO HOẠT ĐỘNG").font = _font(18, True, C.ink)
    _put(ws, 3, 1, f"{T.period_text(rep)} · {T.group_text(rep)}").font = _font(10, color=C.ink3)
    ws.row_dimensions[2].height = 28
    for c in range(1, 4):
        ws.cell(row=3, column=c).border = Border(bottom=Side(style="medium", color=C.accent))

    meta = [("Kỳ báo cáo, từ ngày", rep["from"], T.XL_DATE), ("Kỳ báo cáo, đến ngày", rep["to"], T.XL_DATE),
            ("Gom số liệu theo", T.GROUP_LABEL.get(rep["group"], rep["group"]), None),
            ("Thời điểm xuất (giờ Việt Nam)", generated_at.replace(tzinfo=None), T.XL_DATETIME)]
    if exported_by:
        meta.append(("Người xuất", exported_by, None))
    meta.append(("Nguồn dữ liệu", T.SOURCE, None))
    r = 5
    for label, value, fmt in meta:
        a = _put(ws, r, 1, label)
        a.font = _font(9, color=C.ink3)
        b = _put(ws, r, 2, value)
        b.font = _font(10, color=C.ink)
        b.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        if fmt:
            b.number_format = fmt
        if label == "Nguồn dữ liệu":
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
        for c in range(1, 4):
            ws.cell(row=r, column=c).fill = _fill(C.field)
        r += 1
    r += 1

    def none(v):           # a rate with no denominator is shown as a dash, not as 0 %
        return "–" if v is None else v

    payments = sum(int(x["payments"] or 0) for x in rev["series"])
    sections = [
        ("TÀI CHÍNH (TIỀN THỰC NHẬN, VND)", [
            ("Tiền đã nhận", rev["received"], T.XL_MONEY, "Cọc, thanh toán cuối và phí giao hàng đã thanh toán thành công, "
                                                         "tính theo ngày thanh toán", False),
            ("Tiền đã hoàn", rev["refunded"], T.XL_MONEY, "Khoản hoàn tiền đã hoàn tất trong kỳ", False),
            ("Doanh thu thuần", rev["net"], T.XL_MONEY, "Tiền đã nhận trừ tiền đã hoàn", True),
            ("Số giao dịch thu", payments, T.XL_INT, "Số lần thanh toán thành công (không gồm hoàn tiền)", False)]),
        ("ĐƠN HÀNG VÀ CHẤT LƯỢNG", [
            ("Đơn đã gửi", r_["submitted"], T.XL_INT, "Đơn khách gửi trong kỳ", False),
            ("Đơn bị từ chối", r_["rejected"], T.XL_INT, "Đơn chuyển sang Từ chối trong kỳ", False),
            ("Tỷ lệ từ chối", none(r_["reject_rate"]), T.XL_PCT, "Đơn bị từ chối / đơn đã gửi", True),
            ("Đơn hoàn tất", late["of_completed"], T.XL_INT, "Đơn hoàn tất trong kỳ (mọi loại đơn)", False),
            ("Job viết lần đầu", r_["jobs_written"], T.XL_INT, "Job robot viết xong lần đầu", False),
            ("Job viết lại", r_["rewrites"], T.XL_INT, "Job phải viết lại sau QC hoặc nghiệm thu", False),
            ("Tỷ lệ viết lại", none(r_["rewrite_rate"]), T.XL_PCT, "Job viết lại / job viết lần đầu", True)]),
        ("TIẾN ĐỘ VÀ THIẾT BỊ", [
            ("Đơn hoàn tất trễ ETA", late["count"], T.XL_INT, "Ngày hoàn tất sau ETA đã hẹn", False),
            ("Tỷ lệ trễ ETA", none(late["late_rate"]), T.XL_PCT, "Đơn trễ / đơn hoàn tất", True),
            ("Phút robot viết", sum(int(x["writing_minutes"] or 0) for x in rep["robots"]), T.XL_INT,
             "Tổng thời gian viết của mọi robot", False),
            ("Sự cố robot", sum(int(x["incidents"] or 0) for x in rep["robots"]), T.XL_INT,
             "Sự cố ghi nhận trong kỳ", False)]),
    ]
    for head, items in sections:
        for c, title in enumerate(("Chỉ số", "Giá trị", "Cách tính"), 1):
            cell = _put(ws, r, c, head if c == 1 else title)
            cell.font = _font(10, True, "FFFFFF")
            cell.fill = _fill(C.ink)
            cell.alignment = Alignment(horizontal="right" if c == 2 else "left", vertical="center")
        ws.row_dimensions[r].height = 22
        r += 1
        for k, (label, value, fmt, note, key) in enumerate(items):
            a, b, c = _put(ws, r, 1, label), _put(ws, r, 2, value), _put(ws, r, 3, note)
            a.font = _font(10, key, C.ink)
            b.font = _font(11 if key else 10, key, C.accent if key and value != "–" else (C.muted if value == "–" else C.ink))
            b.alignment = Alignment(horizontal="right", vertical="center")
            if not isinstance(value, str):
                b.number_format = fmt
            c.font = _font(9, color=C.ink3)
            c.alignment = Alignment(vertical="center", wrap_text=True)
            for cell in (a, b, c):
                cell.border = Border(bottom=THIN)
                if k % 2:
                    cell.fill = _fill(C.zebra)
            if label == "Doanh thu thuần" and isinstance(value, int) and value < 0:
                b.font = _font(11, True, C.danger)
            ws.row_dimensions[r].height = 18
            r += 1
        r += 1
    _put(ws, r, 1, "Các trang chi tiết: Doanh thu, Sản lượng, Robot, Trễ ETA. Dòng Tổng cộng ở mỗi trang được tính "
                   "bằng công thức từ các dòng phía trên.").font = _font(9, color=C.ink3, italic=True)
    ws.freeze_panes = None
    _page_setup(ws, 3, r, False, None)


# ---------------------------------------------------------------------------------------------------------- the chart
def _revenue_chart(ws: Worksheet, series: list[dict], group: str, first: int, last: int) -> None:
    """Columns: received (accent) and refunded (grey) beside the table. Up to 62 periods the chart reads the table itself;
    a longer series (a year by day) is summed per calendar month into a small labelled table under the chart, the same
    rule as the PDF, so the columns stay readable."""
    anchor_col = 7                                   # G
    if len(series) <= 62:
        cats = Reference(ws, min_col=1, min_row=first, max_row=last)
        data = Reference(ws, min_col=2, max_col=3, min_row=HEAD_ROW, max_row=last)
        cat_fmt = T.XL_MONTH if group == "month" else "dd/mm"
    else:
        months: dict[date, list[int]] = {}
        for x in series:
            m = months.setdefault(x["bucket"].replace(day=1), [0, 0])
            m[0] += int(x["received"])
            m[1] += int(x["refunded"])
        top = HEAD_ROW + 19
        _put(ws, top - 1, anchor_col, "Cộng dồn theo tháng (nguồn của biểu đồ)").font = _font(9, True, C.ink3)
        for i, title in enumerate(("Tháng", "Tiền đã nhận (đ)", "Tiền đã hoàn (đ)")):
            c = _put(ws, top, anchor_col + i, title)
            c.font, c.fill = _font(9, True, "FFFFFF"), _fill(C.ink)
            c.alignment = Alignment(horizontal="center" if i == 0 else "right", indent=0 if i == 0 else 1)
        for k, mon in enumerate(sorted(months)):
            r = top + 1 + k
            for i, (v, fmt) in enumerate(((mon, T.XL_MONTH), (months[mon][0], T.XL_MONEY), (months[mon][1], T.XL_MONEY))):
                c = ws.cell(row=r, column=anchor_col + i, value=v)
                c.number_format, c.font, c.border = fmt, _font(9), Border(bottom=THIN)
                c.alignment = Alignment(horizontal="center" if i == 0 else "right", indent=0 if i == 0 else 1)
        for i, w in enumerate((10, 18, 18)):
            ws.column_dimensions[get_column_letter(anchor_col + i)].width = w
        end = top + len(months)
        cats = Reference(ws, min_col=anchor_col, min_row=top + 1, max_row=end)
        data = Reference(ws, min_col=anchor_col + 1, max_col=anchor_col + 2, min_row=top, max_row=end)
        cat_fmt = T.XL_MONTH
    ch = BarChart()
    ch.type, ch.grouping, ch.overlap, ch.gapWidth = "col", "clustered", -10, 80
    ch.x_axis.delete = ch.y_axis.delete = False      # openpyxl 3.1 hides both axes in Excel unless told otherwise
    ch.y_axis.numFmt, ch.x_axis.numFmt = "#,##0", cat_fmt
    ch.x_axis.number_format = cat_fmt
    ch.add_data(data, titles_from_data=True)
    ch.set_categories(cats)
    for s, color in zip(ch.series, (C.accent, C.ink3)):
        s.graphicalProperties.solidFill = color
        s.graphicalProperties.line.solidFill = color
    ch.legend.position = "t"
    ch.legend.overlay = False
    ch.height, ch.width = 8.5, 19
    ws.add_chart(ch, f"{get_column_letter(anchor_col)}{HEAD_ROW}")
    ws.page_setup.orientation = "landscape"          # the chart sits beside the table: print both
    ws.print_area = f"A1:Q{max(last + 1, ws.max_row, HEAD_ROW + 18)}"


# ------------------------------------------------------------------------------------------------------- the workbook
def render(rep: dict[str, Any], generated_at: datetime, exported_by: str | None = None) -> bytes:
    wb = Workbook()
    _overview(wb.active, rep, generated_at, exported_by)
    group = rep["group"]

    ws = wb.create_sheet("Doanh thu")
    series = rep["revenue"]["series"]
    first, last = _table(ws, rep, f"Doanh thu theo {T.GROUP_LABEL.get(group, group)}",
                         "Tiền thực nhận: thanh toán thành công tính theo ngày thanh toán, trừ khoản hoàn tiền đã hoàn tất.", [
        Col(T.BUCKET_HEAD.get(group, "Kỳ"), lambda x: x["bucket"], T.XL_MONTH if group == "month" else T.XL_DATE,
            total="label", min_w=14),
        Col("Tiền đã nhận (đ)", lambda x: x["received"], T.XL_MONEY, total="sum", min_w=16),
        Col("Tiền đã hoàn (đ)", lambda x: x["refunded"], T.XL_MONEY, total="sum", min_w=16),
        Col("Doanh thu thuần (đ)", lambda x: x["net"], T.XL_MONEY, total="sum", min_w=18, emphasis=True),
        Col("Số giao dịch thu", lambda x: x["payments"], T.XL_INT, total="sum", min_w=12),
    ], series, "Không có giao dịch thanh toán nào trong kỳ báo cáo.")
    if first and last > first:                       # a chart only says something with at least two periods
        _revenue_chart(ws, series, group, first, last)

    ws = wb.create_sheet("Sản lượng")
    out = rep["output_by_type"]
    _first, _last = HEAD_ROW + 1, HEAD_ROW + len(out)
    _table(ws, rep, "Sản lượng theo loại đơn", "Đơn đã hoàn tất trong kỳ, tính theo ngày hoàn tất. Giá trị là tổng tiền đơn.", [
        Col("Loại đơn", lambda x: T.order_type(x["order_type"]), total="label", min_w=30),
        Col("Mã loại", lambda x: x["order_type"], min_w=18),
        Col("Số đơn", lambda x: x["orders"], T.XL_INT, total="sum"),
        Col("Số bản", lambda x: x["quantity"], T.XL_INT, total="sum"),
        Col("Giá trị đơn (đ)", lambda x: x["total_amount"], T.XL_MONEY, total="sum", min_w=16, emphasis=True),
        Col("Tỷ trọng giá trị", lambda x: None, T.XL_PCT, total="=IFERROR(SUM(F{first}:F{last}),0)", min_w=12,
            row_formula=lambda r: f"=IFERROR(E{r}/SUM(E${_first}:E${_last}),0)"),
    ], out, "Không có đơn hoàn tất nào trong kỳ báo cáo.")

    ws = wb.create_sheet("Robot")
    robots = rep["robots"]
    first, last = _table(ws, rep, "Hoạt động robot", "Job viết xong và phút viết tính theo ngày kết thúc job; sự cố theo ngày ghi nhận.", [
        Col("Robot", lambda x: x["robot_code"], total="label", min_w=16, emphasis=True),
        Col("Job đã viết", lambda x: x["jobs_written"], T.XL_INT, total="sum", min_w=12),
        Col("Phút viết", lambda x: x["writing_minutes"], T.XL_INT, total="sum", min_w=12),
        Col("Sự cố", lambda x: x["incidents"], T.XL_INT, total="sum"),
    ], robots, "Chưa có robot nào trong hệ thống.")
    for k, x in enumerate(robots):                   # a robot with incidents stands out (any incident, no threshold)
        if int(x["incidents"] or 0) > 0:
            ws.cell(row=first + k, column=4).font = _font(10, True, C.danger)

    ws = wb.create_sheet("Trễ ETA")
    lc = rep["late_completed"]
    note = (f"{lc['count']} trên {lc['of_completed']} đơn hoàn tất trong kỳ xong sau ETA, sắp theo số ngày trễ giảm dần"
            + (" (danh sách giới hạn 500 đơn)." if len(lc["orders"]) >= 500 else "."))
    first, last = _table(ws, rep, "Đơn hoàn tất trễ ETA", note, [
        Col("Mã đơn", lambda x: x["code"], min_w=16, emphasis=True),
        Col("ETA đã hẹn", lambda x: x["eta"], T.XL_DATE, min_w=12),
        Col("Ngày hoàn tất", lambda x: x["completed_on"], T.XL_DATE, min_w=13),
        Col("Trễ (ngày)", lambda x: x["days_late"], T.XL_INT, min_w=11),
        Col("Đã dời ETA (ngày)", lambda x: x["eta_postponed_days"] or 0, T.XL_INT, min_w=12),
    ], lc["orders"], "Không có đơn nào hoàn tất trễ ETA trong kỳ báo cáo.")
    if first:
        ws.conditional_formatting.add(f"D{first}:D{last}", DataBarRule(
            start_type="num", start_value=0, end_type="max", color=C.accent_mid))

    wb.calculation.fullCalcOnLoad = True             # totals are formulas; recompute when the file opens
    wb.properties.title = f"Báo cáo hoạt động {T.d(rep['from'])} đến {T.d(rep['to'])}"
    wb.properties.creator = f"{T.BRAND} · {T.WORKSHOP}"
    wb.properties.subject = "Báo cáo Manager (FR-50)"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

