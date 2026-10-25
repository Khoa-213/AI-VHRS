"""Remote monitor for the Technical Staff: watch the pen move on the paper from another room and stop the job.

A small web app served by the agent (the same agent that holds the robot link). It shows the planned strokes on the
sheet, the live pen position and height, the gripper force against the pen's band, the state and the faults, and it has
PAUSE / RESUME / STOP. It is a window onto the real data stream of whatever robot the agent drives (MOCK, SIM or REAL;
the mode is always shown), never a separate animation. It is NOT a camera: it cannot see paper jams, a person
entering the cell or a pen that broke. The physical emergency stop and a person within reach of it stay mandatory for REAL
runs.

Security: it binds to 127.0.0.1 unless told otherwise; when bound to another address a control token is mandatory, and every
control action (not the read-only stream) needs that token in the X-Viewer-Token header.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hmac
import re
import xml.etree.ElementTree as ET
from math import degrees
from pathlib import Path
from typing import Any

import numpy as np
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.requests import HTTPConnection
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.services.motion.frame import PaperFrame
from app.services.stroke_ai.trajectory import Page

from vhrs_agent.gripper import ForceLimits
from vhrs_agent.runner import JobRunner, Snapshot

STATIC = Path(__file__).parent / "static"
FR3_DIR = Path(__file__).resolve().parents[1] / "vendor" / "fr3"
MAX_VIEW_POINTS = 60_000


Guard = Callable[[str, HTTPConnection], None]       # (level "view" | "control", request or websocket) -> raises HTTPException


class ViewerHub:
    def __init__(self, token: str | None = None, guard: Guard | None = None):
        self.token = token
        self.guard: Guard = guard or self._token_guard
        self.runner: JobRunner | None = None
        self.snapshot: Snapshot = Snapshot()
        self.job: dict[str, Any] = {}
        self.paper_confirmed = threading_event()

    def attach(self, runner: JobRunner, pages: list[Page], frame: PaperFrame, limits: ForceLimits,
               press_mm: float, clearance_mm: float, job_id: int, tool_mm: float | None = None) -> None:
        self.runner = runner
        runner.on_snapshot = self.set_snapshot
        self.job = build_scene(pages, frame, limits, press_mm, clearance_mm, job_id, runner.robot.mode.value, tool_mm)

    def set_snapshot(self, snap: Snapshot) -> None:
        self.snapshot = snap

    def _token_guard(self, level: str, conn: HTTPConnection) -> None:
        """Default: anyone may look; with a shared token configured, control needs it (header X-Viewer-Token or ?token=)."""
        if level == "view" or self.token is None:
            return
        supplied = conn.headers.get("x-viewer-token") or conn.query_params.get("token")
        if not (supplied and hmac.compare_digest(supplied, self.token)):
            raise HTTPException(401, "Cần X-Viewer-Token để điều khiển.")


def build_scene(pages: list[Page], frame: PaperFrame, limits: ForceLimits, press_mm: float, clearance_mm: float, job_id: int,
                mode: str, tool_mm: float | None, max_points: int = MAX_VIEW_POINTS) -> dict[str, Any]:
    """Everything a 3D view draws besides the robot: the sheets, the planned strokes (thinned to `max_points`), the paper frame."""
    n_total = sum(len(s.points) for p in pages for s in p.strokes)
    step = max(1, n_total // max_points)
    return {
        "job_id": job_id, "mode": mode,
        "pages": [{"size": p.paper_size, "width_mm": p.width_mm, "height_mm": p.height_mm,
                   "strokes": [[[round(x, 2), round(y, 2)] for x, y in s.points[::step] + s.points[-1:]]
                               for s in p.strokes if len(s.points) >= 2]} for p in pages],
        "frame": {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in frame.to_dict().items()},
        "limits": dataclasses.asdict(limits), "press_mm": press_mm, "clearance_mm": clearance_mm, "tool_mm": tool_mm}


def threading_event():
    import threading
    return threading.Event()


def create_app(hub: ViewerHub) -> FastAPI:
    app = FastAPI(title="VHRS Robot Agent viewer", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/vendor", StaticFiles(directory=STATIC / "vendor", check_dir=False), name="vendor")

    def model_info() -> dict[str, Any]:
        """What the 3D viewer needs: where the vendor's robot model is and the joint limits it declares."""
        urdf = FR3_DIR / "fairino3_v6.urdf"
        have_js = (STATIC / "vendor" / "urdf-loader" / "src" / "URDFLoader.js").exists()
        joints: list[dict[str, Any]] = []
        if urdf.exists():
            for j in ET.parse(urdf).getroot().findall("joint"):
                lim = j.find("limit")
                joints.append({"name": j.get("name"), "lower_deg": round(degrees(float(lim.get("lower"))), 2),
                               "upper_deg": round(degrees(float(lim.get("upper"))), 2)})
        return {"available": urdf.exists() and have_js and (FR3_DIR / "meshes").exists(), "urdf_url": "/fr3/fairino3_v6.urdf",
                "package_root": "/fr3", "joints": joints, "tool_mm": hub.job.get("tool_mm"),
                "note": "Vendor URDF of the FR3 V6. The base frame is ASSUMED to equal the controller's base frame (verify on the robot)."}

    @app.get("/twin.js")
    def twin_js() -> FileResponse:
        return FileResponse(STATIC / "twin.js", media_type="text/javascript")

    @app.get("/api/model")
    def model() -> dict[str, Any]:
        return model_info()

    @app.get("/api/joints")
    def joints(request: Request) -> dict[str, Any]:
        hub.guard("view", request)
        snap = hub.snapshot
        return {"mode": snap.mode, "state": snap.state, "joints_deg": snap.joints_deg, "tcp_mm": snap.tcp, "force_n": snap.force_n,
                "level": snap.level}

    @app.get("/fr3/fairino3_v6.urdf")
    def urdf() -> FileResponse:
        f = FR3_DIR / "fairino3_v6.urdf"
        if not f.exists():
            raise HTTPException(404, "Chưa có mô hình FR3: chạy scripts/fetch_fr3_model.py")
        return FileResponse(f, media_type="application/xml")

    @app.get("/fr3/meshes/fairino3_v6/{name}")
    def mesh(name: str) -> FileResponse:
        f = FR3_DIR / "meshes" / name
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(?i:stl)", name) or not f.is_file():
            raise HTTPException(404, "Không có mesh này.")
        return FileResponse(f, media_type="model/stl")

    @app.get("/api/job")
    def job(request: Request) -> dict[str, Any]:
        hub.guard("view", request)
        return hub.job

    @app.get("/api/state")
    def state(request: Request) -> dict[str, Any]:
        hub.guard("view", request)
        return dataclasses.asdict(hub.snapshot)

    def _need_runner() -> JobRunner:
        if hub.runner is None:
            raise HTTPException(409, "Chưa có job đang chạy.")
        return hub.runner

    @app.post("/api/pause")
    def pause(request: Request) -> dict[str, str]:
        hub.guard("control", request)
        _need_runner().pause()
        return {"ok": "paused"}

    @app.post("/api/resume")
    def resume(request: Request) -> dict[str, str]:
        hub.guard("control", request)
        _need_runner().resume()
        return {"ok": "resumed"}

    @app.post("/api/stop")
    def stop(request: Request) -> dict[str, str]:
        hub.guard("control", request)
        _need_runner().stop("operator STOP from viewer")
        return {"ok": "stopped"}

    @app.post("/api/paper-changed")
    def paper(request: Request) -> dict[str, str]:
        hub.guard("operate", request)
        hub.paper_confirmed.set()
        return {"ok": "confirmed"}

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        try:
            hub.guard("view", sock)
        except Exception:                                          # HTTPException or a service's own auth error
            await sock.close(code=4401)
            return
        await sock.accept()
        try:
            while True:
                await sock.send_json(dataclasses.asdict(hub.snapshot))
                await asyncio.sleep(0.1)
        except (WebSocketDisconnect, RuntimeError):
            return

    return app
