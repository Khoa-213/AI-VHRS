"""Pure rules for a production job on the workshop floor (FR-43..49, BR-17, BR-19, BR-20). No DB, no I/O.

The Technical Staff drives a job through SCHEDULED -> PREPARING -> WRITING (-> PAUSED -> WRITING) -> WRITTEN, or to
FAILED when an incident stops it. The order's production status mirrors the job's (BR-17); the database trigger
`fn_order_state_guard` is the final judge of the order side, these rules decide what the API even attempts.

Nothing here talks to a robot. The workstation (Flutter app + Robot Agent) reports what happened; the server records it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.models.ops import JobEventType, JobStatus


class JobRuleError(ValueError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


# ---------------------------------------------------------------------------------------------- job state machine
# Moves the Technical Staff can make. SCHEDULED comes from the Manager; DONE / PHOTO_UPLOADED belong to the photo step.
TECH_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.SCHEDULED: frozenset({JobStatus.PREPARING}),
    JobStatus.PREPARING: frozenset({JobStatus.WRITING, JobStatus.FAILED}),
    JobStatus.WRITING: frozenset({JobStatus.PAUSED, JobStatus.WRITTEN, JobStatus.FAILED}),
    JobStatus.PAUSED: frozenset({JobStatus.WRITING, JobStatus.FAILED}),
}
# A job in one of these is still on the technician's desk (can be downloaded / inspected / reported on).
OPEN_STATUSES = (JobStatus.SCHEDULED, JobStatus.PREPARING, JobStatus.WRITING, JobStatus.PAUSED)
# Incidents can only stop a job that has been started (an unstarted job is simply re-planned by the Manager).
INCIDENT_FROM = (JobStatus.PREPARING, JobStatus.WRITING, JobStatus.PAUSED)


def can_move(src: JobStatus, dst: JobStatus) -> bool:
    return dst in TECH_TRANSITIONS.get(src, frozenset())


# ---------------------------------------------------------------------------------------------- events from the workstation
@dataclass(frozen=True)
class EventRule:
    allowed_from: tuple[JobStatus, ...]
    to: JobStatus | None = None          # job (and order production) status after the event, None = no change


# Events the Robot Agent / app may post (FR-47, FR-48). Everything else in `job_event_type` is written by the
# server itself (DOWNLOADED, HASH_MISMATCH, CALIBRATED, SIMULATED, START, WRITTEN, INCIDENT).
CLIENT_EVENTS: dict[JobEventType, EventRule] = {
    JobEventType.PROGRESS: EventRule((JobStatus.WRITING,)),
    JobEventType.PAUSE: EventRule((JobStatus.WRITING,), JobStatus.PAUSED),
    JobEventType.RESUME: EventRule((JobStatus.PAUSED,), JobStatus.WRITING),
    # Safety stops: the arm has already lifted the pen. FR-48 "tự PAUSED khi bất thường": a second stop while already
    # paused is still worth logging, it just changes nothing.
    JobEventType.ESTOP: EventRule((JobStatus.WRITING, JobStatus.PAUSED), JobStatus.PAUSED),
    JobEventType.OVER_FORCE: EventRule((JobStatus.WRITING, JobStatus.PAUSED), JobStatus.PAUSED),
    JobEventType.STROKE_LOST: EventRule((JobStatus.WRITING, JobStatus.PAUSED), JobStatus.PAUSED),
    JobEventType.SENSOR_LOST: EventRule((JobStatus.WRITING, JobStatus.PAUSED), JobStatus.PAUSED),
    JobEventType.FORCE_SUMMARY: EventRule((JobStatus.WRITING, JobStatus.PAUSED, JobStatus.WRITTEN)),
}


def event_effect(event: JobEventType, current: JobStatus) -> JobStatus | None:
    """Status the job moves to after `event`, or None when it stays. Raises when the event is not allowed now."""
    rule = CLIENT_EVENTS.get(event)
    if rule is None:
        raise JobRuleError("EVENT_NOT_ALLOWED", f"Sự kiện {event.value} do hệ thống ghi, không gửi từ máy trạm.")
    if current not in rule.allowed_from:
        raise JobRuleError("JOB_STATE_CONFLICT", f"Không ghi được {event.value} khi job đang {current.value}.",
                           {"job_status": current.value, "allowed": [s.value for s in rule.allowed_from]})
    if rule.to is None or rule.to == current:
        return None
    return rule.to


# ---------------------------------------------------------------------------------------------- calibration (FR-44, BR-19)
# ASSUMPTION (checklist items are not listed in the SRS beyond "khung / giấy / bút" + "zero lực"): keep them here so
# the workshop can change them in one place.
REQUIRED_CHECKLIST = ("frame_mounted", "paper_clamped", "pen_installed", "force_zeroed")
MIN_PROBE_POINTS = 3                     # P0, P1, P2 define the paper plane (SRS S7)
MAX_PROBE_POINTS = 400                   # P0..P2 plus an optional grid


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_checklist(checklist: dict[str, Any]) -> None:
    missing = [k for k in REQUIRED_CHECKLIST if checklist.get(k) is not True]
    if missing:
        raise JobRuleError("CHECKLIST_INCOMPLETE", "Checklist chuẩn bị chưa hoàn tất (BR-19).", {"missing": missing})


def check_probe_points(points: list[Any]) -> None:
    if not MIN_PROBE_POINTS <= len(points) <= MAX_PROBE_POINTS:
        raise JobRuleError("INVALID_PROBE_POINTS", f"Cần {MIN_PROBE_POINTS}..{MAX_PROBE_POINTS} điểm dò mặt giấy (P0, P1, P2 + lưới).")
    for i, p in enumerate(points):
        if not (isinstance(p, dict) and all(_num(p.get(k)) for k in ("x", "y", "z"))):
            raise JobRuleError("INVALID_PROBE_POINTS", f"Điểm dò {i}: cần x, y, z là số hữu hạn.")
    p0, p1, p2 = ((p["x"], p["y"], p["z"]) for p in points[:3])
    v1, v2 = [b - a for a, b in zip(p0, p1)], [b - a for a, b in zip(p0, p2)]
    cross = (v1[1] * v2[2] - v1[2] * v2[1], v1[2] * v2[0] - v1[0] * v2[2], v1[0] * v2[1] - v1[1] * v2[0])
    if math.sqrt(sum(c * c for c in cross)) < 1e-6:
        raise JobRuleError("INVALID_PROBE_POINTS", "P0, P1, P2 thẳng hàng hoặc trùng nhau: không xác định được mặt giấy.")


# ---------------------------------------------------------------------------------------------- simulation (FR-45)
def check_simulation(passed: bool, errors: list[str]) -> None:
    """The run is blocked while a feasibility error remains, so a 'passed' report with errors is contradictory."""
    if passed and errors:
        raise JobRuleError("SIMULATION_INCONSISTENT", "Báo cáo mô phỏng còn lỗi khả thi nhưng đánh dấu đạt.", {"errors": errors})


# ---------------------------------------------------------------------------------------------- telemetry
FORCE_SUMMARY_KEYS = ("f_mean", "f_max", "rms_err_pct", "in_band_pct", "samples")   # NFR-05


def check_force_summary(summary: dict[str, Any]) -> None:
    bad = [k for k in FORCE_SUMMARY_KEYS if k in summary and not _num(summary[k])]
    unknown = [k for k in summary if k not in FORCE_SUMMARY_KEYS]
    if bad or unknown or not summary:
        raise JobRuleError("INVALID_FORCE_SUMMARY", "force_summary chỉ gồm số cho: " + ", ".join(FORCE_SUMMARY_KEYS),
                           {"not_numeric": bad, "unknown": unknown})
    if "in_band_pct" in summary and not 0 <= summary["in_band_pct"] <= 100:
        raise JobRuleError("INVALID_FORCE_SUMMARY", "in_band_pct phải trong 0..100.")


# ---------------------------------------------------------------------------------------------- stock (FR-41)
@dataclass(frozen=True)
class StockUse:
    paper: int
    pen: int
    ink: int


def stock_use(quantity: int, pages: int) -> StockUse:
    """Materials used up when a job reaches WRITTEN.

    ASSUMPTION (the SRS only says 'trừ tồn kho khi job WRITTEN'): paper = copies x sheets per copy (the same unit the
    scheduling stock warning uses), and one pen and one ink unit per job.
    """
    return StockUse(paper=max(quantity, 1) * max(pages, 1), pen=1, ink=1)


def deduct(stock: int, used: int) -> tuple[int, int]:
    """(new stock, shortfall). The column cannot go below 0; what is missing is reported, never hidden, and the
    physical writing that already happened is not blocked by an inventory count that was out of date."""
    return max(stock - used, 0), max(used - stock, 0)
