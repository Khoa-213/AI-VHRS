"""Create one OT-3 test job through the real backend API, from order to a job scheduled on the technician's robot.

    .simenv\\python.exe -X utf8 scripts\\create_test_job.py [--text "bảng test thứ 100"] [--size 15]
    .simenv\\python.exe -X utf8 scripts\\create_test_job.py --order 14942      # continue an order made by an earlier run

It goes through every business step with the existing accounts (customer -> Staff -> customer -> Manager), so the job is a normal
job in the database. Each step runs only when the order is in the state it needs, so a run that stopped can be continued.
The deposit uses the MOCK gateway only (no money); if the backend answers with a real gateway it stops.
Passwords are asked hidden and never stored. At the end console.json gets the new job id.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


class Stop(Exception):
    pass


class Api:
    def __init__(self, base: str, label: str):
        self.http = httpx.Client(base_url=base.rstrip("/") + "/api/v1", timeout=120.0)
        self.label, self.token = label, None

    def login(self, email: str) -> None:
        pw = getpass.getpass(f"Mật khẩu {self.label} ({email}): ")
        r = self.http.post("/auth/login", json={"email": email, "password": pw})
        if r.status_code != 200:
            raise Stop(f"Đăng nhập {self.label} {email} thất bại: {r.status_code} {r.text[:200]}")
        self.token = r.json()["access_token"]

    def __call__(self, method: str, path: str, **kw):
        if method in ("POST", "PUT", "PATCH") and "json" not in kw:
            kw["json"] = {}                                      # the API wants a JSON body even when it has no fields
        r = self.http.request(method, path, headers={"Authorization": f"Bearer {self.token}"} if self.token else {}, **kw)
        if r.status_code >= 400:
            raise Stop(f"{self.label}: {method} {path} -> {r.status_code} {r.text[:600]}")
        return r.json() if r.content else None


def step(msg: str) -> None:
    print(f"\n=== {msg}", flush=True)


def create_order(cus: Api, a: argparse.Namespace) -> int:
    step("Khách: chọn giấy A4, bút, mực, mẫu chữ")
    papers = [x for x in cus("GET", "/catalog/papers") if x["size"] == "A4"]
    if not papers:
        raise Stop("Không có giấy A4 đang bán.")
    paper = next((x for x in papers if "PLAIN" in str(x.get("code", "")).upper()), papers[0])
    pens = cus("GET", "/catalog/pens", params={"paper_id": paper["id"]})
    if not pens:
        raise Stop(f"Không có bút hợp với giấy {paper['name']}.")
    pen = next((x for x in pens if "BALL" in str(x.get("code", "")).upper()), pens[0])
    inks = cus("GET", f"/catalog/pens/{pen['id']}/inks")
    ink = next((x for x in inks if x["name"].lower().startswith("đen")), inks[0]) if inks else None
    templates = cus("GET", "/catalog/templates")
    tpl = next((t for t in templates if t["kind"] != "TYPOGRAPHY"), templates[0])
    print(f"  giấy {paper['name']} | bút {pen['name']} | mực {ink['name'] if ink else '-'} | mẫu {tpl['name']} ({tpl['kind']})")

    step("Khách: tạo đơn OT-3, nhập chữ (giữa tờ giấy), gửi đơn")
    order = cus("POST", "/orders", json={"order_type": "OT3_TEMPLATE", "quantity": 1})
    oid = order["id"]
    cus("PATCH", f"/orders/{oid}", json={"paper_type_id": paper["id"], "pen_type_id": pen["id"],
                                         **({"ink_color_id": ink["id"]} if ink else {})})
    cus("PUT", f"/orders/{oid}/inputs/text", json={
        "text_content": a.text, "template_id": tpl["id"], "font_size_mm": a.size, "alignment": "CENTER",
        "layout": {"version": 1, "vertical_align": "MIDDLE"}})
    cus("POST", f"/orders/{oid}/submit", json={"terms_accepted": True})
    print(f"  đơn {oid} ({order.get('order_code', '')}) đã gửi")
    return oid


def schedule(man: Api, a: argparse.Namespace, oid: int, cfg: dict) -> None:
    step(f"Manager: xếp lịch cho kỹ thuật viên của robot {a.robot}")
    robot = next((r for r in man("GET", "/manager/robots") if r["id"] == a.robot), None)
    if robot is None or not robot.get("technician_id"):
        raise Stop(f"Robot {a.robot} không có hoặc chưa giao cho kỹ thuật viên nào.")
    slot = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(microsecond=0).isoformat()
    job = man("POST", f"/manager/orders/{oid}/schedule",
              json={"technician_id": robot["technician_id"], "robot_id": a.robot, "slot_start": slot, "note": f"Test: {a.text}"})
    print(f"  JOB {job['id']} ({job.get('status')}) cho {robot.get('technician_name')} trên robot {a.robot}")
    cfg["job_id"] = job["id"]
    (ROOT / "console.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nĐã ghi job_id = {job['id']} vào console.json. Tiếp theo: robot_console.py status, rồi prepare.")


def main() -> int:
    cfg = json.loads((ROOT / "console.json").read_text(encoding="utf-8-sig"))
    p = argparse.ArgumentParser()
    p.add_argument("--text", default="bảng test thứ 100")
    p.add_argument("--size", type=float, default=15.0, help="cỡ chữ mm (4-100)")
    p.add_argument("--backend", default=cfg["backend_url"])
    p.add_argument("--customer", default=None)
    p.add_argument("--staff", default="staff@netviet.vn")
    p.add_argument("--manager", default="manager@netviet.vn")
    p.add_argument("--robot", type=int, default=46)
    p.add_argument("--order", type=int, default=None, help="chạy tiếp một đơn đã tạo (bỏ qua bước khách tạo đơn)")
    a = p.parse_args()
    customer_email = a.customer or input("E-mail tài khoản khách hàng (Customer) của đơn: ").strip()

    cus, staff, man = Api(a.backend, "khách"), Api(a.backend, "Staff"), Api(a.backend, "Manager")
    cus.login(customer_email)
    staff.login(a.staff)
    man.login(a.manager)

    if a.order is None:
        oid = create_order(cus, a)
    else:
        oid = a.order

    def status() -> str:
        return cus("GET", f"/orders/{oid}")["order_status"]

    print(f"\nĐơn {oid}: {status()}")
    if status() in ("SUBMITTED", "ACCEPTED"):
        step("Staff: nhận đơn, tiếp nhận, sinh phác thảo A4, chốt, lập và gửi báo giá")
        if status() == "SUBMITTED":
            try:
                staff("POST", f"/workshop/orders/{oid}/claim")
            except Stop as exc:
                print(f"  (nhận đơn: {exc}) -> có thể đã nhận rồi, làm tiếp")
            staff("POST", f"/workshop/orders/{oid}/accept")
        sk = staff("POST", f"/workshop/orders/{oid}/sketches/generate", json={"paper_size": "A4"})
        staff("POST", f"/workshop/orders/{oid}/sketches/{sk['version']}/finalize")
        q = staff("POST", f"/workshop/orders/{oid}/quotations", json={})
        staff("POST", f"/workshop/quotations/{q['id']}/send")
        print(f"  phác thảo v{sk['version']}, báo giá {q['id']} đã gửi")

    if status() in ("AWAITING_PRIVACY", "QUOTED", "AWAITING_DEPOSIT"):
        step("Khách: đồng ý chính sách (nếu cần), duyệt báo giá, đặt cọc MOCK")
        if status() == "AWAITING_PRIVACY":
            cus("POST", f"/orders/{oid}/privacy", json={"accept": True})
        if status() == "QUOTED":
            cus("POST", f"/orders/{oid}/quotation/approve", json={})
        pay = cus("POST", f"/orders/{oid}/payments/deposit", json={"gateway": "VNPAY"})
        if pay.get("mode") == "MOCK":
            res = cus("POST", f"/payments/{pay['id']}/mock-checkout", json={"result": "SUCCESS"})
            print(f"  cọc MOCK: {res.get('status')} -> đơn {res.get('order_status')}")
        elif pay.get("mode") == "SANDBOX" and pay.get("pay_url"):
            print(f"  Cổng {pay['gateway']} ở chế độ SANDBOX (môi trường thử, không trừ tiền thật), số tiền {pay.get('amount')}.")
            print("  Mở link này trong trình duyệt và tự thanh toán bằng thẻ thử của VNPay:")
            print(f"\n  {pay['pay_url']}\n")
            for _ in range(10):
                input("  Thanh toán xong (trang báo thành công) thì bấm Enter...")
                if status() == "CONFIRMED":
                    print("  Đã nhận cọc -> CONFIRMED")
                    break
                print(f"  Đơn vẫn {status()}: BE chưa nhận kết quả. Đợi vài giây rồi bấm Enter lại.")
        else:
            raise Stop(f"Cổng thanh toán ở chế độ {pay.get('mode')}: dừng, không trả tiền. Đơn {oid} đang chờ cọc.")

    if status() != "CONFIRMED":
        raise Stop(f"Đơn {oid} đang {status()}, chưa CONFIRMED: không xếp lịch được.")
    schedule(man, a, oid, cfg)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Stop as exc:
        print(f"\nDỪNG: {exc}", file=sys.stderr)
        sys.exit(1)
