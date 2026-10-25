"""Command line.

  python -m vhrs_agent.cli demo            SIM only: writes a sample sentence on a simulated robot and opens the viewer
  python -m vhrs_agent.cli authorize ...   prints the token an operator must give for a REAL run of this exact plan
  python -m vhrs_agent.cli run ...         runs a backend job (MOCK / SIM / REAL)

Nothing here moves a real robot unless `--mode real` is given together with the matching `--authorize` token and a finished
pen-up dry run of the same plan. The authors never run REAL mode; the operator does, on site, next to the emergency stop.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

from app.services.motion.frame import build_frame
from app.services.motion.plan import MotionConfig
from app.services.motion.validate import Workspace, validate
from app.services.stroke_ai import text_to_stroke as tts

from vhrs_agent.gripper import ForceLimits, SimGripper
from vhrs_agent.port import Mode
from vhrs_agent.runner import JobRunner, RunRefused, Watchdogs, authorization_token, plan_digest
from vhrs_agent.sim import MockRobot, RunawaySimRobot, SimRobot
from vhrs_agent.viewer import ViewerHub, create_app

# DEMO fixtures only. They exist so the simulator can be watched; they are NOT measurements of any robot or paper.
DEMO_PROBES = [{"x": -250.0, "y": -74.0, "z": 20.0}, {"x": -250.0, "y": 74.0, "z": 20.0}, {"x": -460.0, "y": -74.0, "z": 20.0}]
DEMO_TOOL_MM = 250.0            # wrist3 frame to pen tip (flange ~103 mm + gripper + pen): a demo value, the real one is measured
DEMO_START = (-350.0, 0.0, 80.0)
DEMO_CFG = MotionConfig(a_lat_mm_s2=2000.0, a_tan_mm_s2=1000.0, travel_speed_mm_s=100.0, approach_speed_mm_s=10.0,
                        pen_up_clearance_mm=5.0, spring_k_n_per_mm=0.4, max_spring_travel_mm=6.0, f_target_n=1.0,
                        v_max_mm_s=40.0)
DEMO_WS = Workspace(box_min_mm=(-600.0, -300.0, -50.0), box_max_mm=(0.0, 300.0, 200.0))
DEMO_LIMITS = ForceLimits(f_min=0.6, f_target=1.0, f_max=1.6, f_hard=4.0)
# DEMO values for rehearsing the alerts; the real thresholds are measured on the robot.
DEMO_WATCHDOGS = Watchdogs(stop_settle_s=0.3, stop_window_s=0.5, stop_tolerance_mm=1.0, tracking_tolerance_mm=5.0, tracking_grace_s=0.5)


def _serve(hub: ViewerHub, host: str, port: int) -> None:
    import uvicorn
    threading.Thread(target=lambda: uvicorn.run(create_app(hub), host=host, port=port, log_level="warning"), daemon=True).start()


def _make_robot(a: argparse.Namespace):
    """The robot for the demo: with a joint model (PyBullet + the vendor's URDF) when available, else the simple timing model."""
    if a.scenario == "runaway":
        return RunawaySimRobot(DEMO_START, speed_factor=a.speed)
    if a.sim in ("auto", "pybullet"):
        try:
            from vhrs_agent.kinematics import FR3Kinematics
            from vhrs_agent.sim_pybullet import PyBulletSimRobot
            return PyBulletSimRobot(FR3Kinematics(tool_offset_mm=DEMO_TOOL_MM, table_z_mm=19.0), DEMO_START, speed_factor=a.speed)
        except Exception as exc:                                       # noqa: BLE001 - PyBullet or the model may be missing
            if a.sim == "pybullet":
                raise
            print(f"(simple SIM: no joint model because {exc})")
    return SimRobot(DEMO_START, speed_factor=a.speed)


def cmd_demo(a: argparse.Namespace) -> int:
    pages = tts.compose_text(a.text, font_name="futural", paper_size="A5", font_size_mm=7.0, alignment="LEFT", seed=1)
    frame = build_frame(DEMO_PROBES)

    def depth(p: np.ndarray) -> float:
        rel = np.asarray(p) - frame.origin
        return -(float(rel @ frame.normal) - float(frame.height(rel @ frame.x_axis, rel @ frame.y_axis)))

    robot = _make_robot(a)
    k = 3.0 if a.scenario == "overforce" else 0.4                     # a far too stiff spring model makes the force exceed F_hard
    runner = JobRunner(robot, SimGripper(depth, k, DEMO_LIMITS.f_hard, DEMO_CFG.max_spring_travel_mm),
                       run_dir=Path(a.run_dir), limits=DEMO_LIMITS, watchdogs=DEMO_WATCHDOGS)
    hub = ViewerHub(token=a.token)
    hub.attach(runner, pages, frame, DEMO_LIMITS, DEMO_CFG.press_mm, DEMO_CFG.pen_up_clearance_mm, job_id=0, tool_mm=DEMO_TOOL_MM)
    _serve(hub, a.host, a.port)
    print(f"SIMULATION. Viewer: http://{a.host}:{a.port}/   (Ctrl+C to leave)")
    time.sleep(1.5)
    kw = dict(job_id=0, pages=pages, package_hash="0" * 64, probes=DEMO_PROBES, cfg=DEMO_CFG, ws=DEMO_WS)
    res = runner.run(dry_run=True, **kw)
    print("dry run:", res.state)
    if a.scenario == "runaway":                                        # the operator presses STOP a few seconds into the writing
        threading.Timer(3.0, lambda: runner.stop("operator pressed STOP (rehearsal)")).start()
        print("REHEARSAL: the simulated robot will ignore the stop command; watch the red alert.")
    res = runner.run(**kw)
    print("write  :", res.state, f"{res.completed_strokes}/{res.total_strokes} strokes", res.force_summary)
    time.sleep(a.linger)
    return 0 if res.state == "DONE" else 1


def cmd_authorize(a: argparse.Namespace) -> int:
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    digest = plan_digest(cfg["package_hash"], cfg["probe_points"], MotionConfig.from_dict(cfg["motion"]),
                         Workspace.from_dict(cfg.get("workspace")))
    print(f"job {a.job}  plan digest {digest[:16]}…")
    print("Operator, after checking the paper, the pen, the cell and the emergency stop, may authorize THIS plan with:")
    print("  ", authorization_token(a.job, digest))
    return 0


def cmd_run(a: argparse.Namespace) -> int:                                   # pragma: no cover - needs a backend
    from vhrs_agent.bridge import BackendBridge
    token = os.environ.get("VHRS_TOKEN")
    if not token:
        print("Set VHRS_TOKEN (the technician's access token) in the environment.", file=sys.stderr)
        return 2
    bridge = BackendBridge(a.backend, token)
    job = bridge.fetch_job(a.job)
    detail = bridge._req("GET", f"/jobs/{a.job}")
    cal = detail.get("calibration")
    if not cal:
        print("The job has no valid calibration yet.", file=sys.stderr)
        return 2
    block = cal.get("frame_transform") or {}
    cfg = MotionConfig.from_dict({**(block.get("motion") or {}), "f_target_n": job["package"]["pen"]["f_target_n"],
                                  "v_max_mm_s": job["package"]["pen"]["v_max_mm_s"]})
    ws = Workspace.from_dict(block.get("workspace"))
    pen = job["package"]["pen"]
    limits = ForceLimits(pen["f_min_n"], pen["f_target_n"], pen["f_max_n"], pen["f_hard_n"])
    if a.mode == "real":
        print("REAL mode is wired for the operator's on-site session only; see docs/ROBOT_AGENT.md section 'First real run'.")
        return 3
    robot = MockRobot((0, 0, 100)) if a.mode == "mock" else SimRobot((200.0, 0.0, 80.0), speed_factor=a.speed)
    frame = build_frame(cal["probe_points"])

    def depth(p: np.ndarray) -> float:
        rel = np.asarray(p) - frame.origin
        return -(float(rel @ frame.normal) - float(frame.height(rel @ frame.x_axis, rel @ frame.y_axis)))

    gripper = SimGripper(depth, cfg.spring_k_n_per_mm or 0.4, limits.f_hard, cfg.max_spring_travel_mm or 6.0)
    runner = JobRunner(robot, gripper, run_dir=Path(a.run_dir), limits=limits, bridge=bridge)
    hub = ViewerHub(token=a.token)
    hub.attach(runner, job["pages"], frame, limits, cfg.press_mm if not cfg.missing() else 0.0,
               cfg.pen_up_clearance_mm or 0.0, a.job)
    _serve(hub, a.host, a.port)
    try:
        res = runner.run(job_id=a.job, pages=job["pages"], package_hash=job["hash"], probes=cal["probe_points"], cfg=cfg,
                         ws=ws, dry_run=a.dry_run, resume_from=a.resume_from, confirm_unknown=a.confirm_unknown)
    except RunRefused as exc:
        print("REFUSED:", exc.code, exc.message, exc.details or "")
        return 1
    print(res)
    return 0 if res.state in ("DONE", "DRY_RUN_DONE") else 1


def cmd_serve(a: argparse.Namespace) -> int:                                  # pragma: no cover - starts a server
    from vhrs_agent.server import ServerConfig, serve
    cfg = ServerConfig.from_file(a.config)
    if a.host:
        cfg.host = a.host
    if a.port:
        cfg.port = a.port
    print(f"Robot Agent {cfg.host}:{cfg.port}  backend {cfg.backend_url}  modes {list(cfg.modes)}"
          + ("  TLS" if cfg.tls_certfile else "  (no TLS: use it only on a trusted LAN)"))
    serve(cfg)
    return 0


def cmd_real_enable(a: argparse.Namespace) -> int:
    """A person at the workstation allows ONE job to run on the real robot for a limited time. A remote API call cannot do this."""
    import getpass
    import json
    import time
    from vhrs_agent.server import REAL_ENABLE_MAX_MINUTES, ServerConfig
    if not 1 <= a.minutes <= REAL_ENABLE_MAX_MINUTES:
        print(f"--minutes must be 1..{REAL_ENABLE_MAX_MINUTES}", file=sys.stderr)
        return 2
    cfg = ServerConfig.from_file(a.config)
    f = cfg.run_dir / "REAL_ENABLED.json"
    if a.off:
        f.unlink(missing_ok=True)
        print("REAL disabled.")
        return 0
    print("You are about to allow job", a.job, "to move the REAL robot for", a.minutes, "minutes.")
    if input("Is a person next to the emergency stop, the cell clear and the paper fixed? Type YES: ").strip() != "YES":
        print("Not enabled.")
        return 1
    waive = bool(getattr(a, "waive_dry_run", False))
    if waive:
        print("WAIVER: the REAL pen-up rehearsal is skipped for this job. The pen will touch the paper on its very first move of this plan.")
        if input("Type SKIP-DRY-RUN to accept that risk (anything else cancels): ").strip() != "SKIP-DRY-RUN":
            print("Not enabled.")
            return 1
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"job_id": a.job, "expires_at": time.time() + a.minutes * 60, "enabled_by": getpass.getuser(),
                             "enabled_at": time.time(), "waive_dry_run": waive}), encoding="utf-8")
    print("Enabled until", time.strftime("%H:%M:%S", time.localtime(time.time() + a.minutes * 60)))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vhrs_agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    d.add_argument("--text", default="Xin chào Việt Nam")
    d.add_argument("--sim", choices=["auto", "simple", "pybullet"], default="auto",
                   help="pybullet = vendor URDF kinematics (joint angles, 3D arm); simple = pen-tip timing model only")
    d.add_argument("--scenario", choices=["normal", "overforce", "runaway"], default="normal",
                   help="normal; overforce = the pen presses too hard (orange alert); runaway = the robot ignores STOP (red alert)")
    d.add_argument("--speed", type=float, default=4.0, help="simulation speed factor (1 = real time)")
    d.add_argument("--host", default="127.0.0.1")
    d.add_argument("--port", type=int, default=8765)
    d.add_argument("--token", default=None, help="required when --host is not 127.0.0.1")
    d.add_argument("--run-dir", default="runs-demo")
    d.add_argument("--linger", type=float, default=600.0)
    sv = sub.add_parser("serve", help="run the agent as a network service (HTTP API + 3D viewer + control console)")
    sv.add_argument("--config", required=True)
    sv.add_argument("--host", default=None)
    sv.add_argument("--port", type=int, default=None)
    re_ = sub.add_parser("real-enable", help="at the workstation: allow one job to run on the REAL robot for a limited time")
    re_.add_argument("--config", required=True)
    re_.add_argument("--job", type=int, default=0)
    re_.add_argument("--minutes", type=int, default=30)
    re_.add_argument("--off", action="store_true")
    re_.add_argument("--waive-dry-run", action="store_true", dest="waive_dry_run",
                     help="skip the REAL pen-up rehearsal for this job (asks for an extra confirmation; recorded in the run log and the run record)")
    a_ = sub.add_parser("authorize")
    a_.add_argument("--job", type=int, required=True)
    a_.add_argument("--config", required=True)
    r = sub.add_parser("run")
    r.add_argument("--backend", required=True)
    r.add_argument("--job", type=int, required=True)
    r.add_argument("--mode", choices=["mock", "sim", "real"], default="sim")
    r.add_argument("--speed", type=float, default=1.0)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--resume-from", type=int, default=None)
    r.add_argument("--confirm-unknown", action="store_true")
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--port", type=int, default=8765)
    r.add_argument("--token", default=None)
    r.add_argument("--run-dir", default="runs")
    args = p.parse_args(argv)
    if args.cmd in ("demo", "run") and getattr(args, "host", "127.0.0.1") != "127.0.0.1" and not getattr(args, "token", None):
        print("A control token (--token) is mandatory when the viewer listens on a network address.", file=sys.stderr)
        return 2
    return {"demo": cmd_demo, "authorize": cmd_authorize, "run": cmd_run, "serve": cmd_serve,
            "real-enable": cmd_real_enable}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
