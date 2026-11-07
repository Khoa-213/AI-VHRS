"""Manager (Phase 5b): production dashboard (UC-45) and reports (UC-46, FR-50), with an Excel export.

Revenue is CASH received (owner's decision 2026-11-07): DEPOSIT / FINAL / SHIPPING payments that succeeded, counted on the day
they were paid, minus REFUNDs that succeeded on the day they were paid back. Days, weeks and months are those of the workshop
(Asia/Ho_Chi_Minh). Every figure is read straight from the database; nothing is cached.
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError

TZ = "Asia/Ho_Chi_Minh"
VN = timezone(timedelta(hours=7))
GROUPS = ("day", "week", "month")
MAX_DAYS = 366
LOW_PAPER = 10                              # sheets
ETA_OPEN = ("CONFIRMED", "AWAITING_ACCEPTANCE", "AWAITING_FINAL_PAYMENT", "READY_TO_DELIVER", "DELIVERING")


def _today() -> date:
    return datetime.now(VN).date()


def _rows(session: Session, sql: str, **p) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in session.execute(text(sql), p)]


def _num(v: Any) -> int:
    return int(v or 0)


class ReportService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ UC-45
    def dashboard(self) -> dict[str, Any]:
        s, today = self.session, _today()
        by_status = {r["status"]: r["n"] for r in _rows(s, """
            select order_status::text as status, count(*) as n from orders
            where order_status not in ('DRAFT', 'COMPLETED', 'CANCELLED', 'REJECTED') group by 1""")}
        jobs_today = _rows(s, f"""
            select j.id as job_id, j.order_id, o.code as order_code, j.robot_id, r.code as robot_code, j.technician_id,
                   j.status::text as status, j.slot_start, j.slot_end, j.is_rewrite
            from production_jobs j join orders o on o.id = j.order_id join robots r on r.id = j.robot_id
            where (j.slot_start at time zone '{TZ}')::date = :d and j.status::text <> 'CANCELLED'
            order by j.slot_start, j.id""", d=today)
        upcoming = _num(s.execute(text(f"""
            select count(*) from production_jobs where status::text = 'SCHEDULED'
            and (slot_start at time zone '{TZ}')::date > :d and (slot_start at time zone '{TZ}')::date <= :d + 7"""),
            {"d": today}).scalar())
        open_list = ", ".join(f"'{x}'" for x in ETA_OPEN)
        late = _rows(s, f"""
            select id as order_id, code, order_status::text as status, eta, (:d - eta) as days_late, assigned_staff_id
            from orders where eta < :d and order_status::text in ({open_list}) order by eta, id limit 100""", d=today)
        due_soon = _rows(s, f"""
            select id as order_id, code, order_status::text as status, eta, assigned_staff_id
            from orders where eta between :d and :d + 2 and order_status::text in ('CONFIRMED', 'AWAITING_ACCEPTANCE')
            order by eta, id limit 100""", d=today)
        low_stock = (
            _rows(s, "select 'PAPER' as kind, id, name, stock_qty from paper_types where is_active and stock_qty < :n "
                     "order by stock_qty, id", n=LOW_PAPER)
            + _rows(s, "select 'PEN' as kind, id, name, stock_qty from pen_types where is_active and stock_qty < 1 order by id")
            + _rows(s, "select 'INK' as kind, id, name, stock_qty from ink_colors where is_active and stock_qty < 1 order by id"))
        return {
            "date": today, "orders_by_status": by_status, "jobs_today": jobs_today, "jobs_next_7_days": upcoming,
            "late_orders": late, "due_in_2_days": due_soon, "low_stock": low_stock,
            "pending": {
                "unclaimed_orders": _num(s.execute(text(
                    "select count(*) from orders where order_status::text = 'SUBMITTED' and assigned_staff_id is null")).scalar()),
                "price_adjustments": _num(s.execute(text(
                    "select count(*) from quotations where adjustment_status::text = 'PENDING_MANAGER'")).scalar()),
                "orders_to_schedule": _num(s.execute(text(
                    "select count(*) from orders where order_status::text = 'CONFIRMED' and not exists (select 1 from "
                    "production_jobs j where j.order_id = orders.id and j.status::text not in ('CANCELLED', 'FAILED', 'DONE'))"
                )).scalar()),
                "open_incidents": _num(s.execute(text("select count(*) from incidents where resolved_at is null")).scalar()),
                "refunds_to_confirm": _num(s.execute(text(
                    "select count(*) from payments where type::text = 'REFUND' and status::text = 'PENDING'")).scalar()),
            },
        }

    # ------------------------------------------------------------------ UC-46
    @staticmethod
    def period(start: date | None, end: date | None, group: str) -> tuple[date, date, str]:
        end = end or _today()
        start = start or (end - timedelta(days=29))
        if group not in GROUPS:
            raise AppError(422, "INVALID_GROUP", "group phải là day, week hoặc month.")
        if start > end:
            raise AppError(422, "INVALID_PERIOD", "Ngày bắt đầu phải trước ngày kết thúc.")
        if (end - start).days + 1 > MAX_DAYS:
            raise AppError(422, "PERIOD_TOO_LONG", f"Tối đa {MAX_DAYS} ngày mỗi báo cáo.")
        return start, end, group

    def report(self, start: date | None = None, end: date | None = None, group: str = "day") -> dict[str, Any]:
        start, end, group = self.period(start, end, group)
        s = self.session
        p = {"a": start, "b": end, "g": group}
        local = f"at time zone '{TZ}'"
        revenue = _rows(s, f"""
            select (date_trunc(:g, paid_at {local}))::date as bucket,
                   sum(case when type::text <> 'REFUND' then amount else 0 end) as received,
                   sum(case when type::text = 'REFUND' then amount else 0 end) as refunded,
                   count(*) filter (where type::text <> 'REFUND') as payments
            from payments where status::text = 'SUCCESS' and paid_at is not null
              and (paid_at {local})::date between :a and :b
            group by 1 order by 1""", **p)
        for r in revenue:
            r["received"], r["refunded"] = _num(r["received"]), _num(r["refunded"])
            r["net"] = r["received"] - r["refunded"]
        by_type = _rows(s, f"""
            select order_type::text as order_type, count(*) as orders, coalesce(sum(quantity), 0) as quantity,
                   coalesce(sum(total_amount), 0) as total_amount
            from orders where order_status::text = 'COMPLETED' and completed_at is not null
              and (completed_at {local})::date between :a and :b group by 1 order by 1""", **p)
        for r in by_type:
            r["total_amount"] = _num(r["total_amount"])
        submitted = _num(s.execute(text(f"select count(*) from orders where submitted_at is not null and "
                                        f"(submitted_at {local})::date between :a and :b"), p).scalar())
        rejected = _num(s.execute(text(f"""select count(distinct order_id) from status_histories where state_type = 'ORDER'
            and to_status = 'REJECTED' and (created_at {local})::date between :a and :b"""), p).scalar())
        jobs = s.execute(text(f"""select count(*) filter (where not is_rewrite) as first, count(*) filter (where is_rewrite) as rewrites
            from production_jobs where finished_at is not null and status::text in ('WRITTEN', 'PHOTO_UPLOADED', 'DONE',
            'REWRITE_REQUIRED') and (finished_at {local})::date between :a and :b"""), p).first()
        first, rewrites = _num(jobs.first), _num(jobs.rewrites)
        robots = _rows(s, f"""
            select r.id as robot_id, r.code as robot_code,
              (select count(*) from production_jobs j where j.robot_id = r.id and j.finished_at is not null
                 and (j.finished_at {local})::date between :a and :b) as jobs_written,
              (select coalesce(round(sum(extract(epoch from (j.finished_at - j.started_at))) / 60.0), 0)
                 from production_jobs j where j.robot_id = r.id and j.started_at is not null and j.finished_at is not null
                 and (j.finished_at {local})::date between :a and :b) as writing_minutes,
              (select count(*) from incidents i where i.robot_id = r.id and (i.created_at {local})::date between :a and :b)
                 as incidents
            from robots r order by r.code""", **p)
        for r in robots:
            r["writing_minutes"] = _num(r["writing_minutes"])
        late = _rows(s, f"""
            select id as order_id, code, eta, (completed_at {local})::date as completed_on,
                   ((completed_at {local})::date - eta) as days_late, eta_postponed_days
            from orders where order_status::text = 'COMPLETED' and eta is not null and completed_at is not null
              and (completed_at {local})::date between :a and :b and (completed_at {local})::date > eta
            order by days_late desc, id limit 500""", **p)
        completed = sum(_num(r["orders"]) for r in by_type)
        return {
            "from": start, "to": end, "group": group,
            "revenue": {"series": revenue, "received": sum(r["received"] for r in revenue),
                        "refunded": sum(r["refunded"] for r in revenue), "net": sum(r["net"] for r in revenue)},
            "output_by_type": by_type,
            "rates": {"submitted": submitted, "rejected": rejected,
                      "reject_rate": round(rejected / submitted, 4) if submitted else None,
                      "jobs_written": first, "rewrites": rewrites,
                      "rewrite_rate": round(rewrites / first, 4) if first else None},
            "robots": robots,
            "late_completed": {"count": len(late), "of_completed": completed,
                               "late_rate": round(len(late) / completed, 4) if completed else None, "orders": late},
        }

    # ------------------------------------------------------------------ FR-50 export
    def export_xlsx(self, start: date | None = None, end: date | None = None, group: str = "day") -> tuple[bytes, str]:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        rep = self.report(start, end, group)
        wb = Workbook()
        bold = Font(bold=True)

        def sheet(title: str, header: list[str], rows: list[list[Any]], first: bool = False):
            ws = wb.active if first else wb.create_sheet()
            ws.title = title
            ws.append(header)
            for c in ws[1]:
                c.font = bold
            for r in rows:
                ws.append(r)
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = max(12, min(40, max(len(str(c.value or "")) for c in col) + 2))

        r = rep["rates"]
        sheet("Tổng quan", ["Chỉ số", "Giá trị"], [
            ["Từ ngày", rep["from"]], ["Đến ngày", rep["to"]], ["Gom theo", rep["group"]],
            ["Tiền nhận (đ)", rep["revenue"]["received"]], ["Tiền hoàn (đ)", rep["revenue"]["refunded"]],
            ["Doanh thu thuần (đ)", rep["revenue"]["net"]], ["Đơn gửi", r["submitted"]], ["Đơn bị từ chối", r["rejected"]],
            ["Tỷ lệ từ chối", r["reject_rate"]], ["Job viết (lần đầu)", r["jobs_written"]], ["Job viết lại", r["rewrites"]],
            ["Tỷ lệ viết lại", r["rewrite_rate"]], ["Đơn hoàn tất trễ ETA", rep["late_completed"]["count"]],
            ["Tỷ lệ trễ", rep["late_completed"]["late_rate"]]], first=True)
        sheet("Doanh thu", ["Kỳ", "Tiền nhận (đ)", "Tiền hoàn (đ)", "Thuần (đ)", "Số giao dịch"],
              [[x["bucket"], x["received"], x["refunded"], x["net"], x["payments"]] for x in rep["revenue"]["series"]])
        sheet("Sản lượng", ["Loại đơn", "Số đơn", "Số bản", "Giá trị (đ)"],
              [[x["order_type"], x["orders"], x["quantity"], x["total_amount"]] for x in rep["output_by_type"]])
        sheet("Robot", ["Robot", "Job đã viết", "Phút viết", "Sự cố"],
              [[x["robot_code"], x["jobs_written"], x["writing_minutes"], x["incidents"]] for x in rep["robots"]])
        sheet("Trễ ETA", ["Mã đơn", "ETA", "Hoàn tất", "Trễ (ngày)", "Đã dời (ngày)"],
              [[x["code"], x["eta"], x["completed_on"], x["days_late"], x["eta_postponed_days"]]
               for x in rep["late_completed"]["orders"]])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), f"bao-cao_{rep['from']}_{rep['to']}.xlsx"
