"""Manager report as PDF (FR-50, UC-46): the same figures as the Excel export, laid out as an A4 portrait business report.

Layout: brand header and title on page 1, a short running header on the next pages, KPI tiles, a revenue chart (only when
there are at least two periods), then one table per section. Tables repeat their column titles on every page, keep a
section title with its first rows, and end with a total row. Footer on every page: brand, export time, data source note,
"Trang x/y". DejaVu Sans is embedded because the built-in PDF fonts cannot draw Vietnamese. Colours and formats come from
`report_theme` (the workshop palette of the web app).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from fpdf import FPDF

from app.services import report_theme as T
from app.services.report_theme import C, rgb

MARGIN = 16.0
ROW_H = 6.4
HEAD_H = 7.4
FOOT_SPACE = 18.0


def _ellipsis(pdf: FPDF, text: str, width: float) -> str:
    """Shorten text that would not fit a cell (keeps tables inside the page; never seen with today's codes)."""
    if pdf.get_string_width(text) <= width:
        return text
    while text and pdf.get_string_width(text + "…") > width:
        text = text[:-1]
    return text + "…"


@dataclass
class Column:
    title: str
    width: float           # share of the table width; normalised in _table
    align: str = "L"       # L / R / C
    bold: bool = False


class _Pdf(FPDF):
    generated: str = ""
    running: str = ""

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_y(9)
        self.set_font("dv", "B", 8)
        self.set_text_color(*rgb(C.accent))
        self.cell(20, 5, T.BRAND)
        self.set_font("dv", "", 8)
        self.set_text_color(*rgb(C.ink3))
        self.cell(0, 5, self.running, align="R")
        self.set_draw_color(*rgb(C.line))
        self.set_line_width(0.3)
        self.line(MARGIN, 15, self.w - MARGIN, 15)
        self.set_y(20)

    def footer(self) -> None:
        y = self.h - 13
        self.set_draw_color(*rgb(C.line))
        self.set_line_width(0.3)
        self.line(MARGIN, y, self.w - MARGIN, y)
        self.set_xy(MARGIN, y + 1.5)
        self.set_font("dv", "B", 7.5)
        self.set_text_color(*rgb(C.ink))
        self.cell(self.get_string_width(T.BRAND) + 1.5, 4, T.BRAND)
        self.set_font("dv", "", 7.5)
        self.set_text_color(*rgb(C.ink3))
        self.cell(0, 4, f"· {T.WORKSHOP} · Báo cáo nội bộ · Xuất lúc {self.generated}")
        self.set_x(MARGIN)
        self.cell(0, 4, f"Trang {self.page_no()}/{{nb}}", align="R")
        self.set_xy(MARGIN, y + 5.5)
        self.set_font("dv", "", 6.5)
        self.set_text_color(*rgb(C.muted))
        self.cell(0, 3.5, T.SOURCE)
        self.set_text_color(*rgb(C.ink))

    @property
    def body_w(self) -> float:
        return self.w - 2 * MARGIN

    def space_left(self) -> float:
        return self.page_break_trigger - self.get_y()


# ------------------------------------------------------------------------------------------------------- building blocks
def _first_page_header(pdf: _Pdf, rep: dict, exported_by: str | None) -> None:
    top = 13
    if T.LOGO.exists():
        pdf.image(str(T.LOGO), x=MARGIN, y=top, h=13)             # 900 x 365 px source, ratio kept by fpdf (h only)
    pdf.set_xy(MARGIN, top + 1)
    pdf.set_font("dv", "B", 9)
    pdf.set_text_color(*rgb(C.ink))
    pdf.cell(0, 5, T.WORKSHOP, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 8)
    pdf.set_text_color(*rgb(C.ink3))
    pdf.cell(0, 4.5, "Hệ thống viết tay tiếng Việt bằng robot", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4.5, "Báo cáo nội bộ dành cho Manager", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(top + 19)
    pdf.set_draw_color(*rgb(C.line))
    pdf.set_line_width(0.3)
    pdf.line(MARGIN, pdf.get_y(), pdf.w - MARGIN, pdf.get_y())
    pdf.set_fill_color(*rgb(C.accent))
    pdf.rect(MARGIN, pdf.get_y() - 0.6, 24, 1.2, style="F")      # short accent mark on the rule

    pdf.ln(6)
    pdf.set_font("dv", "", 8)
    pdf.set_text_color(*rgb(C.accent))
    pdf.cell(0, 4.5, "BÁO CÁO HOẠT ĐỘNG · FR-50", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "B", 19)
    pdf.set_text_color(*rgb(C.ink))
    pdf.cell(0, 10, "Doanh thu, sản lượng và vận hành", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 10)
    pdf.set_text_color(*rgb(C.ink2))
    pdf.cell(0, 6, f"{T.period_text(rep)} · {T.group_text(rep)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    meta = [("Kỳ báo cáo", f"{T.d(rep['from'])} đến {T.d(rep['to'])}", 1.25),
            ("Gom theo", T.GROUP_LABEL.get(rep["group"], rep["group"]).capitalize(), 0.6),
            ("Thời điểm xuất", pdf.generated, 0.9)]
    if exported_by:
        meta.append(("Người xuất", exported_by, 1.25))
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
        size = 9.0
        pdf.set_font("dv", "B", size)
        while pdf.get_string_width(value) > w - 6 and size > 7:          # shrink a long name before cutting it
            size -= 0.25
            pdf.set_font("dv", "B", size)
        pdf.set_text_color(*rgb(C.ink))
        pdf.cell(w - 6, 5, _ellipsis(pdf, value, w - 6))
        x += w
    pdf.set_y(y + 13 + 6)


def _section(pdf: _Pdf, title: str, caption: str | None, need: float) -> None:
    """Section title; starts a new page when the title and `need` mm after it would not fit."""
    if pdf.space_left() < 13 + need:
        pdf.add_page()
    pdf.set_font("dv", "B", 11.5)
    pdf.set_text_color(*rgb(C.ink))
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
    if caption:
        pdf.set_font("dv", "", 8)
        pdf.set_text_color(*rgb(C.ink3))
        pdf.multi_cell(0, 4.2, caption, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.8)


def _tiles(pdf: _Pdf, tiles: Sequence[tuple[str, str, str, str | None]], accent: bool = False) -> None:
    """One row of KPI tiles: (label, value, note, value colour or None). With accent, the first tile carries the accent bar."""
    gap = 3.0
    w = (pdf.body_w - gap * (len(tiles) - 1)) / len(tiles)
    h = 22.0
    y = pdf.get_y()
    for i, (label, value, note, color) in enumerate(tiles):
        x = MARGIN + i * (w + gap)
        pdf.set_fill_color(*rgb(C.field))
        pdf.rect(x, y, w, h, style="F")
        if accent and i == 0:
            pdf.set_fill_color(*rgb(C.accent))
            pdf.rect(x, y, 1.2, h, style="F")
        pdf.set_xy(x + 4, y + 2.6)
        pdf.set_font("dv", "", 7)
        pdf.set_text_color(*rgb(C.ink3))
        pdf.cell(w - 6, 4, _ellipsis(pdf, label.upper(), w - 6))
        pdf.set_xy(x + 4, y + 7.5)
        size = 14
        pdf.set_font("dv", "B", size)
        while pdf.get_string_width(value) > w - 7 and size > 9:          # long amounts shrink instead of overflowing
            size -= 0.5
            pdf.set_font("dv", "B", size)
        pdf.set_text_color(*rgb(color or C.ink))
        pdf.cell(w - 6, 7, value)
        pdf.set_xy(x + 4, y + 15.5)
        pdf.set_font("dv", "", 6.8)
        pdf.set_text_color(*rgb(C.ink3))
        pdf.cell(w - 6, 4, _ellipsis(pdf, note, w - 6))
    pdf.set_text_color(*rgb(C.ink))
    pdf.set_y(y + h + gap)


def _table(pdf: _Pdf, cols: Sequence[Column], rows: list[Sequence[str]], total: Sequence[str] | None, empty: str,
           highlight: dict[tuple[int, int], str] | None = None) -> None:
    share = sum(c.width for c in cols)
    widths = [c.width / share * pdf.body_w for c in cols]
    highlight = highlight or {}

    def head() -> None:
        pdf.set_fill_color(*rgb(C.ink))
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("dv", "B", 8)
        x = MARGIN
        y = pdf.get_y()
        pdf.rect(MARGIN, y, pdf.body_w, HEAD_H, style="F")
        for c, w in zip(cols, widths):
            pdf.set_xy(x + 2, y)
            pdf.cell(w - 4, HEAD_H, _ellipsis(pdf, c.title, w - 4), align=c.align)
            x += w
        pdf.set_y(y + HEAD_H)
        pdf.set_text_color(*rgb(C.ink))

    head()
    if not rows:
        y = pdf.get_y()
        pdf.set_font("dv", "", 8.5)
        pdf.set_text_color(*rgb(C.muted))
        pdf.cell(pdf.body_w, ROW_H + 3, empty, align="C")
        pdf.set_draw_color(*rgb(C.line))
        pdf.line(MARGIN, y + ROW_H + 3, pdf.w - MARGIN, y + ROW_H + 3)
        pdf.set_y(y + ROW_H + 3 + 7)
        pdf.set_text_color(*rgb(C.ink))
        return

    LINE_H = 4.0

    def height(values: Sequence[str], is_total: bool = False) -> float:
        """Row height: long text wraps inside its cell instead of being cut, so nothing is lost."""
        n = 1
        for c, w, v in zip(cols, widths, values):
            pdf.set_font("dv", "B" if is_total or c.bold else "", 8.3)
            if pdf.get_string_width(v) > w - 4:
                n = max(n, len(pdf.multi_cell(w - 4, LINE_H, v, dry_run=True, output="LINES")))
        return max(ROW_H, n * LINE_H + 2.4) + (0.6 if is_total else 0)

    def line(values: Sequence[str], k: int, h: float, is_total: bool = False) -> None:
        y = pdf.get_y()
        if is_total:
            pdf.set_fill_color(*rgb(C.field))
            pdf.rect(MARGIN, y, pdf.body_w, h, style="F")
        elif k % 2:
            pdf.set_fill_color(*rgb(C.zebra))
            pdf.rect(MARGIN, y, pdf.body_w, h, style="F")
        x = MARGIN
        for i, (c, w, v) in enumerate(zip(cols, widths, values)):
            bold = is_total or c.bold
            pdf.set_font("dv", "B" if bold else "", 8.3)
            pdf.set_text_color(*rgb(highlight.get((k, i)) or (C.ink if bold else C.ink2)))
            if pdf.get_string_width(v) > w - 4:
                pdf.set_xy(x + 2, y + 1.2)
                pdf.multi_cell(w - 4, LINE_H, v, align=c.align)
            else:
                pdf.set_xy(x + 2, y)
                pdf.cell(w - 4, h, v, align=c.align)
            x += w
        pdf.set_draw_color(*rgb(C.ink if is_total else C.line))
        pdf.set_line_width(0.35 if is_total else 0.2)
        pdf.line(MARGIN, y + (0 if is_total else h), pdf.w - MARGIN, y + (0 if is_total else h))
        pdf.set_y(y + h)

    total_h = height(total, True) if total else 0.0
    for k, row in enumerate(rows):
        h = height(row)
        if pdf.will_page_break(h + (total_h if k == len(rows) - 1 else 0)):
            pdf.add_page()                       # the last row moves with the total row, the column titles repeat
            head()
        line(row, k, h)
    if total:
        line(total, -1, total_h, is_total=True)
    pdf.set_text_color(*rgb(C.ink))
    pdf.set_line_width(0.2)
    pdf.ln(7)


def _chart(pdf: _Pdf, labels: list[str], received: list[int], refunded: list[int]) -> None:
    """Grouped columns: money received (accent) and refunded (grey) per period. Axis from 0, 4 gridlines, no 3D."""
    h, axis_w = 52.0, 18.0
    y0 = pdf.get_y()
    top = max(max(received, default=0), max(refunded, default=0), 1)
    step = _nice(top / 4)
    top = step * 4
    plot_x, plot_w, plot_h = MARGIN + axis_w, pdf.body_w - axis_w, h - 14
    base = y0 + 4 + plot_h
    pdf.set_font("dv", "", 6.5)
    for i in range(5):                                    # gridlines + values
        y = base - plot_h * i / 4
        pdf.set_draw_color(*rgb(C.line))
        pdf.set_line_width(0.2)
        pdf.line(plot_x, y, plot_x + plot_w, y)
        pdf.set_text_color(*rgb(C.ink3))
        pdf.set_xy(MARGIN, y - 2)
        pdf.cell(axis_w - 2, 4, _short_money(step * i), align="R")
    n = len(labels)
    slot = plot_w / n
    bar = min(6.0, slot * 0.36)
    every = max(1, round(n / 12))                         # at most ~12 period labels under the axis
    for i in range(n):
        cx = plot_x + slot * i + slot / 2
        for v, color, dx in ((received[i], C.accent, -bar), (refunded[i], C.ink3, 0)):
            bh = plot_h * v / top
            if bh > 0:
                pdf.set_fill_color(*rgb(color))
                pdf.rect(cx + dx, base - bh, bar, bh, style="F")
        if i % every == 0:
            pdf.set_text_color(*rgb(C.ink3))
            pdf.set_xy(cx - slot * every / 2, base + 1)
            pdf.cell(slot * every, 4, _ellipsis(pdf, labels[i], slot * every), align="C")
    pdf.set_draw_color(*rgb(C.ink3))
    pdf.line(plot_x, base, plot_x + plot_w, base)
    ly = base + 6.5                                       # legend
    for x, color, text in ((plot_x, C.accent, "Tiền đã nhận"), (plot_x + 34, C.ink3, "Tiền đã hoàn")):
        pdf.set_fill_color(*rgb(color))
        pdf.rect(x, ly + 1, 3, 3, style="F")
        pdf.set_xy(x + 4.5, ly)
        pdf.set_text_color(*rgb(C.ink2))
        pdf.cell(28, 5, text)
    pdf.set_text_color(*rgb(C.ink))
    pdf.set_y(y0 + h + 4)


def _chart_points(series: list[dict], group: str) -> tuple[list[str], list[int], list[int]]:
    """Chart points. Up to 62 periods are drawn one by one; more (a long period by day or week) are summed per calendar
    month for the chart only, so the columns stay readable. Day labels drop the year, which the report title carries."""
    if len(series) <= 62:
        fmt = (lambda b: b.strftime("%d/%m")) if group == "day" else (lambda b: T.bucket(b, group).replace("Tuần ", ""))
        return [fmt(x["bucket"]) for x in series], [int(x["received"]) for x in series], [int(x["refunded"]) for x in series]
    months: dict[tuple[int, int], list[int]] = {}
    for x in series:
        m = months.setdefault((x["bucket"].year, x["bucket"].month), [0, 0])
        m[0] += int(x["received"])
        m[1] += int(x["refunded"])
    keys = sorted(months)
    return [f"{mo:02d}/{y}" for y, mo in keys], [months[k][0] for k in keys], [months[k][1] for k in keys]


def _nice(x: float) -> int:
    if x <= 0:
        return 1
    import math
    p = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 2.5, 5, 10):
        if x <= m * p:
            return int(m * p) or 1
    return int(10 * p)


def _short_money(v: int) -> str:
    if v >= 1_000_000_000:
        return f"{v / 1e9:g} tỷ".replace(".", ",")
    if v >= 1_000_000:
        return f"{v / 1e6:g} tr".replace(".", ",")
    if v >= 1_000:
        return f"{v / 1e3:g} nghìn".replace(".", ",")
    return str(v)


# ----------------------------------------------------------------------------------------------------------- document
def render(rep: dict[str, Any], generated_at: datetime, exported_by: str | None = None) -> bytes:
    pdf = _Pdf(format="A4", unit="mm")
    pdf.generated = generated_at.strftime("%H:%M %d/%m/%Y")
    pdf.running = f"Báo cáo hoạt động · {T.period_text(rep)}"
    pdf.set_margins(MARGIN, 20, MARGIN)
    pdf.set_auto_page_break(True, margin=FOOT_SPACE)
    pdf.add_font("dv", "", str(T.ASSETS / "fonts" / "DejaVuSans.ttf"))
    pdf.add_font("dv", "B", str(T.ASSETS / "fonts" / "DejaVuSans-Bold.ttf"))
    pdf.set_title(f"Báo cáo hoạt động {T.d(rep['from'])} đến {T.d(rep['to'])}")
    pdf.set_author(f"{T.BRAND} · {T.WORKSHOP}")
    pdf.set_subject("Báo cáo Manager (FR-50)")
    pdf.set_creator(T.BRAND)
    pdf.add_page()
    _first_page_header(pdf, rep, exported_by)

    rev, r, late = rep["revenue"], rep["rates"], rep["late_completed"]
    payments = sum(int(x["payments"] or 0) for x in rev["series"])
    _section(pdf, "Tổng quan", None, 50)
    _tiles(pdf, [
        ("Doanh thu thuần", T.money(rev["net"], unit=True), "Tiền đã nhận trừ tiền đã hoàn",
         C.danger if int(rev["net"] or 0) < 0 else None),
        ("Tiền đã nhận", T.money(rev["received"], unit=True), f"{T.num(payments)} giao dịch thành công", None),
        ("Tiền đã hoàn", T.money(rev["refunded"], unit=True), "Khoản hoàn đã hoàn tất", None),
    ], accent=True)
    _tiles(pdf, [
        ("Đơn đã gửi", T.num(r["submitted"]), f"{T.num(r['rejected'])} đơn bị từ chối", None),
        ("Tỷ lệ từ chối", T.pct(r["reject_rate"]), "Từ chối / đơn đã gửi", C.muted if r["reject_rate"] is None else None),
        ("Tỷ lệ viết lại", T.pct(r["rewrite_rate"]), f"{T.num(r['rewrites'])} / {T.num(r['jobs_written'])} job",
         C.muted if r["rewrite_rate"] is None else None),
        ("Trễ ETA", T.pct(late["late_rate"]), f"{T.num(late['count'])} / {T.num(late['of_completed'])} đơn hoàn tất",
         C.muted if late["late_rate"] is None else None),
    ])
    pdf.ln(4)

    group = rep["group"]
    series = rev["series"]
    _section(pdf, f"Doanh thu theo {T.GROUP_LABEL.get(group, group)}",
             "Tiền thực nhận: cọc, thanh toán cuối và phí giao hàng đã thanh toán thành công, tính theo ngày thanh toán, "
             "trừ khoản hoàn tiền đã hoàn tất.", 60 if len(series) >= 2 else 25)
    if len(series) >= 2:
        labels, received, refunded = _chart_points(series, group)
        _chart(pdf, labels, received, refunded)
        if len(labels) < len(series):
            pdf.set_font("dv", "", 7.5)
            pdf.set_text_color(*rgb(C.ink3))
            pdf.cell(0, 4, f"Biểu đồ cộng dồn theo tháng để dễ đọc; bảng bên dưới giữ chi tiết theo "
                           f"{T.GROUP_LABEL.get(group, group)}.", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
    neg = {(k, 3): C.danger for k, x in enumerate(series) if int(x["net"]) < 0}
    _table(pdf, [Column(T.BUCKET_HEAD.get(group, "Kỳ"), 30), Column("Tiền đã nhận (đ)", 30, "R"),
                 Column("Tiền đã hoàn (đ)", 30, "R"), Column("Doanh thu thuần (đ)", 32, "R", bold=True),
                 Column("Giao dịch", 18, "R")],
           [(T.bucket(x["bucket"], group), T.money(x["received"]), T.money(x["refunded"]), T.money(x["net"]),
             T.num(x["payments"])) for x in series],
           ("Tổng cộng", T.money(rev["received"]), T.money(rev["refunded"]), T.money(rev["net"]), T.num(payments)),
           "Không có giao dịch thanh toán nào trong kỳ báo cáo.", neg)

    out = rep["output_by_type"]
    _section(pdf, "Sản lượng theo loại đơn", "Đơn đã hoàn tất trong kỳ, tính theo ngày hoàn tất. Giá trị là tổng tiền đơn.", 25)
    value_sum = sum(int(x["total_amount"]) for x in out)
    _table(pdf, [Column("Loại đơn", 56), Column("Số đơn", 16, "R"), Column("Số bản", 16, "R"),
                 Column("Giá trị đơn (đ)", 26, "R", bold=True), Column("Tỷ trọng", 16, "R")],
           [(T.order_type(x["order_type"]), T.num(x["orders"]), T.num(x["quantity"]), T.money(x["total_amount"]),
             T.pct(int(x["total_amount"]) / value_sum if value_sum else None)) for x in out],
           ("Tổng cộng", T.num(sum(int(x["orders"]) for x in out)), T.num(sum(int(x["quantity"]) for x in out)),
            T.money(value_sum), T.pct(1.0) if value_sum else "–"),
           "Không có đơn hoàn tất nào trong kỳ báo cáo.")

    robots = rep["robots"]
    _section(pdf, "Hoạt động robot", "Job viết xong và phút viết tính theo ngày kết thúc job; sự cố theo ngày ghi nhận.", 25)
    _table(pdf, [Column("Robot", 40, bold=True), Column("Job đã viết", 25, "R"), Column("Phút viết", 25, "R"),
                 Column("Sự cố", 20, "R")],
           [(x["robot_code"], T.num(x["jobs_written"]), T.num(x["writing_minutes"]), T.num(x["incidents"])) for x in robots],
           ("Tổng cộng", T.num(sum(int(x["jobs_written"]) for x in robots)),
            T.num(sum(int(x["writing_minutes"]) for x in robots)), T.num(sum(int(x["incidents"]) for x in robots))),
           "Chưa có robot nào trong hệ thống.",
           {(k, 3): C.danger for k, x in enumerate(robots) if int(x["incidents"] or 0) > 0})

    orders = late["orders"]
    cap = (f"{T.num(late['count'])} trên {T.num(late['of_completed'])} đơn hoàn tất trong kỳ xong sau ETA, "
           "sắp theo số ngày trễ giảm dần" + (" (danh sách giới hạn 500 đơn)." if len(orders) >= 500 else "."))
    _section(pdf, "Đơn hoàn tất trễ ETA", cap, 25)
    _table(pdf, [Column("Mã đơn", 34, bold=True), Column("ETA đã hẹn", 24, "C"), Column("Ngày hoàn tất", 24, "C"),
                 Column("Trễ (ngày)", 18, "R", bold=True), Column("Đã dời ETA (ngày)", 24, "R")],
           [(x["code"], T.d(x["eta"]), T.d(x["completed_on"]), T.num(x["days_late"]), T.num(x["eta_postponed_days"] or 0))
            for x in orders], None, "Không có đơn nào hoàn tất trễ ETA trong kỳ báo cáo.")
    return bytes(pdf.output())
