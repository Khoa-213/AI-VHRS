"""Read-only XML-RPC timing probe; never enables, moves, stops, or configures the robot.

GetSoftwareVersion latency is NOT evidence that ServoCart meets its deadline.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from scripts.inspect_robot import bounded_call
from vhrs_agent.fairino_robot import _SDKWorker, load_sdk


def probe(rpc, *, iterations=5000, period=.008):
    worker = _SDKWorker()
    samples = []
    report = {"READ_ONLY_NO_MOTION": True,
              "note": "GetSoftwareVersion only; not ServoCart hardware validation",
              "period_ms": period * 1000}
    try:
        report["initial_pose"] = worker.call(rpc.GetActualTCPPose, (), 1)
        for index in range(iterations):
            timing = {}
            started = time.perf_counter()
            result = worker.call(rpc.GetSoftwareVersion, (), 1, timing)
            ended = time.perf_counter()
            if result[0] != 0:
                raise RuntimeError(f"Read rejected: {result[0]}")
            samples.append({"index": index, "total_ms": (ended - started) * 1000,
                            "queue_ms": (timing["started"] - timing["queued"]) * 1000,
                            "sdk_execution_ms": (timing["finished"] - timing["started"]) * 1000,
                            "return_ms": (timing["returned"] - timing["finished"]) * 1000})
            wait = started + period - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
        report["final_pose"] = worker.call(rpc.GetActualTCPPose, (), 1)
        report["controller_errors"] = worker.call(rpc.GetRobotErrorCode, (), 1)
        report["emergency_stop"] = worker.call(rpc.GetRobotEmergencyStopState, (), 1)
        report["ok"] = True
    except Exception as exc:
        report.update(ok=False, error=f"{type(exc).__name__}: {exc}")
    finally:
        worker.close()
    report["iterations"] = len(samples)
    if samples:
        report["timing"] = {key: {"mean": float(np.mean(values)), "p99": float(np.percentile(values, 99)),
                                  "max": max(values)}
                            for key in ("total_ms", "queue_ms", "sdk_execution_ms", "return_ms")
                            for values in ([s[key] for s in samples],)}
        report["calls_above_3_periods"] = sum(s["total_ms"] > 3 * period * 1000 for s in samples)
        report["slowest_calls"] = sorted(samples, key=lambda s: s["total_ms"], reverse=True)[:10]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", default="192.168.58.2")
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--output", type=Path, default=ROOT / "runs" / "read_timing_detailed.json")
    args = parser.parse_args()
    if not 1 <= args.iterations <= 10000:
        parser.error("iterations must be 1..10000")
    print("READ-ONLY: GetSoftwareVersion timing. No motion, stop, enable, I/O or configuration.", flush=True)
    rpc = bounded_call(lambda: load_sdk().RPC(args.ip), 5)
    try:
        report = probe(rpc, iterations=args.iterations)
    finally:
        bounded_call(rpc.CloseRPC, 5)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
