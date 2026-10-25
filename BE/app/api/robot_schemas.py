"""Request / response models for robot operations: runs, alerts, heartbeat, robot status, health, compliance."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Mode = Literal["MOCK", "SIM", "REAL"]
RunResult = Literal["DONE", "STOPPED", "FAULT", "UNKNOWN", "DRY_RUN_DONE", "REFUSED"]
Short = Annotated[str, StringConstraints(max_length=80)]


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _bounded(v: Any, limit: int = 20_000) -> None:
    import json
    if v is not None and len(json.dumps(v, default=str)) > limit:
        raise ValueError("dữ liệu quá lớn")


class RunOpenIn(BaseModel):
    """The agent opens a run before it moves anything (also for dry runs; a refused attempt is recorded closed)."""
    run_id: Annotated[str, StringConstraints(min_length=6, max_length=40, pattern=r"^[A-Za-z0-9_.:-]+$")]
    mode: Mode
    dry_run: bool = False
    authorized: bool = Field(default=False, description="The operator typed the authorization for this job and plan (REAL only).")
    plan_digest: Annotated[str, StringConstraints(max_length=64)] | None = None
    total_strokes: int = Field(default=0, ge=0, le=1_000_000)
    agent_version: Short | None = None
    robot_info: dict[str, Any] | None = None
    refused_reason: Annotated[str, StringConstraints(max_length=500)] | None = Field(
        default=None, description="Set when the preflight refused to start: the run is stored already closed as REFUSED.")

    @model_validator(mode="after")
    def _size(self) -> "RunOpenIn":
        _bounded(self.robot_info)
        return self


class RunCloseIn(BaseModel):
    result: RunResult
    completed_strokes: int = Field(default=0, ge=0, le=1_000_000)
    total_strokes: int | None = Field(default=None, ge=0, le=1_000_000)
    summary: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _size(self) -> "RunCloseIn":
        _bounded(self.summary)
        return self


class RunOut(_ORM):
    id: int
    run_id: str
    job_id: int
    robot_id: int
    mode: str
    dry_run: bool
    started_at: datetime
    ended_at: datetime | None
    result: str | None
    completed_strokes: int
    total_strokes: int
    plan_digest: str | None
    authorized_by: int | None
    authorized_at: datetime | None
    agent_version: str | None
    robot_info: dict[str, Any] | None
    summary: dict[str, Any] | None


class AlertRaiseIn(BaseModel):
    """The agent only names the alert. Level, sentence and action come from the catalogue, never from the agent."""
    robot_id: int
    code: Annotated[str, StringConstraints(min_length=3, max_length=40)]
    job_id: int | None = None
    run_id: Annotated[str, StringConstraints(max_length=40)] | None = Field(default=None, description="the agent's run_id string")
    details: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _size(self) -> "AlertRaiseIn":
        _bounded(self.details)
        return self


class AlertOut(_ORM):
    id: int
    robot_id: int
    robot_code: str = ""
    job_id: int | None
    run_id: int | None
    code: str
    level: int
    title_vi: str
    action_vi: str
    estop_advised: bool
    details: dict[str, Any] | None
    occurrences: int
    raised_at: datetime
    last_raised_at: datetime
    emailed_at: datetime | None
    acknowledged_by: int | None
    acknowledged_at: datetime | None
    resolved_by: int | None
    resolved_at: datetime | None
    resolution_note: str | None


class AlertResolveIn(BaseModel):
    note: Annotated[str, StringConstraints(min_length=3, max_length=500)]


class HeartbeatIn(BaseModel):
    mode: Mode
    controller_version: Short | None = None
    firmware_version: Short | None = None
    sdk_version: Short | None = None
    agent_version: Short | None = None


class CatalogOut(_ORM):
    code: str
    level: int
    title_vi: str
    action_vi: str
    estop_advised: bool
    notify_roles: list[str]
    send_email: bool
    threshold: dict[str, Any] | None
    is_active: bool
    updated_at: datetime


class CatalogPatch(BaseModel):
    """The Manager changes wording, who is told, e-mail on/off, thresholds and on/off. The level never changes."""
    title_vi: Annotated[str, StringConstraints(min_length=3, max_length=300)] | None = None
    action_vi: Annotated[str, StringConstraints(min_length=3, max_length=600)] | None = None
    notify_roles: list[Literal["TECHNICAL_STAFF", "MANAGER", "STAFF"]] | None = None
    send_email: bool | None = None
    threshold: dict[str, Any] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _size(self) -> "CatalogPatch":
        _bounded(self.threshold, 2000)
        return self


class RobotStatusOut(BaseModel):
    robot_id: int
    robot_code: str
    state: Literal["OFFLINE", "IDLE", "PREPARING", "WRITING", "PAUSED_SAFE", "DANGER"]
    headline_vi: str
    level: int = Field(description="Highest open alert level (1 when none).")
    mode: str | None
    connection_state: str
    last_seen_at: datetime | None
    seconds_since_seen: float | None
    controller_version: str | None
    firmware_version: str | None
    sdk_version: str | None
    agent_version: str | None
    job_id: int | None
    job_status: str | None
    open_run: RunOut | None
    open_alerts: list[AlertOut]
    calibration_age_minutes: float | None


class HealthOut(BaseModel):
    robot: RobotStatusOut
    since: datetime
    runs_by_result: dict[str, int]
    runs_by_mode: dict[str, int]
    run_seconds: float
    safety_stops: int
    alerts_by_level: dict[str, int]
    in_band_pct_avg: float | None
    open_incidents: int
    unresolved_red: int


class ComplianceStep(BaseModel):
    key: str
    label_vi: str
    status: Literal["PASS", "FAIL", "PENDING", "NOT_APPLICABLE"]
    at: datetime | None = None
    detail: str | None = None


class ComplianceOut(BaseModel):
    job_id: int
    order_code: str
    robot_code: str
    job_status: str
    steps: list[ComplianceStep]
    exceptions: list[str]
    followed_process: bool
