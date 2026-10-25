"""Read the active TCP and robot poses without a backend, calibration or motion commands.

    .simenv\python.exe scripts\inspect_robot.py --ip 192.168.58.2

This is discovery only: it does not certify TCP calibration or SDK compatibility,
enable REAL, change controller settings, or write agent/calibration configuration.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import math
import sys
import threading
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

READ_METHODS = (
    "GetSoftwareVersion", "GetSDKVersion", "GetActualTCPNum", "GetTCPOffset",
    "GetActualWObjNum", "GetWObjOffset", "GetActualTCPPose",
    "GetActualToolFlangePose", "GetActualJointPosDegree",
    "GetRobotErrorCode", "GetRobotEmergencyStopState",
)


def bounded_call(fn: Callable[[], Any], timeout: float) -> Any:
    box: dict[str, Any] = {}

    def work() -> None:
        try:
            box["result"] = fn()
        except Exception as exc:
            box["error"] = exc

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError(f"No response within {timeout:g}s; inspection aborted, no command retried.")
    if "error" in box:
        raise box["error"]
    return box["result"]


def inspect(rpc: Any, reads: dict[str, Any], timeout: float) -> dict[str, Any]:
    for name in READ_METHODS:
        # The pinned SDK starts with the state STRUCTURE TYPE, before receiving a packet.
        # Cached getters must not report this uninitialised state as a valid tool/pose.
        if name == "GetActualTCPNum" and (
            getattr(rpc, "robot_state_pkg", None) is None
            or isinstance(rpc.robot_state_pkg, type)
        ):
            raise RuntimeError("No decoded realtime state. Check SDK/controller compatibility and port 20004.")
        result = bounded_call(getattr(rpc, name), timeout)
        reads[name] = result
        code = result[0] if isinstance(result, (tuple, list)) and result else result
        if code != 0:
            raise RuntimeError(f"{name} returned SDK error: {result!r}")
        if not isinstance(result, (tuple, list)) or len(result) < 2:
            raise RuntimeError(f"{name} returned no data: {result!r}")

    tcp = reads["GetActualTCPPose"][1]
    flange = reads["GetActualToolFlangePose"][1]
    if any(len(pose) != 6 or not all(math.isfinite(float(v)) for v in pose) for pose in (tcp, flange)):
        raise RuntimeError("Invalid TCP/flange pose; do not use these readings for calibration.")
    return {"flange_to_active_tcp_mm": math.dist(tcp[:3], flange[:3]),
            "note": "Active TCP data is not proof that the pen-tip TCP is calibrated. Compare with the pendant."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", type=ipaddress.IPv4Address, default="192.168.58.2")
    parser.add_argument("--timeout", type=float, default=5.0, help="seconds per SDK operation")
    parser.add_argument("--output", type=Path, default=ROOT / "runs" / "robot_inspection.json")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive finite number")
    report: dict[str, Any] = {"ip": str(args.ip), "ok": False, "reads": {}}
    rpc = None
    print("READ-ONLY INSPECTION: no motion, enable, I/O or configuration commands.", flush=True)
    try:
        from vhrs_agent.fairino_robot import load_sdk

        sdk = load_sdk()
        rpc = bounded_call(lambda: sdk.RPC(str(args.ip)), args.timeout)
        report["derived"] = inspect(rpc, report["reads"], args.timeout)
        report["ok"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if rpc is not None:
            try:
                bounded_call(rpc.CloseRPC, args.timeout)
            except Exception as exc:
                report["close_error"] = f"{type(exc).__name__}: {exc}"
                report["ok"] = False
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {args.output}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
