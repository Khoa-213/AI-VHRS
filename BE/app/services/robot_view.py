"""Read-only 3D view of a robot: a short-lived ticket instead of a login in the page.

The technician's app (or the web FE) asks for a ticket with its normal bearer token, then opens the BE-hosted viewer page
(`/viewer/robot.html?ticket=...`) in a WebView / iframe. The ticket only lets that page READ the live frames and the scene of ONE robot:
it cannot send a command. Commands (pause, resume, stop...) go through `/technician/robot-commands` with the app's own token.
The robot model (vendor URDF + STL, public SDK files) lives in object storage and is served by `/api/v1/robot-model/...`.
"""
from __future__ import annotations

import re
from datetime import timedelta

from app.core import security
from app.core.errors import AppError
from app.integrations.storage import ObjectStorage

TICKET_TYPE = "rview"
TICKET_TTL = timedelta(minutes=60)
MODEL_PREFIX = "robot-models/fr3/"
MODEL_FILES = ("fairino3_v6.urdf",)
MESH_RE = re.compile(r"^[A-Za-z0-9_.-]+\.(?i:stl)$")
_cache: dict[str, bytes] = {}


def issue_ticket(account_id: int, robot_id: int) -> tuple[str, int]:
    token = security.create_token(account_id, TICKET_TYPE, TICKET_TTL, robot=robot_id)
    return token, int(TICKET_TTL.total_seconds())


def robot_of_ticket(ticket: str) -> int:
    try:
        payload = security.decode_token(ticket, TICKET_TYPE)
    except AppError as exc:
        raise AppError(401, "INVALID_VIEW_TICKET", "Liên kết xem robot không hợp lệ hoặc đã hết hạn: hãy mở lại từ ứng dụng.") from exc
    return int(payload["robot"])


def model_bytes(storage: ObjectStorage | None, name: str, *, mesh: bool) -> bytes:
    if mesh and not MESH_RE.fullmatch(name) or not mesh and name not in MODEL_FILES:
        raise AppError(404, "MODEL_FILE_NOT_FOUND", "Không có file mô hình này.")
    path = MODEL_PREFIX + (f"meshes/{name}" if mesh else name)
    if path in _cache:
        return _cache[path]
    if storage is None:
        raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
    data = storage.read(path)
    if data is None:
        raise AppError(404, "MODEL_NOT_UPLOADED", "Mô hình robot chưa được tải lên kho lưu trữ (chạy scripts/upload_robot_model.py).")
    _cache[path] = data
    return data
