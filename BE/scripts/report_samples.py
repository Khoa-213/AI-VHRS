"""Build sample Manager report files (Excel + PDF) from synthetic report dicts, without a database.

    python scripts/report_samples.py [out_dir]          # default: docs/report_samples

Datasets: small (one week, few rows), large (a year by day: 366 periods, 500 late orders, billion-đồng totals, a period with
net below zero), empty (nothing in the period), long (long codes and an unknown order type), month (grouped by month).
The figures are made up for layout checks only; real exports read the database through ReportService.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import report_pdf, report_xlsx  # noqa: E402


def make(start: date, days: int, group: str, n_late: int, scale: int, robots: list[str], types: list[str],
         empty: bool = False) -> dict:
    end = start + timedelta(days=days - 1)
    series = []
    if not empty:
        step = {"day": 1, "week": 7, "month": 30}[group]
        cur = start
        i = 0
        while cur <= end:
            b = cur.replace(day=1) if group == "month" else cur - timedelta(days=cur.weekday()) if group == "week" else cur
            rec = scale * (3 + (i * 7) % 11) * 50_000
            ref = (scale * 2_400_000 if i % 9 == 4 else 0) + (rec + 900_000 if i == 5 else 0)
            series.append({"bucket": b, "received": rec, "refunded": ref, "net": rec - ref, "payments": 2 + i % 5})
            cur = (cur.replace(day=1) + timedelta(days=32)).replace(day=1) if group == "month" else cur + timedelta(days=step)
            i += 1
    rec, ref = sum(x["received"] for x in series), sum(x["refunded"] for x in series)
    out = [] if empty else [{"order_type": t, "orders": n_late // max(len(types), 1) + 4 + k * 3, "quantity": 20 + k * 37,
                              "total_amount": scale * (k + 1) * 1_850_000} for k, t in enumerate(types)]
    late = [] if empty else [{"order_id": k, "code": f"ORD-2026-{k + 1:05d}", "eta": start + timedelta(days=k % days),
                              "completed_on": start + timedelta(days=k % days + 1 + k % 6), "days_late": 1 + k % 6 + (n_late - k) // 60,
                              "eta_postponed_days": (k % 4) or None} for k in range(n_late)]
    late.sort(key=lambda x: -x["days_late"])
    completed = sum(x["orders"] for x in out)
    return {"from": start, "to": end, "group": group,
            "revenue": {"series": series, "received": rec, "refunded": ref, "net": rec - ref},
            "output_by_type": out,
            "rates": {"submitted": 0 if empty else 48 * scale, "rejected": 0 if empty else 5 * scale,
                      "reject_rate": None if empty else round(5 / 48, 4), "jobs_written": 0 if empty else 40 * scale,
                      "rewrites": 0 if empty else 3 * scale, "rewrite_rate": None if empty else 0.075},
            "robots": [{"robot_id": k, "robot_code": c, "jobs_written": 0 if empty else 12 * (k + 1),
                        "writing_minutes": 0 if empty else 340 * (k + 1), "incidents": 0 if empty else k % 2}
                       for k, c in enumerate(robots)],
            "late_completed": {"count": len(late), "of_completed": completed,
                               "late_rate": round(len(late) / completed, 4) if completed else None, "orders": late}}


TYPES = ["OT1_COPY_RESTORE", "OT3_TEMPLATE"]
SETS = {
    "small": make(date(2026, 11, 2), 7, "day", 3, 1, ["FR3-01"], TYPES),
    "large": make(date(2025, 11, 15), 366, "day", 500, 400, ["FR3-01", "FR3-02", "FR3-03"], TYPES + ["OT2_LEARNED_STYLE"]),
    "month": make(date(2025, 12, 1), 350, "month", 40, 60, ["FR3-01", "FR3-02"], TYPES),
    "empty": make(date(2026, 10, 1), 31, "week", 0, 1, [], [], empty=True),
    "long": make(date(2026, 10, 1), 28, "week", 12, 2500,
                 ["FR3-XUONG-NET-VIET-CHI-NHANH-THU-DUC-ROBOT-SO-01-DU-PHONG"], TYPES + ["OT9_LOAI_DON_MOI_CHUA_CO_NHAN_HIEN_THI"]),
}

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "docs" / "report_samples")
    out.mkdir(parents=True, exist_ok=True)
    when = datetime(2026, 11, 15, 9, 30)
    for name, rep in SETS.items():
        (out / f"bao-cao_{name}.xlsx").write_bytes(report_xlsx.render(rep, when, "Nguyễn Thị Quản Lý Xưởng"))
        (out / f"bao-cao_{name}.pdf").write_bytes(report_pdf.render(rep, when, "Nguyễn Thị Quản Lý Xưởng"))
        print(name, "ok")
