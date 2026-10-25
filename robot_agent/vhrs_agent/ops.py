"""Reporting to the backend's robot operations API: runs, alerts, heartbeat. Best effort, never raises into the motion loop.

The agent only NAMES an alert (a code). The backend's catalogue decides the level, the sentence and the action. Because a red
alert must reach the operator even when the network is down, the agent also carries a small built-in copy of the safety
sentences (FALLBACK) and shows that locally; the backend's text replaces it when the call succeeds.
"""
from __future__ import annotations

import threading
import time
from typing import Any

# Offline copy of the sentences that matter when the network is gone. Same codes and levels as migration 0008.
FALLBACK: dict[str, dict[str, Any]] = {
    "STOP_NOT_EFFECTIVE": {"level": 4, "title_vi": "Đã gửi lệnh dừng nhưng đầu bút vẫn đang di chuyển.",
                           "action_vi": "BẤM NÚT E-STOP NGAY. Phần mềm không thể tự dừng robot trong trường hợp này."},
    "LINK_LOST_MOVING": {"level": 4, "title_vi": "Mất kết nối với robot khi robot đang chạy.",
                         "action_vi": "Nếu robot còn chuyển động, BẤM NÚT E-STOP NGAY. Sau đó kiểm tra dây mạng và nguồn."},
    "TRACKING_ERROR": {"level": 4, "title_vi": "Đầu bút lệch xa đường đã định.",
                       "action_vi": "BẤM NÚT E-STOP NGAY. Không chạy lại cho tới khi xác định nguyên nhân."},
    "CONTROLLER_SAFETY_FAULT": {"level": 4, "title_vi": "Robot báo lỗi an toàn hoặc va chạm trong lúc di chuyển.",
                                "action_vi": "BẤM NÚT E-STOP NGAY nếu robot chưa đứng yên, rồi gọi Manager."},
    "OVER_FORCE_STILL": {"level": 4, "title_vi": "Lực ép vẫn vượt giới hạn dù đã gửi lệnh dừng.",
                         "action_vi": "BẤM NÚT E-STOP NGAY. Bút hoặc giấy có thể đang bị kẹt."},
    "OVER_FORCE": {"level": 3, "title_vi": "Bút ép quá mạnh, robot đã tự dừng và nhấc bút.",
                   "action_vi": "Kiểm tra bút và tờ giấy, rồi chọn tiếp tục hoặc bỏ qua nét dở; không tự chạy lại từ đầu."},
    "SENSOR_LOST": {"level": 3, "title_vi": "Mất tín hiệu cảm biến lực, robot đã dừng.",
                    "action_vi": "Kiểm tra dây USB của gripper rồi chạy lại bước kiểm tra trước khi viết."},
    "STROKE_LOST": {"level": 3, "title_vi": "Bút rời khỏi giấy khi đang viết, robot đã tạm dừng.",
                    "action_vi": "Kiểm tra giấy và bút rồi tiếp tục hoặc bỏ qua nét dở."},
    "RUN_OUTCOME_UNKNOWN": {"level": 3, "title_vi": "Mất kết nối giữa chừng: chưa biết bản viết đã đến đâu.",
                            "action_vi": "Nhìn tờ giấy, xác định nét nào đã viết xong, rồi chọn nét bắt đầu lại."},
    "STROKE_INTERRUPTED": {"level": 3, "title_vi": "Một nét đang viết dở khi dừng.",
                           "action_vi": "Xem nét dở trên giấy rồi chọn viết lại nét đó hoặc bỏ qua."},
    "PREFLIGHT_REFUSED": {"level": 2, "title_vi": "Chưa chạy được vì bước kiểm tra trước khi chạy không đạt.",
                          "action_vi": "Đọc lý do hiển thị và xử lý. Robot không di chuyển."},
    "DROPPED_FRAMES": {"level": 2, "title_vi": "Cảm biến lực mất nhiều gói tin.", "action_vi": "Kiểm tra dây USB của gripper."},
    "BACKEND_LINK_LOST": {"level": 3, "title_vi": "Máy trạm mất kết nối tới hệ thống trong lúc đang viết: robot đã viết xong nét hiện tại, nhấc bút và tạm dừng.",
                          "action_vi": "Kiểm tra mạng của máy trạm. Khi kết nối lại, chọn tiếp tục hoặc dừng job. Nếu thấy robot chuyển động bất thường, dùng nút dừng khẩn vật lý."},
    "PAPER_CHANGE": {"level": 1, "title_vi": "Cần đặt tờ giấy mới cho trang kế tiếp.",
                     "action_vi": "Đặt giấy mới, kẹp chặt rồi xác nhận để tiếp tục."},
}


class OpsReporter:
    def __init__(self, bridge: Any, *, robot_id: int | None, log: Any = None, heartbeat_every_s: float = 2.0):
        self.bridge, self.robot_id, self.log, self.every = bridge, robot_id, log, heartbeat_every_s
        self._hb_stop = threading.Event()
        self._hb: threading.Thread | None = None
        self.last_error: str | None = None

    def _note(self, kind: str, **data: Any) -> None:
        if self.log is not None:
            self.log.write(kind, **data)

    # ---- runs
    def open_run(self, job_id: int, *, run_id: str, mode: str, dry_run: bool, authorized: bool, digest: str | None, total: int,
                 robot_info: dict[str, Any] | None, agent_version: str, refused_reason: str | None = None) -> bool:
        """True when the backend recorded the run. A REAL run must not start without this record."""
        if self.bridge is None:
            return True
        try:
            self.bridge.open_run(job_id, run_id=run_id, mode=mode, dry_run=dry_run, authorized=authorized, plan_digest=digest,
                                 total_strokes=total, agent_version=agent_version, robot_info=robot_info,
                                 refused_reason=refused_reason)
            return True
        except Exception as exc:                            # noqa: BLE001
            self.last_error = str(exc)
            self._note("bridge_error", op="open_run", error=str(exc))
            return False

    def close_run(self, run_id: str, *, result: str, completed: int, total: int, summary: dict[str, Any] | None) -> None:
        if self.bridge is None:
            return
        try:
            self.bridge.close_run(run_id, result=result, completed_strokes=completed, total_strokes=total, summary=summary)
        except Exception as exc:                            # noqa: BLE001
            self._note("bridge_error", op="close_run", error=str(exc))

    # ---- alerts
    def alert(self, code: str, *, job_id: int | None, run_id: str | None, details: dict[str, Any] | None = None) -> dict[str, Any]:
        """Always returns something to show locally; tells the backend when it can."""
        local = {"code": code, **FALLBACK.get(code, {"level": 3, "title_vi": code, "action_vi": "Kiểm tra robot."}),
                 "estop_advised": FALLBACK.get(code, {}).get("level") == 4, "details": details, "source": "local"}
        self._note("alert", code=code, level=local["level"], details=details)
        if self.bridge is None or self.robot_id is None:
            return local
        try:
            remote = self.bridge.alert(self.robot_id, code, job_id=job_id, run_id=run_id, details=details)
            return {**local, **{k: remote[k] for k in ("level", "title_vi", "action_vi", "estop_advised") if k in remote},
                    "id": remote.get("id"), "source": "backend"}
        except Exception as exc:                            # noqa: BLE001
            self._note("bridge_error", op="alert", code=code, error=str(exc))
            return local

    # ---- heartbeat
    def start_heartbeat(self, robot: Any, mode: str, versions: dict[str, str | None]) -> None:
        if self.bridge is None or self.robot_id is None or self._hb is not None:
            return
        self._hb_stop.clear()

        def loop() -> None:
            while not self._hb_stop.is_set():
                try:
                    self.bridge.heartbeat(self.robot_id, mode=mode, **versions)
                except Exception as exc:                    # noqa: BLE001
                    self._note("bridge_error", op="heartbeat", error=str(exc))
                self._hb_stop.wait(self.every)

        self._hb = threading.Thread(target=loop, daemon=True)
        self._hb.start()

    def stop_heartbeat(self) -> None:
        self._hb_stop.set()
        if self._hb is not None:
            self._hb.join(timeout=2)
            self._hb = None
