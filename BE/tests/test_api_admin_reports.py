"""Phase 5b: Admin system parameters / integrations / dashboard (UC-49, 50, 52) and the Manager dashboard / reports (UC-45, 46,
FR-50). Real database.

The shared database holds the real settings: a test never changes a value, it only writes the value already in force (a no-op
for the business) to exercise the write path and the audit; every refused value is checked to have changed nothing.
Report figures include real data, so they are checked as differences before / after the test's own payment.
"""
import io
import json
from datetime import date, timedelta

from openpyxl import load_workbook

from tests.test_api_orders import API, _sql
from tests.test_api_payments import _paid
from tests.test_api_workshop import _err, _user, cust, policy, staff, store, wcat  # noqa: F401

A, M = f"{API}/admin", f"{API}/manager"


def _settings(client, h):
    r = client.get(f"{A}/settings", headers=h)
    assert r.status_code == 200, r.text
    return {s["key"]: s for s in r.json()}


def test_admin_reads_and_writes_system_parameters(client):
    admin, admin_id = _user(client, "ADMIN")
    s = _settings(client, admin)
    assert {"quotation_valid_days", "deposit_deadline_days", "auto_accept_days", "photo_purge_enabled",
            "order_types_enabled", "fallback_shipping_fees"} <= set(s)
    before = _sql("select value::text from system_settings where key='max_pages_per_order'")
    bad = [("max_pages_per_order", 0), ("max_pages_per_order", "5"), ("max_pages_per_order", True),
           ("max_upload_mb", 50), ("photo_purge_enabled", "yes"), ("order_types_enabled", ["OT2_LEARNED_STYLE"]),
           ("fallback_shipping_fees", {"FLAT_BOX_A4": 1}), ("accept_reminder_days", s["auto_accept_days"]["value"])]
    for key, value in bad:
        r = client.put(f"{A}/settings/{key}", headers=admin, json={"value": value})
        assert r.status_code == 422 and _err(r) == "INVALID_SETTING", (key, value, r.text)
    assert client.put(f"{A}/settings/jwt_secret", headers=admin, json={"value": 1}).status_code == 404
    assert _sql("select value::text from system_settings where key='max_pages_per_order'") == before    # nothing written

    current = s["max_pages_per_order"]["value"]                                     # no-op write of the value in force
    r = client.put(f"{A}/settings/max_pages_per_order", headers=admin, json={"value": current, "reason": "pytest"})
    assert r.status_code == 200 and r.json()["value"] == current and r.json()["updated_by"] == admin_id
    assert _sql("""select count(*) from audit_logs where actor_id=:a and action='SETTING_UPDATE'
                   and new_value->>'key' = 'max_pages_per_order'""", a=admin_id) == 1
    for role in ("MANAGER", "STAFF"):
        assert client.get(f"{A}/settings", headers=_user(client, role)[0]).status_code == 403


def test_integrations_show_status_without_secrets(client):
    admin, admin_id = _user(client, "ADMIN")
    r = client.get(f"{A}/integrations", headers=admin)
    assert r.status_code == 200
    names = {i["name"]: i for i in r.json()}
    assert {"VNPAY", "MOMO", "PAYOS", "GHN", "SMTP", "STORAGE", "GOOGLE_LOGIN"} <= set(names)
    assert names["GHN"]["toggleable"] is True and names["VNPAY"]["toggleable"] is False
    blob = json.dumps(r.json()).lower()
    assert all(w not in blob for w in ("token", "secret", "password", "key\""))
    r = client.put(f"{A}/integrations/VNPAY", headers=admin, json={"enabled": True})
    assert r.status_code == 422 and _err(r) == "INTEGRATION_NOT_TOGGLEABLE"
    ghn = names["GHN"]["enabled"]                                                   # no-op: the flag stays as it is
    r = client.put(f"{A}/integrations/ghn", headers=admin, json={"enabled": ghn, "reason": "pytest"})
    assert r.status_code == 200 and r.json()["enabled"] is ghn
    assert _sql("select count(*) from audit_logs where actor_id=:a and action='INTEGRATION_TOGGLE'", a=admin_id) == 1


def test_admin_system_dashboard(client):
    admin, _ = _user(client, "ADMIN")
    d = client.get(f"{A}/dashboard", headers=admin).json()
    assert d["database_ms"] >= 0 and d["accounts"]["by_role"]["ADMIN"]["ACTIVE"] >= 1
    assert d["accounts"]["active_sessions"] >= 1 and d["accounts"]["new_last_7_days"] >= 1
    assert {"total", "online", "by_status"} <= set(d["robots"]) and isinstance(d["integrations"], list)
    assert d["background_jobs"]["enabled"] is False and "emails_failed_last_24h" in d["notifications"]


def test_manager_dashboard_shows_late_orders(client, cust, staff, wcat):
    mgr, _ = _user(client, "MANAGER")
    oid, q, p = _paid(client, cust, staff[0], wcat)
    yesterday = date.today() - timedelta(days=1)
    _sql("""update orders set eta = cast(:d as date) where id=:o
            and set_config('app.status_reason', 'pytest', true) is not null returning 1""", o=oid, d=yesterday.isoformat())
    d = client.get(f"{M}/dashboard", headers=mgr)
    assert d.status_code == 200, d.text
    d = d.json()
    late = {x["order_id"]: x for x in d["late_orders"]}
    assert oid in late and late[oid]["days_late"] >= 1
    assert d["orders_by_status"].get("CONFIRMED", 0) >= 1 and d["pending"]["orders_to_schedule"] >= 1
    assert {"jobs_today", "jobs_next_7_days", "low_stock", "due_in_2_days"} <= set(d)
    assert client.get(f"{M}/dashboard", headers=staff[0]).status_code == 403


def test_reports_count_the_cash_received(client, cust, staff, wcat):
    mgr, _ = _user(client, "MANAGER")
    today = date.today().isoformat()

    def received():
        r = client.get(f"{M}/reports", headers=mgr, params={"from": today, "to": today, "group": "day"})
        assert r.status_code == 200, r.text
        return r.json()
    before = received()
    oid, q, p = _paid(client, cust, staff[0], wcat)
    after = received()
    paid = int(_sql("select amount from payments where id=:p", p=p["id"]))
    assert after["revenue"]["received"] - before["revenue"]["received"] == paid
    assert after["revenue"]["net"] == after["revenue"]["received"] - after["revenue"]["refunded"]
    assert after["rates"]["submitted"] >= before["rates"]["submitted"] + 1
    assert {"output_by_type", "robots", "late_completed"} <= set(after)
    for params, code in (({"from": today, "to": "2020-01-01"}, "INVALID_PERIOD"),
                         ({"from": "2024-01-01", "to": today}, "PERIOD_TOO_LONG")):
        r = client.get(f"{M}/reports", headers=mgr, params=params)
        assert r.status_code == 422 and _err(r) == code
    assert client.get(f"{M}/reports", headers=mgr, params={"group": "year"}).status_code == 422


def test_reports_export_to_excel(client):
    mgr, _ = _user(client, "MANAGER")
    r = client.get(f"{M}/reports/export", headers=mgr, params={"group": "month"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="bao-cao_' in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Tổng quan", "Doanh thu", "Sản lượng", "Robot", "Trễ ETA"]
    assert wb["Tổng quan"]["A5"].value == "Tiền nhận (đ)"
