"""Technician test console: drive one job from the command line, one step per command, through the backend (the same API the app uses).

    .simenv\\python.exe scripts\\robot_console.py <command> [options]

Settings come from `console.json` next to this folder's README (copy `console.example.json`): backend URL, technician e-mail, job id,
mode. The password comes from the workstation's Windows-encrypted credential, VHRS_TECH_PASSWORD, or an interactive prompt. This tool only sends the same
requests the technician's app will send; the Robot Agent (running on this PC) is what talks to the robot.

Commands, in the order of a job:
  status                     where the job, the agent and the robot are, right now
  prepare                    download the approved sketch package and mark the job PREPARING
  calibrate                  send calibration.json (paper points, motion limits, safe box) to the backend
  simulate                   report the simulation as passed (the backend re-checks it itself and may overrule)
  load                       the agent downloads the job, validates it, prints the plan and the authorization token
  identify                   read-only connection to the robot (no enable, no motion)
  preflight                  all checks, robot does not move
  dry-run                    pen-up rehearsal (REAL: the arm MOVES; asks you to type YES)
  align-start                move the arm (which you put near the start by hand) to the job's fixed start pose with the exact writing
                             orientation. REAL: the arm MOVES slowly; asks you to type YES. Fixes START_ORIENTATION_MISMATCH.
  home                       STOP any run, wait until the arm is still, then bring the pen to the fixed start point (like align-start).
                             Software stop only: if anything is dangerous press the E-Stop first. Asks you to type YES for REAL.
  reset-progress             forget what this job already wrote (LOCAL file on this PC): use ONLY after you put a NEW blank sheet in place.
                             Keeps the finished REAL pen-up rehearsal. Asks you to type YES.
  start                      mark the job WRITING (needed before `run`)
  run                        write (REAL: the arm MOVES and the pen touches the paper; asks you to type YES)
  pause | resume | stop      software pause / resume / stop (NOT a substitute for the E-Stop)
  watch                      live view in the terminal (Ctrl+C to leave; the robot is not affected)
  finish                     mark the job WRITTEN after a completed run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STATE = ROOT / ".console_state.json"

from vhrs_agent.credentials import CredentialError, get_password


class ConsoleError(Exception):
    pass


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConsoleError(f"Chưa có {path}. Sao chép console.example.json thành console.json rồi điền (xem docs/ROBOT_FIRST_REAL_TEST.md).")
    cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    for k in ("backend_url", "email", "job_id"):
        if not cfg.get(k) or str(cfg[k]).startswith("<"):
            raise ConsoleError(f"console.json: hãy điền '{k}'.")
    cfg.setdefault("mode", "SIM")
    return cfg


class Client:
    def __init__(self, cfg: dict[str, Any], transport: httpx.BaseTransport | None = None):
        self.cfg, self.job = cfg, int(cfg["job_id"])
        self.http = httpx.Client(base_url=cfg["backend_url"].rstrip("/") + "/api/v1", timeout=90.0, transport=transport)
        self.token: str | None = None

    def login(self, password: str | None = None) -> None:
        pw = get_password(self.cfg["backend_url"], self.cfg["email"], password)
        r = self.http.post("/auth/login", json={"email": self.cfg["email"], "password": pw})
        if r.status_code != 200:
            raise ConsoleError("Đăng nhập thất bại (sai email/mật khẩu).")
        if r.json()["account"]["role"] != "TECHNICAL_STAFF":
            raise ConsoleError("Tài khoản này không phải Technical Staff.")
        self.token = r.json()["access_token"]

    def call(self, method: str, path: str, **kw: Any) -> Any:
        r = self.http.request(method, path, headers={"Authorization": f"Bearer {self.token}"}, **kw)
        if r.status_code >= 400:
            err = r.json().get("error", {}) if r.headers.get("content-type", "").startswith("application/json") else {}
            raise ConsoleError(f"{r.status_code} {err.get('code', '')}: {err.get('message', r.text[:200])}"
                               + (f"\n  chi tiết: {json.dumps(err.get('details'), ensure_ascii=False)[:600]}" if err.get("details") else ""))
        return r.json() if r.content else None

    # ---- helpers
    def job_detail(self) -> dict[str, Any]:
        return self.call("GET", f"/technician/jobs/{self.job}")

    def robot_id(self) -> int:
        return int(self.job_detail()["robot_id"])

    def command(self, kind: str, params: dict[str, Any] | None = None, wait_s: float = 120.0, with_job: bool = True) -> dict[str, Any]:
        body: dict[str, Any] = {"kind": kind, "params": params or {}, "idempotency_key": str(uuid.uuid4())}
        if with_job:
            body["job_id"] = self.job
        else:
            body["robot_id"] = self.robot_id()
        cmd = self.call("POST", "/technician/robot-commands", json=body)
        end = time.time() + wait_s
        while cmd["status"] in ("PENDING", "DELIVERED") and time.time() < end:
            time.sleep(0.5)
            cmd = self.call("GET", f"/technician/robot-commands/{cmd['id']}")
        return cmd


def save_state(d: dict[str, Any]) -> None:
    STATE.write_text(json.dumps(d), encoding="utf-8")


def load_state() -> dict[str, Any]:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def show_cmd(cmd: dict[str, Any], keys: tuple[str, ...] = ()) -> None:
    label = "ĐÃ XỬ LÝ LỆNH (xem status để biết kết quả chạy)" if cmd['kind'] in ("DRY_RUN", "RUN") and cmd['status'] == "DONE" else cmd['status']
    print(f"  -> {cmd['kind']} {label}" + (f"  [{cmd['error_code']}] {cmd['error_message']}" if cmd.get("error_code") else ""))
    res = cmd.get("result") or {}
    for k in keys:
        if k in res:
            print(f"     {k}: {json.dumps(res[k], ensure_ascii=False)}")


def confirm_real(mode: str, what: str) -> None:
    if mode != "REAL":
        return
    print(f"\n*** {what} bằng robot THẬT: cánh tay sẽ chuyển động. ***")
    print("Kiểm tra: E-Stop trong tầm tay, vùng robot trống, giấy kẹp chặt, đã chạy `real-enable` ở cửa sổ khác cho đúng job này.")
    if input("Gõ YES để tiếp tục: ").strip() != "YES":
        raise ConsoleError("Đã huỷ. Robot không được gửi lệnh.")


# ---------------------------------------------------------------------------------------------- commands
def cmd_status(c: Client, _a: argparse.Namespace) -> None:
    j = c.job_detail()
    print(f"Job {c.job}: {j['status']}  robot_id={j['robot_id']}  can_start={j.get('can_start')}")
    live = c.call("GET", f"/technician/robots/{j['robot_id']}/live")
    print(f"Agent: {'ĐANG KẾT NỐI' if live['agent_online'] else 'CHƯA KẾT NỐI'}  (im lặng {live['age_s']}s)  chế độ agent: {live['mode']}")
    st = live.get("status") or {}
    print(f"Trạng thái: {st.get('state')}  busy={st.get('busy')}  mức cảnh báo={st.get('level')}")
    if st.get("last"):
        rts = st["last"].get("return_to_start") if isinstance(st["last"], dict) else None
        print("Lần chạy gần nhất:", json.dumps({k: v for k, v in st["last"].items() if k != "return_to_start"}, ensure_ascii=False)[:500])
        if rts is not None:
            print("Về điểm bắt đầu sau khi xong:", "ĐÃ VỀ" if rts.get("ok") else f"CHƯA VỀ ({rts.get('code')}: {rts.get('message')}): chạy align-start")
        result = st["last"].get("result") or {}
        if result.get("fault") == "STREAM_OVERRUN" or str(result.get("reason", "")).startswith("Luồng lệnh trễ"):
            print("  Nguyên nhân: trễ nhịp gửi lệnh servo; thông báo này không tự chứng minh đứt mạng. Chưa chạy lại.")
    alerts = c.call("GET", "/technician/alerts", params={"job_id": c.job})
    for a in alerts["items"]:
        print(f"  CẢNH BÁO ĐANG MỞ mức {a['level']}: {a['title_vi']} -> {a['action_vi']}")


def cmd_prepare(c: Client, _a: argparse.Namespace) -> None:
    pkg = c.call("GET", f"/technician/jobs/{c.job}/package")
    print(f"Đã tải gói: order {pkg.get('order_code')}, hash {pkg['package_hash'][:12]}…, bút: {(pkg.get('pen') or {}).get('name')}")
    paper, pen = pkg.get("paper") or {}, pkg.get("pen") or {}
    print(f"Giấy: {paper.get('name')} | khổ: {paper.get('size')} | số trang: {pkg.get('pages')}")
    print(f"Hồ sơ bút: lực mục tiêu {pen.get('f_target_n')} N | tốc độ tối đa {pen.get('v_max_mm_s')} mm/s")
    j = c.call("POST", f"/technician/jobs/{c.job}/prepare")
    print("Job:", j["status"])


def cmd_calibrate(c: Client, a: argparse.Namespace) -> None:
    path = Path(a.file)
    if not path.exists():
        raise ConsoleError(f"Không thấy {path}. Sao chép calibration.example.json thành calibration.json rồi điền số đo.")
    body = json.loads(path.read_text(encoding="utf-8-sig"))
    todo = []

    def walk(x: Any, p: str = "") -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if not k.startswith("_"):
                    walk(v, f"{p}.{k}" if p else k)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{p}[{i}]")
        elif x is None or (isinstance(x, str) and x.startswith("<")):
            todo.append(p)

    def strip(x: Any) -> Any:                                        # keys starting with "_" are notes for the human, never sent
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if not k.startswith("_")}
        return [strip(v) for v in x] if isinstance(x, list) else x

    body = strip(body)
    walk(body)
    if todo:
        raise ConsoleError("calibration.json còn chỗ chưa điền: " + ", ".join(todo))
    out = c.call("POST", f"/technician/jobs/{c.job}/calibration", json=body)
    print("Đã gửi hiệu chuẩn, id", out.get("id"), "- kết quả mô phỏng cũ (nếu có) đã bị xoá: chạy `simulate` lại.")


def cmd_simulate(c: Client, _a: argparse.Namespace) -> None:
    j = c.call("POST", f"/technician/jobs/{c.job}/simulation", json={"passed": True})
    sim = j.get("simulation") or {}
    print("Job:", j["status"], "| kết quả mô phỏng:", json.dumps(sim, ensure_ascii=False)[:600] if sim else "(xem `status`)")
    d = c.job_detail()
    print("can_start =", d.get("can_start"))


def cmd_load(c: Client, _a: argparse.Namespace) -> None:
    # LOAD can wait for BE's package verification, the storage download, then validation.
    cmd = c.command("LOAD", wait_s=240.0)
    show_cmd(cmd)
    res = cmd.get("result") or {}
    if cmd["status"] != "DONE":
        return
    v = res.get("validation", {})
    print(f"  tờ giấy/nét: {res.get('pages')} trang, {res.get('strokes')} nét, ước tính {res.get('estimated_seconds')} giây, bút: {res.get('pen')}")
    print(f"  kiểm chứng quỹ đạo: {'ĐẠT' if v.get('passed') else 'KHÔNG ĐẠT'}  lỗi: {v.get('errors')}  cảnh báo: {v.get('warnings')}")
    save_state({"job": c.job, "authorization_token": res.get("authorization_token"), "plan_digest": res.get("plan_digest")})
    print("  mã xác nhận chạy THẬT đã lưu cho các lệnh sau (gắn với đúng kế hoạch này).")


def _auth(c: Client, mode: str) -> dict[str, Any]:
    if mode != "REAL":
        return {}
    st = load_state()
    if st.get("job") != c.job or not st.get("authorization_token"):
        raise ConsoleError("Chưa có mã xác nhận: chạy `load` trước (mã gắn với job và kế hoạch).")
    return {"authorization": st["authorization_token"]}


def cmd_identify(c: Client, a: argparse.Namespace) -> None:
    cmd = c.command("IDENTIFY", {"mode": a.mode}, with_job=False)
    show_cmd(cmd, ("info", "healthy", "tcp_mm", "joints_deg"))


def cmd_preflight(c: Client, a: argparse.Namespace) -> None:
    cmd = c.command("PREFLIGHT", {"mode": a.mode, **_auth(c, a.mode)})
    show_cmd(cmd, ("ok", "moves", "code", "message", "details", "note"))


def cmd_dry_run(c: Client, a: argparse.Namespace) -> None:
    confirm_real(a.mode, "Chạy thử pen-up")
    cmd = c.command("DRY_RUN", {"mode": a.mode, "speed": a.speed, **_auth(c, a.mode)} if a.speed else {"mode": a.mode, **_auth(c, a.mode)})
    show_cmd(cmd)
    print("  Theo dõi bằng `watch`. Khi dừng, xem `status`: lần chạy gần nhất phải là DRY_RUN_DONE.")


def cmd_align_start(c: Client, a: argparse.Namespace) -> None:
    if not getattr(a, "_skip_confirm", False):                               # `home` already asked for the YES
        confirm_real(a.mode, "Đưa bút về điểm bắt đầu cố định (xoay đúng góc viết)")
    cmd = c.command("ALIGN_START", {"mode": a.mode, **_auth(c, a.mode)}, wait_s=180)
    show_cmd(cmd, ("moved", "distance_mm", "angle_deg", "target_mm", "final_pose", "details"))
    if cmd["status"] == "DONE":
        print("  Xong. Bút đang ở điểm bắt đầu, đúng góc viết. Giờ chạy `preflight` rồi `run`.")


def cmd_home(c: Client, a: argparse.Namespace) -> None:
    confirm_real(a.mode, "DỪNG rồi đưa bút về điểm chờ")
    stop = c.command("STOP", wait_s=30)
    show_cmd(stop)                                                           # NO_RUN_ACTIVE just means nothing was running
    rid = c.robot_id()
    end = time.time() + 60
    while time.time() < end:                                                 # let the run thread finish its stop before moving again
        st = c.call("GET", f"/technician/robots/{rid}/live").get("status") or {}
        if not st.get("busy"):
            break
        time.sleep(0.5)
    else:
        raise ConsoleError("Agent vẫn báo bận sau 60 giây: xem `status`; nếu robot đã đứng yên, thử lại `home` hoặc `align-start`.")
    time.sleep(1.0)
    print("  Robot đã dừng. Đưa bút về điểm chờ…")
    cmd_align_start(c, argparse.Namespace(mode=a.mode, _skip_confirm=True))


def cmd_reset_progress(c: Client, a: argparse.Namespace) -> None:
    import shutil
    agent_cfg = json.loads(Path(a.agent_config).read_text(encoding="utf-8-sig"))
    run_dir = Path(a.agent_config).resolve().parent / agent_cfg.get("run_dir", "runs")
    path = run_dir / f"job{c.job}" / "progress.json"
    if not path.exists():
        print(f"Job {c.job} chưa viết gì (chưa có {path.name}): không cần đặt lại.")
        return
    d = json.loads(path.read_text(encoding="utf-8"))
    print(f"Tiến độ hiện tại: trạng thái {d.get('state')}, đã viết {d.get('completed')} nét.")
    print("Đặt lại nghĩa là lần chạy sau viết từ nét đầu tiên. Nếu tờ giấy còn nét cũ, robot sẽ viết CHỒNG lên.")
    if input("Gõ YES nếu tờ giấy là tờ MỚI, trắng, kẹp đúng vị trí cũ: ").strip() != "YES":
        raise ConsoleError("Đã huỷ. Không thay đổi gì.")
    import time as _t
    backup = path.with_name(path.name + ".bak-" + _t.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, backup)
    d.update({"state": "IDLE", "completed": 0, "interrupted": None, "resume_at": 0})
    path.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"Đã đặt lại về nét đầu (sao lưu: {backup.name}). Chạy thử thật đã đạt vẫn còn hiệu lực nếu bạn không đổi agent.json.")


def cmd_start(c: Client, _a: argparse.Namespace) -> None:
    status = c.job_detail()["status"]
    if status in ("WRITING", "PAUSED"):                                      # nothing to do: `run` already accepts these
        print(f"Job {c.job} đang {status}: không cần bắt đầu lại.")
        return
    print("Job:", c.call("POST", f"/technician/jobs/{c.job}/start")["status"])


def cmd_run(c: Client, a: argparse.Namespace) -> None:
    confirm_real(a.mode, "VIẾT")
    p: dict[str, Any] = {"mode": a.mode, **_auth(c, a.mode)}
    if a.speed:
        p["speed"] = a.speed
    if a.resume_from is not None:
        p["resume_from"] = a.resume_from
    if a.confirm_unknown:
        p["confirm_unknown"] = True
    show_cmd(c.command("RUN", p))
    print("  Theo dõi bằng `watch`. DỪNG khẩn cấp: E-Stop vật lý.")


def _ctl(kind: str):
    def run(c: Client, _a: argparse.Namespace) -> None:
        show_cmd(c.command(kind, wait_s=30))
    return run


def cmd_finish(c: Client, _a: argparse.Namespace) -> None:
    print("Job:", c.call("POST", f"/technician/jobs/{c.job}/finish")["status"])


def cmd_watch(c: Client, _a: argparse.Namespace) -> None:
    rid, last = c.robot_id(), 0
    print("Đang xem (Ctrl+C để thoát; robot không bị ảnh hưởng)…")
    try:
        while True:
            live = c.call("GET", f"/technician/robots/{rid}/live", params={"after": last})
            for f in live["frames"]:
                alerts = " | ".join(f"M{a['level']} {a['title_vi']}" for a in f.get("alerts") or [])
                tcp = f.get("tcp")
                print(f"{f.get('state', '?'):10} nét {f.get('stroke')}/{f.get('total_strokes')}  {f.get('progress_pct', 0):5.1f}%  "
                      f"tcp={[round(v, 1) for v in tcp] if tcp else '-'}  lực={f.get('force_n')}  {alerts}", flush=True)
            last = live["last_seq"]
            if not live["agent_online"]:
                print("!! agent MẤT KẾT NỐI", flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()


COMMANDS = {"status": cmd_status, "prepare": cmd_prepare, "calibrate": cmd_calibrate, "simulate": cmd_simulate, "load": cmd_load,
            "identify": cmd_identify, "preflight": cmd_preflight, "dry-run": cmd_dry_run, "align-start": cmd_align_start, "home": cmd_home, "reset-progress": cmd_reset_progress, "start": cmd_start, "run": cmd_run,
            "pause": _ctl("PAUSE"), "resume": _ctl("RESUME"), "stop": _ctl("STOP"), "watch": cmd_watch, "finish": cmd_finish}


def main(argv: list[str] | None = None, transport: httpx.BaseTransport | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=sorted(COMMANDS))
    p.add_argument("--config", default=str(ROOT / "console.json"))
    p.add_argument("--file", default=str(ROOT / "calibration.json"), help="calibrate: file số đo")
    p.add_argument("--mode", choices=["MOCK", "SIM", "REAL"], default=None, help="mặc định lấy từ console.json")
    p.add_argument("--speed", type=float, default=None, help="SIM: hệ số tốc độ mô phỏng (1 = thời gian thật)")
    p.add_argument("--resume-from", type=int, default=None, dest="resume_from", help="run: viết tiếp từ nét số (chỉ khi job viết dở)")
    p.add_argument("--agent-config", default=str(ROOT / "agent.json"), help="reset-progress: agent.json để biết thư mục runs")
    p.add_argument("--confirm-unknown", action="store_true", dest="confirm_unknown",
                   help="run: bạn đã xem tờ giấy và xác nhận kết quả lần chạy trước không rõ (mất kết nối/agent tắt)")
    a = p.parse_args(argv)
    try:
        cfg = load_settings(Path(a.config))
        a.mode = (a.mode or cfg["mode"]).upper()
        c = Client(cfg, transport)
        c.login()
        COMMANDS[a.command](c, a)
        return 0
    except (ConsoleError, CredentialError) as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"LỖI mạng: không gọi được hệ thống ({exc}). BE có đang chạy không?", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
