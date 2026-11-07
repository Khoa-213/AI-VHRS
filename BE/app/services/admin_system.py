"""Admin (Phase 5b): system parameters (UC-50), integrations (UC-49), system dashboard (UC-52). FR-51: every change is audited.

Only keys the code actually reads can be edited, each with its own check (a typo'd or out-of-range value would otherwise reach
the business rules). Secrets (gateway keys, SMTP password, GHN token) are NEVER stored in the database nor shown: they stay in
the server's environment; the integrations view only tells whether each one is configured and in which mode.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.account import Account, AuthSession, Role
from app.models.notification import Notification, NotificationChannel
from app.models.ops import Robot
from app.models.order import OrderType
from app.services import audit


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SettingError(ValueError):
    pass


def _int(lo: int, hi: int) -> Callable[[Any], int]:
    def check(v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int):
            raise SettingError("phải là số nguyên")
        if not lo <= v <= hi:
            raise SettingError(f"phải từ {lo} đến {hi}")
        return v
    return check


def _bool(v: Any) -> bool:
    if not isinstance(v, bool):
        raise SettingError("phải là true hoặc false")
    return v


def _order_types(v: Any) -> list[str]:
    allowed = {OrderType.OT1_COPY_RESTORE.value, OrderType.OT3_TEMPLATE.value}       # OT-2 stays locked (no AI for it)
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise SettingError("phải là danh sách mã loại đơn")
    bad = [x for x in v if x not in allowed]
    if bad:
        raise SettingError(f"chỉ được {sorted(allowed)}; không nhận {bad}")
    return sorted(set(v))


def _fees(v: Any) -> dict[str, int]:
    keys = {"FLAT_BOX_A5", "FLAT_BOX_A4", "TUBE"}
    if not isinstance(v, dict) or set(v) != keys:
        raise SettingError(f"phải có đủ và chỉ các khoá {sorted(keys)}")
    return {k: _int(0, 1_000_000)(x) for k, x in v.items()}


@dataclass(frozen=True)
class Spec:
    check: Callable[[Any], Any]
    default: Any
    label: str


SPECS: dict[str, Spec] = {
    "quotation_valid_days": Spec(_int(1, 60), 7, "Hiệu lực báo giá (ngày, BR-08)"),
    "deposit_deadline_days": Spec(_int(1, 30), 3, "Hạn đặt cọc sau khi duyệt báo giá (ngày)"),
    "accept_reminder_days": Spec(_int(1, 30), 3, "Nhắc nghiệm thu sau (ngày)"),
    "auto_accept_days": Spec(_int(2, 60), 7, "Tự nghiệm thu sau (ngày, FR-28)"),
    "eta_cancel_threshold_days": Spec(_int(1, 60), 7, "Ngưỡng dời ETA cho huỷ hoàn 100% (ngày, BR-16)"),
    "max_upload_mb": Spec(_int(1, 20), 20, "Dung lượng tối đa mỗi file (MB)"),
    "max_pages_per_order": Spec(_int(1, 50), 10, "Số trang tối đa mỗi đơn"),
    "order_types_enabled": Spec(_order_types, ["OT1_COPY_RESTORE", "OT3_TEMPLATE"], "Loại đơn đang nhận (MSG03)"),
    "fallback_shipping_fees": Spec(_fees, {"FLAT_BOX_A5": 25000, "FLAT_BOX_A4": 30000, "TUBE": 45000},
                                   "Phí ship dự phòng theo kiện (đ)"),
    "image_retention_days": Spec(_int(30, 3650), 90, "Giữ ảnh khách sau khi đơn xong (ngày, BR-23)"),
    "photo_purge_enabled": Spec(_bool, False, "Bật xoá thật ảnh khách quá hạn (BR-23)"),
}
TOGGLEABLE_INTEGRATIONS = ("GHN",)        # the only flag of integrations_enabled the code reads


class AdminSystemService:
    def __init__(self, session: Session, admin: Account, ip: str | None = None):
        self.session, self.admin, self.ip = session, admin, ip

    # ---- UC-50 ----
    def _rows(self) -> dict[str, dict[str, Any]]:
        rows = self.session.execute(text("select key, value, updated_by, updated_at from system_settings"))
        return {r.key: {"value": r.value, "updated_by": r.updated_by, "updated_at": r.updated_at} for r in rows}

    def settings(self) -> list[dict[str, Any]]:
        rows = self._rows()
        out = []
        for key, spec in SPECS.items():
            row = rows.get(key)
            out.append({"key": key, "label": spec.label, "value": row["value"] if row else spec.default,
                        "is_default": row is None, "updated_by": row["updated_by"] if row else None,
                        "updated_at": row["updated_at"] if row else None})
        return out

    def _current(self, key: str) -> Any:
        row = self._rows().get(key)
        return row["value"] if row else SPECS[key].default

    def set_setting(self, key: str, value: Any, reason: str | None) -> dict[str, Any]:
        spec = SPECS.get(key)
        if spec is None:
            raise AppError(404, "SETTING_NOT_EDITABLE", "Tham số không tồn tại hoặc không được sửa qua API.")
        try:
            value = spec.check(value)
        except SettingError as exc:
            raise AppError(422, "INVALID_SETTING", f"{spec.label}: {exc}.", {"key": key}) from exc
        if key == "accept_reminder_days" and value >= self._current("auto_accept_days"):
            raise AppError(422, "INVALID_SETTING", "Ngày nhắc nghiệm thu phải nhỏ hơn ngày tự nghiệm thu.", {"key": key})
        if key == "auto_accept_days" and value <= self._current("accept_reminder_days"):
            raise AppError(422, "INVALID_SETTING", "Ngày tự nghiệm thu phải lớn hơn ngày nhắc nghiệm thu.", {"key": key})
        old = self._rows().get(key)
        self._write(key, value)
        audit.record(self.session, actor_id=self.admin.id, action="SETTING_UPDATE", entity_type="system_setting",
                     old={"key": key, "value": old["value"] if old else None}, new={"key": key, "value": value},
                     reason=reason, ip=self.ip)
        return next(s for s in self.settings() if s["key"] == key)

    def _write(self, key: str, value: Any) -> None:
        self.session.execute(text("""
            insert into system_settings (key, value, description, updated_by, updated_at)
            values (:k, cast(:v as jsonb), :d, :a, now())
            on conflict (key) do update set value = excluded.value, updated_by = excluded.updated_by, updated_at = now()"""),
            {"k": key, "v": _json(value), "d": SPECS[key].label if key in SPECS else None, "a": self.admin.id})
        self.session.flush()

    # ---- UC-49 ----
    def integrations(self) -> list[dict[str, Any]]:
        from app.integrations import payment_gateway as pg
        s = get_settings()
        flags = self._rows().get("integrations_enabled", {}).get("value") or {}
        out = [{"name": g["gateway"], "kind": "PAYMENT", "mode": g["mode"], "configured": g["enabled"], "toggleable": False,
                "enabled": g["enabled"]} for g in pg.gateway_status()]
        out.append({"name": "GHN", "kind": "CARRIER", "mode": s.carrier_mode.upper(),
                    "configured": bool(s.ghn_token and s.ghn_shop_id) or s.carrier_mode == "mock", "toggleable": True,
                    "enabled": bool(flags.get("GHN")) if isinstance(flags, dict) else False})
        out.append({"name": "SMTP", "kind": "EMAIL", "mode": "LIVE" if s.smtp_host else "CONSOLE",
                    "configured": bool(s.smtp_host and (s.smtp_from or s.smtp_user)), "toggleable": False,
                    "enabled": bool(s.smtp_host)})
        out.append({"name": "STORAGE", "kind": "STORAGE", "mode": "SUPABASE",
                    "configured": bool(s.supabase_url and s.supabase_service_key), "toggleable": False,
                    "enabled": bool(s.supabase_url and s.supabase_service_key)})
        out.append({"name": "GOOGLE_LOGIN", "kind": "AUTH", "mode": "LIVE", "configured": bool(s.google_client_id),
                    "toggleable": False, "enabled": bool(s.google_client_id)})
        return out

    def set_integration(self, name: str, enabled: bool, reason: str | None) -> dict[str, Any]:
        name = name.upper()
        if name not in TOGGLEABLE_INTEGRATIONS:
            raise AppError(422, "INTEGRATION_NOT_TOGGLEABLE",
                           "Tích hợp này bật/tắt bằng cấu hình server (khoá, chế độ), không bằng API.", {"name": name})
        row = self.session.execute(text("select value from system_settings where key='integrations_enabled' for update")).first()
        old = dict(row.value) if row and isinstance(row.value, dict) else {}
        new = {**old, name: bool(enabled)}
        self._write("integrations_enabled", new)
        audit.record(self.session, actor_id=self.admin.id, action="INTEGRATION_TOGGLE", entity_type="system_setting",
                     old={"key": "integrations_enabled", name: old.get(name)}, new={"key": "integrations_enabled", name: enabled},
                     reason=reason, ip=self.ip)
        return next(i for i in self.integrations() if i["name"] == name)

    # ---- UC-52 ----
    def dashboard(self) -> dict[str, Any]:
        from app.services import background_jobs
        from app.services.robot_link import hub
        t0 = time.perf_counter()
        self.session.execute(text("select 1"))
        db_ms = round((time.perf_counter() - t0) * 1000, 1)
        now = _now()
        by_role = self.session.execute(select(Role.code, Account.status, func.count()).join(Role, Role.id == Account.role_id)
                                       .group_by(Role.code, Account.status)).all()
        accounts: dict[str, dict[str, int]] = {}
        for role, status, n in by_role:
            accounts.setdefault(role, {})[getattr(status, "value", str(status))] = n
        new_7d = self.session.scalar(select(func.count()).select_from(Account).where(Account.created_at > now - timedelta(days=7)))
        sessions = self.session.scalar(select(func.count()).select_from(AuthSession).where(
            AuthSession.revoked_at.is_(None), AuthSession.expires_at > now))
        robots = self.session.execute(select(Robot.id, Robot.status)).all()
        failed_mail = self.session.scalar(select(func.count()).select_from(Notification).where(
            Notification.channel == NotificationChannel.EMAIL, Notification.sent_at.is_(None),
            Notification.created_at < now - timedelta(minutes=2), Notification.created_at > now - timedelta(days=1)))
        s = get_settings()
        return {
            "generated_at": now, "database_ms": db_ms,
            "accounts": {"by_role": accounts, "new_last_7_days": new_7d or 0, "active_sessions": sessions or 0},
            "robots": {"total": len(robots), "online": sum(1 for r in robots if hub.online(r.id)),
                       "by_status": _count(getattr(r.status, "value", str(r.status)) for r in robots)},
            "integrations": self.integrations(),
            "background_jobs": {"enabled": s.background_jobs_enabled, "interval_seconds": s.background_jobs_interval_seconds,
                                "last_run": background_jobs.last_run(self.session)},
            "notifications": {"emails_failed_last_24h": failed_mail or 0},
        }


def _count(items) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in items:
        out[x] = out.get(x, 0) + 1
    return out


def _json(v: Any) -> str:
    import json
    return json.dumps(v, ensure_ascii=False)
