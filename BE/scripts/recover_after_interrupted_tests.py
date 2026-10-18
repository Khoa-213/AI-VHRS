"""Put the shared (Supabase) database back after a pytest run was cut short (codespace stopped, process killed).

An interrupted run skips the suite's end-of-session cleanup, which leaves 'pytest_*' rows behind and, worse, leaves the
real setting `order_types_enabled` deleted (the suite removes it while running so every order type can be tested), so
customers could order the disabled R&D type. This script restores that setting and removes the 'pytest_' leftovers with
the suite's own `_cleanup` (real orders that use a test catalog row are protected there). Idempotent and safe to re-run.

Run from BE/ with no pytest session active:   .venv/bin/python scripts/recover_after_interrupted_tests.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.db.session import get_engine  # noqa: E402
from tests.conftest import _cleanup  # noqa: E402

DEFAULT_ORDER_TYPES = ('["OT1_COPY_RESTORE", "OT3_TEMPLATE"]', "LI-10: loại đơn đang nhận.")
CHECKS = {
    "tài khoản pytest_": "select count(*) from accounts where email like 'pytest\\_%'",
    "danh mục/robot pytest_": ("select (select count(*) from pen_types where code like 'pytest\\_%')"
                               "+(select count(*) from paper_types where code like 'pytest\\_%')"
                               "+(select count(*) from templates where code like 'pytest\\_%')"
                               "+(select count(*) from robots where code like 'pytest\\_%')"),
    "bảng giá đang active (phải = 1)": "select count(*) from pricing_configs where is_active",
    "order_types_enabled": "select value::text from system_settings where key='order_types_enabled'",
}


def main() -> None:
    with get_engine().begin() as c:
        had = c.execute(text("select 1 from system_settings where key='order_types_enabled'")).scalar()
        c.execute(text("insert into system_settings (key, value, description) values "
                       "('order_types_enabled', cast(:v as jsonb), :d) on conflict (key) do nothing"),
                  {"v": DEFAULT_ORDER_TYPES[0], "d": DEFAULT_ORDER_TYPES[1]})
    print("order_types_enabled:", "đã có sẵn" if had else "ĐÃ KHÔI PHỤC về mặc định dự án")
    _cleanup()
    with get_engine().connect() as c:
        for label, sql in CHECKS.items():
            print(f"{label}: {c.execute(text(sql)).scalar()}")


if __name__ == "__main__":
    main()
