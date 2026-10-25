"""Schemas of the Robot Agent link (commands, live view, agent sync)."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["LOAD", "PREFLIGHT", "DRY_RUN", "RUN", "PAUSE", "RESUME", "STOP", "PAPER_CHANGED", "IDENTIFY", "ALIGN_START"]


class CommandIn(BaseModel):
    kind: Kind
    job_id: int | None = Field(default=None, description="Bắt buộc với LOAD, PREFLIGHT, DRY_RUN, RUN, PAPER_CHANGED.")
    robot_id: int | None = Field(default=None, description="Chỉ cần khi không có job_id (IDENTIFY, PAUSE/RESUME/STOP theo robot).")
    params: dict[str, Any] = Field(default_factory=dict, description=(
        "PREFLIGHT/DRY_RUN/RUN/IDENTIFY: `mode` MOCK|SIM|REAL. DRY_RUN/RUN/ALIGN_START: `authorization`; DRY_RUN/RUN: `speed`. RUN: `resume_from`, `confirm_unknown`."))
    idempotency_key: str | None = Field(default=None, max_length=80, description="Gửi lại cùng khoá thì không tạo thêm lệnh.")


class CommandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    robot_id: int
    job_id: int | None
    kind: str
    params: dict[str, Any]
    status: Literal["PENDING", "DELIVERED", "DONE", "FAILED", "EXPIRED", "CANCELLED"]
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    expires_at: datetime
    delivered_at: datetime | None
    finished_at: datetime | None


class LiveOut(BaseModel):
    robot_id: int
    robot_code: str
    agent_online: bool
    age_s: float | None
    mode: str | None
    status: dict[str, Any]
    last_seq: int
    frames: list[dict[str, Any]]


class SceneOut(BaseModel):
    command_id: str
    job_id: int | None
    scene: dict[str, Any]


class AgentKeyOut(BaseModel):
    robot_id: int
    key: str = Field(description="CHỈ HIỆN MỘT LẦN. Đặt vào agent.json (`agent_key`) trên máy trạm, không commit.")
    key_prefix: str


class AgentInfoOut(BaseModel):
    robot_id: int
    has_key: bool
    key_prefix: str | None
    issued_at: datetime | None
    online: bool
    last_seen_at: datetime | None
    session_keys: list[dict[str, Any]] = []
    controlled_by_account_id: int | None = None


class SessionKeyIn(BaseModel):
    instance_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$",
                             description="Mã ngẫu nhiên (UUID) sinh MỘT lần mỗi lần mở app; gia hạn phải gửi lại đúng mã này.")


class SessionKeyOut(BaseModel):
    robot_id: int
    key: str = Field(description="Chỉ giữ trong bộ nhớ của app/agent, không ghi ra file.")
    key_prefix: str
    expires_at: datetime
    renew_after_s: int = Field(description="Sau chừng này giây phải xin khoá mới (cùng instance_id); khoá cũ còn sống thêm ~2 phút.")


class AgentSyncIn(BaseModel):
    status: dict[str, Any] = Field(default_factory=dict, description="mode, busy, current job, state, level...")
    frames: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    controller_version: str | None = Field(default=None, max_length=60)
    firmware_version: str | None = Field(default=None, max_length=80)
    sdk_version: str | None = Field(default=None, max_length=60)
    agent_version: str | None = Field(default=None, max_length=30)


class AgentCommand(BaseModel):
    id: str
    kind: str
    job_id: int | None
    params: dict[str, Any]
    expires_at: datetime


class AgentSyncOut(BaseModel):
    commands: list[AgentCommand]
    server_time: datetime
    robot_id: int


class AgentResultIn(BaseModel):
    ok: bool
    result: dict[str, Any] | None = None
    error_code: str | None = Field(default=None, max_length=40)
    message: str | None = Field(default=None, max_length=1000)
