"""Run the whole test suite faster on the shared (Supabase) database: test files split into shards that run at the same time,
then the files that touch shared state run alone (docs/TEST_SPEEDUP_PLAN.md, T2, owner approved 2026-11-21).

Why: almost all of a Supabase run is network latency (~60 ms per round trip from the dev machine), so N processes in
parallel cut the wall time without changing any test.

How it stays safe:
  * this runner holds the suite's advisory lock for the whole run, so an ordinary `pytest` cannot start meanwhile (and this
    runner refuses to start while one is running); the shards are told so by VHRS_TEST_RUNNER_LOCK=1 and skip that lock;
  * each shard gets its own data prefix (`pytest_s<k>_`, VHRS_TEST_SHARD=s<k>) and its cleanup removes only that prefix, so
    shards never delete each other's rows;
  * `order_types_enabled` is lifted once here and put back at the end (the shards and the serial phase leave it alone);
  * SERIAL_FILES (they change pricing / settings / alert catalog, read whole-system totals, compare robot suggestions or
    measure speed) run after the shards, as one ordinary session whose start and end cleanup remove every `pytest_` row;
  * each shard keeps at most DB_POOL_SIZE + DB_MAX_OVERFLOW connections (Supabase's session pooler caps clients).

If the run is killed, run scripts/recover_after_interrupted_tests.py (restores `order_types_enabled`, removes leftovers).

    .venv/Scripts/python.exe scripts/run_tests_sharded.py               # 3 shards, logs in .test_progress/
    .venv/Scripts/python.exe scripts/run_tests_sharded.py --shards 2 --tag mylabel
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

BE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BE))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402

SUITE_LOCK_KEY = 0x56485253      # same key as tests/conftest.py
SERIAL_FILES = {
    "test_api_orders.py",          # switches order_types_enabled on and off
    "test_api_refunds.py",         # changes the BR-16 threshold in system_settings
    "test_api_manager_ops.py",     # saves new pricing versions, catalog validation
    "test_api_admin_reports.py",   # admin settings / integrations, revenue totals of the whole system
    "test_api_scheduling.py",      # the Manager's top-5 robot suggestion competes with every AVAILABLE robot
    "test_api_robot_ops.py",       # edits the alert catalog other tests rely on
    "test_api_materials.py",       # material suggestions list at most 60 combinations: other shards' test catalog crowds it
    "test_nfr01_performance.py",   # timing limits: must not share the machine / database with other shards
}
# Single tests that fire requests from several threads (or hold an SSE stream) at once: each thread takes its own
# database connection, and with the shards running Supabase's session pooler refused new clients (2026-11-21,
# EMAXCONNSESSION). They are taken out of their shard and run in the serial phase.
SERIAL_TESTS = (
    "test_api_audit_fixes.py::test_concurrent_requests_cannot_book_one_technician_twice",
    "test_api_audit_fixes.py::test_customer_actions_racing_the_webhook_never_fail_with_a_500",
    "test_api_chat_inbox.py::test_a_double_tap_makes_one_card",
    "test_api_chat_inbox.py::test_the_stream_sends_chat_messages_as_their_own_event",
    "test_api_delivery_final.py::test_concurrent_final_payment_starts_and_webhooks_settle_exactly_once",
    "test_api_gateways_real.py::test_identical_ipns_arriving_together_settle_exactly_once",
    "test_api_notifications.py::test_the_stream_says_ready_then_pushes_new_notifications",
    "test_api_payments.py::test_concurrent_identical_webhooks_confirm_the_order_exactly_once",
    "test_api_payos.py::test_identical_webhooks_arriving_together_settle_exactly_once",
    "test_api_photos_acceptance.py::test_accept_and_rewrite_at_the_same_time_leave_one_consistent_result",
    "test_api_shipments.py::test_two_staff_clicks_and_two_identical_callbacks_change_things_once",
    "test_api_technician.py::test_finish_is_idempotent_under_concurrency_and_never_blocked_by_stale_stock",
    "test_v2_acceptance.py::test_a_second_submit_is_refused_even_while_the_first_is_running_and_the_staff_get_one_v1",
)
TIMINGS = BE / ".test_progress" / "test_file_seconds.json"


def _files() -> list[str]:
    return sorted(p.name for p in (BE / "tests").glob("test_*.py"))


def _weights(files: list[str]) -> dict[str, float]:
    """Seconds per file from the last sharded run; otherwise the number of test functions (rough)."""
    known = json.loads(TIMINGS.read_text()) if TIMINGS.exists() else {}
    out = {}
    for f in files:
        if f in known:
            out[f] = float(known[f])
        else:
            src = (BE / "tests" / f).read_text(encoding="utf-8")
            out[f] = 10.0 * max(1, src.count("\ndef test_"))
    return out


def _split(files: list[str], n: int) -> list[list[str]]:
    """Longest-first greedy: each file goes to the currently lightest shard."""
    w = _weights(files)
    shards: list[list[str]] = [[] for _ in range(n)]
    load = [0.0] * n
    for f in sorted(files, key=lambda x: -w[x]):
        i = load.index(min(load))
        shards[i].append(f)
        load[i] += w[f]
    return shards


def _junit(path: Path) -> tuple[dict[str, int], dict[str, float]]:
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    per_file: dict[str, float] = {}
    if not path.exists():
        return counts, per_file
    root = ET.parse(path).getroot()
    for suite in root.iter("testsuite"):
        for k in counts:
            counts[k] += int(suite.get(k, 0))
    for case in root.iter("testcase"):
        f = (case.get("classname") or "").split(".")[1:2]
        if f:
            per_file[f[0] + ".py"] = per_file.get(f[0] + ".py", 0.0) + float(case.get("time") or 0)
    return counts, per_file


def _pytest(targets: list[str], env: dict, log: Path, xml: Path, deselect: list[str] = ()) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", f"--junitxml={xml}",
           *[f"tests/{t}" for t in targets], *[a for d in deselect for a in ("--deselect", f"tests/{d}")]]
    return subprocess.Popen(cmd, cwd=BE, env=env, stdout=log.open("w", encoding="utf-8"), stderr=subprocess.STDOUT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", type=int, default=3)
    ap.add_argument("--tag", default=date.today().isoformat())
    ap.add_argument("--pool-size", type=int, default=3)
    ap.add_argument("--max-overflow", type=int, default=1)
    args = ap.parse_args()

    logs = BE / ".test_progress"
    logs.mkdir(exist_ok=True)
    files = _files()
    parallel = [f for f in files if f not in SERIAL_FILES]
    serial = [f for f in files if f in SERIAL_FILES]
    shards = [s for s in _split(parallel, args.shards) if s]

    engine = create_engine(get_settings().sqlalchemy_url, poolclass=NullPool)
    lock = engine.connect()
    if not lock.execute(text("select pg_try_advisory_lock(:k)"), {"k": SUITE_LOCK_KEY}).scalar():
        print("Another pytest session is running on this database; try again when it has finished.")
        return 3
    lock.commit()
    saved = None
    started = time.time()
    try:
        # AI-10 (audit 2026-11-27): `order_types_enabled` is no longer removed from the database for the run (that opened OT-2 to
        # the real customers meanwhile); every pytest process opens the order types for itself in memory (tests/conftest.py).
        base = {**os.environ, "VHRS_TEST_RUNNER_LOCK": "1", "VHRS_TEST_ORDER_TYPES_OPEN": "1",
                "DB_POOL_SIZE": str(args.pool_size), "DB_MAX_OVERFLOW": str(args.max_overflow), "PYTHONIOENCODING": "utf-8"}
        procs = []
        for i, part in enumerate(shards, 1):
            log, xml = logs / f"sharded_{args.tag}_s{i}.log", logs / f"sharded_{args.tag}_s{i}.xml"
            print(f"shard s{i}: {len(part)} files -> {log.name}")
            out = [t for t in SERIAL_TESTS if t.split("::")[0] in part]
            procs.append((f"s{i}", _pytest(part, {**base, "VHRS_TEST_SHARD": f"s{i}"}, log, xml, out), xml))
        for _, p, _ in procs:
            p.wait()
        t_par = time.time() - started
        print(f"parallel phase: {t_par / 60:.1f} min")
        log, xml = logs / f"sharded_{args.tag}_serial.log", logs / f"sharded_{args.tag}_serial.xml"
        extra = [t for t in SERIAL_TESTS if t.split("::")[0] not in serial]
        print(f"serial: {len(serial)} files + {len(extra)} single tests -> {log.name}")
        sp = _pytest(serial + extra, base, log, xml)
        sp.wait()
        procs.append(("serial", sp, xml))
    finally:
        lock.execute(text("select pg_advisory_unlock(:k)"), {"k": SUITE_LOCK_KEY})
        lock.close()

    total = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    timings = json.loads(TIMINGS.read_text()) if TIMINGS.exists() else {}
    bad = False
    for name, p, xml in procs:
        counts, per_file = _junit(xml)
        timings.update(per_file)
        for k in total:
            total[k] += counts[k]
        bad |= p.returncode not in (0,)
        print(f"{name}: exit {p.returncode}, {counts}")
    TIMINGS.write_text(json.dumps(timings, indent=1, sort_keys=True))
    passed = total["tests"] - total["failures"] - total["errors"] - total["skipped"]
    print(f"TOTAL {passed} passed, {total['skipped']} skipped, {total['failures']} failed, {total['errors']} errors "
          f"in {(time.time() - started) / 60:.1f} min")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
