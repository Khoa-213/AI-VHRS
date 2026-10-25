"""The agent's outbound link to the backend: the workstation calls OUT, so the technician's phone can drive the robot through the
deployed API without any inbound port at the workshop.

Every `tick` the agent POSTs its state and a live frame to `/agent/sync` and gets the pending commands back (STOP first). Slow
commands (LOAD, PREFLIGHT, IDENTIFY, starting a run) run on one worker thread so that PAUSE / RESUME / STOP are never queued behind
them. Each command is answered once with `/agent/commands/{id}/result`; the backend never re-sends a command, so a command that
arrives is either executed here or refused here, never both.

Lost link while writing (decided by the owner): after `link_loss_grace_s` without a successful sync, the agent finishes the stroke it
is on, lifts the pen and pauses (no motion command is ever re-sent), shows an orange alert locally and reports it to the backend as
soon as the link is back. The agent cannot stop a robot it cannot talk to: the physical E-Stop stays the real safety.

REAL runs are unchanged: the agent still requires `real` in its modes, the on-site `real-enable` file for that job, the plan-bound
authorization token and a finished dry run. A command from the backend cannot bypass any of them.
"""
from __future__ import annotations

import dataclasses
import logging
import queue
import threading
import time
from typing import Any, Callable

import httpx

from app.services.motion.frame import build_frame

from vhrs_agent import __version__
from vhrs_agent.server import AgentService, ApiError, JobCtx
from vhrs_agent.viewer import build_scene

log = logging.getLogger("vhrs_agent.link")
LINK_WHO = {"id": 0, "role": "TECHNICAL_STAFF", "name": "app"}      # commands come from an authenticated technician at the backend
SCENE_MAX_POINTS = 12_000                                            # the scene is stored with the LOAD command: keep it small
CONTROL = ("PAUSE", "RESUME", "STOP")


class LinkClient:
    def __init__(self, service: AgentService, *, key: str | None = None, provider: Any = None,
                 transport: httpx.BaseTransport | None = None, clock: Callable[[], float] = time.monotonic):
        """`key`: a fixed agent key (Manager-issued). `provider`: a SessionKeyProvider (technician login): its key renews itself."""
        if (key is None) == (provider is None):
            raise ValueError("give exactly one of key or provider")
        self.svc, self._fixed_key, self.provider, self.clock = service, key, provider, clock
        cfg = service.cfg
        self.http = httpx.Client(base_url=cfg.backend_url.rstrip("/") + "/api/v1/agent", transport=transport, timeout=8.0)
        self.last_ok = clock()
        self.link_lost = False                                      # a loss during a write was handled and not yet reported
        self.lost_reported = True
        self._slow: "queue.Queue[dict[str, Any] | None]" = queue.Queue()
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self.versions: dict[str, str | None] = {"agent_version": __version__}

    def _key(self) -> str:
        """The key to use right now. Passed as a callable to long runs so a renewal in the middle of a run is picked up."""
        return self.provider.current() if self.provider is not None else self._fixed_key

    @property
    def key(self) -> str:
        return self._key()

    # ---- loop
    def run_forever(self) -> None:                                  # pragma: no cover - the process main loop
        self._worker = threading.Thread(target=self._work, daemon=True, name="link-commands")
        self._worker.start()
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.svc.cfg.sync_active_s if self.svc._busy else self.svc.cfg.sync_idle_s)

    def close(self) -> None:
        self._stop.set()
        self._slow.put(None)

    def tick(self) -> None:
        snap = dataclasses.asdict(self.svc.hub.snapshot)
        snap["t"] = round(time.time(), 3)
        status = {"mode": (snap.get("mode") or ("SIM" if "sim" in self.svc.cfg.modes else "MOCK")).upper(), "busy": self.svc._busy,
                  "current": self.svc.current, "last": self.svc.last, "state": snap["state"], "level": snap["level"],
                  "enabled_modes": [m.upper() for m in self.svc.cfg.modes], "agent_version": __version__}
        body = {"status": status, "frames": [snap] if (self.svc._busy or snap["state"] != "IDLE" or snap["joints_deg"]) else [],
                **{k: v for k, v in self.versions.items() if v}}
        try:
            r = self.http.post("/sync", json=body, headers={"Authorization": f"Bearer {self._key()}"})
            if r.status_code == 401:
                log.error("backend refused the agent key (revoked, expired or wrong): %s", r.text[:160])
                if self.provider is not None:
                    self.provider.renew_now()                         # e.g. the backend restarted or the key was cut: ask for a fresh one
                raise httpx.HTTPError("agent key refused")
            r.raise_for_status()
            cmds = r.json()["commands"]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            self._on_failure(exc)
            return
        self._on_success()
        for c in cmds:
            if c["kind"] in CONTROL:
                self.handle(c)                                      # inline: never wait behind a slow command
            else:
                self._slow.put(c)
                if self._worker is None:                            # tests drive ticks by hand
                    self.drain()

    def drain(self) -> None:
        """Run queued slow commands in the calling thread (the worker thread does this in production)."""
        while True:
            try:
                c = self._slow.get_nowait()
            except queue.Empty:
                return
            if c is not None:
                self.handle(c)

    def _work(self) -> None:                                        # pragma: no cover - thread body
        while True:
            c = self._slow.get()
            if c is None:
                return
            self.handle(c)

    # ---- link state
    def _on_success(self) -> None:
        self.last_ok = self.clock()
        if self.link_lost and not self.lost_reported:
            self.lost_reported = True
            runner = self.svc.hub.runner
            try:
                self.svc.bridge(self._key).alert(self._robot_id(), "BACKEND_LINK_LOST", job_id=(self.svc.current or {}).get("job_id"),
                                                run_id=getattr(runner, "run_id", None) or None,
                                                details={"note": "reported after the link came back; the run was paused after the stroke"})
            except Exception as exc:                                # noqa: BLE001 - try again on the next success
                self.lost_reported = False
                log.warning("could not report the lost link yet: %s", exc)

    def _on_failure(self, exc: Exception) -> None:
        log.warning("sync failed: %s", exc)
        if self.link_lost or not self.svc._busy or self.clock() - self.last_ok < self.svc.cfg.link_loss_grace_s:
            return
        runner = self.svc.hub.runner
        cur = self.svc.current or {}
        if runner is None or cur.get("dry_run"):
            return                                                  # nothing is being written; a rehearsal can simply run on
        self.link_lost, self.lost_reported = True, False
        runner.pause_after_stroke("link to the backend lost")
        runner._raise("BACKEND_LINK_LOST", {"quiet_s": round(self.clock() - self.last_ok, 1)})   # shown locally; the backend is unreachable

    def _robot_id(self) -> int:
        ctx = next(iter(self.svc.jobs.values()), None)
        cur = self.svc.current or {}
        job = self.svc.jobs.get(cur.get("job_id")) if cur else ctx
        return job.robot_id if job else 0

    # ---- commands
    def handle(self, c: dict[str, Any]) -> None:
        try:
            result = self.execute(c)
            body = {"ok": True, "result": result}
        except ApiError as exc:
            body = {"ok": False, "error_code": exc.code, "message": exc.message, "result": {"details": exc.details} if exc.details else None}
        except Exception as exc:                                    # noqa: BLE001 - a command must always be answered
            log.exception("command %s failed", c.get("id"))
            body = {"ok": False, "error_code": "AGENT_ERROR", "message": f"{type(exc).__name__}: {exc}"}
        for attempt in range(3):
            try:
                self.http.post(f"/commands/{c['id']}/result", json=body, headers={"Authorization": f"Bearer {self._key()}"}).raise_for_status()
                return
            except httpx.HTTPError as exc:
                log.warning("could not answer command %s (try %d): %s", c["id"], attempt + 1, exc)
                time.sleep(0.2)

    def _ctx(self, job_id: int | None) -> JobCtx:
        if job_id is None:
            raise ApiError(422, "JOB_REQUIRED", "Lệnh này cần job_id.")
        return self.svc.ctx(job_id, LINK_WHO)

    def execute(self, c: dict[str, Any]) -> dict[str, Any]:
        kind, p, job_id = c["kind"], c.get("params") or {}, c.get("job_id")
        mode = str(p.get("mode", "sim")).lower()
        svc = self.svc
        if kind == "LOAD":
            ctx = svc.load_job(job_id, self._key, LINK_WHO)
            frame = build_frame(ctx.probes)
            scene = build_scene(ctx.pages, frame, ctx.limits, ctx.cfg.press_mm, ctx.cfg.pen_up_clearance_mm or 0.0, ctx.job_id,
                                "SIM" if "sim" in svc.cfg.modes else "MOCK", None, max_points=SCENE_MAX_POINTS)
            return {**ctx.summary, "scene": scene}
        if kind == "PREFLIGHT":
            return svc.do_preflight(self._ctx(job_id), mode, self._key)
        if kind in ("DRY_RUN", "RUN"):
            return svc.start(self._ctx(job_id), self._key, "app", mode=mode, dry_run=kind == "DRY_RUN", authorization=p.get("authorization"),
                             resume_from=p.get("resume_from"), confirm_unknown=bool(p.get("confirm_unknown", False)), speed=p.get("speed"))
        if kind == "ALIGN_START":
            return svc.do_align(self._ctx(job_id), mode, p.get("authorization"))
        if kind == "IDENTIFY":
            return svc.do_identify(mode)
        if kind == "PAPER_CHANGED":
            svc.paper_event.set()
            return {"ok": "confirmed"}
        if kind in ("PAUSE", "STOP") and svc.align_ctl is not None:       # an alignment move is in progress: both stop it in place
            svc.align_ctl.request_stop("operator " + kind)
            return {"ok": "stopped"}
        runner = svc.need_runner()
        if kind == "PAUSE":
            runner.pause()
            return {"ok": "paused"}
        if kind == "RESUME":
            runner.resume()
            return {"ok": "resumed"}
        if kind == "STOP":
            runner.stop("operator STOP from the app")
            return {"ok": "stopped"}
        raise ApiError(422, "UNKNOWN_COMMAND", f"Lệnh không hỗ trợ: {kind}")
