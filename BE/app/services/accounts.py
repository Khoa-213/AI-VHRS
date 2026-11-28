"""Profile (FR-02) and account administration (FR-51, BR-01)."""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AppError
from app.integrations.locations import normalize_address
from app.models.account import Account, AccountStatus, RoleCode
from app.repositories.accounts import AccountRepository
from app.services import audit, phone_reminders

# BR-01: Admin creates internal accounts; Admin itself is system-provisioned.
INTERNAL_ROLES = {RoleCode.STAFF.value, RoleCode.TECHNICAL_STAFF.value, RoleCode.MANAGER.value}


class ProfileService:
    def __init__(self, session: Session):
        self.session = session

    def update(self, acc: Account, *, full_name: str | None, phone: str | None,
               addresses: list[dict[str, Any]] | None, phone_given: bool) -> Account:
        if full_name is not None:
            acc.full_name = full_name.strip()
        if phone_given and phone != acc.phone:
            acc.phone, acc.phone_verified_at = phone, None  # a new number must be verified again (FR-53)
            phone_reminders.on_phone_changed(self.session, acc)          # bell: "verify this number" (2026-11-26)
        if addresses is not None:
            acc.addresses = [normalize_address(a) for a in addresses]     # codes checked, names from the catalogue
        return acc

    def change_password(self, acc: Account, current: str, new: str) -> None:
        if not security.verify_password(current, acc.password_hash):
            raise AppError(400, "WRONG_PASSWORD", "Mật khẩu hiện tại không đúng.")
        security.validate_password_strength(new)
        acc.password_hash = security.hash_password(new)


class AccountAdminService:
    def __init__(self, session: Session, actor: Account, ip: str | None = None):
        self.session, self.actor, self.ip = session, actor, ip
        self.repo = AccountRepository(session)

    def create_internal(self, *, email: str, password: str, full_name: str, phone: str | None,
                        role_code: str) -> Account:
        if role_code not in INTERNAL_ROLES:
            raise AppError(422, "ROLE_NOT_ALLOWED", "Chỉ tạo được tài khoản Staff, Technical Staff hoặc Manager.")
        security.validate_password_strength(password)
        if self.repo.get_by_email(email):
            raise AppError(409, "EMAIL_TAKEN", "Email đã được đăng ký.")
        role = self.repo.role_by_code(role_code)
        assert role is not None
        acc = self.repo.add(Account(
            role_id=role.id, email=email.strip(), password_hash=security.hash_password(password),
            full_name=full_name.strip(), phone=phone, created_by=self.actor.id))
        audit.record(self.session, actor_id=self.actor.id, action="ACCOUNT_CREATE", entity_type="account",
                     entity_id=acc.id, new={"email": acc.email, "role": role_code}, ip=self.ip)
        return acc

    def open_work(self, account_id: int) -> dict[str, list[int]]:
        """What this account still holds (D05): orders in its hands as Staff, production jobs and robots as Technical Staff."""
        from app.models.ops import ACTIVE_JOB_STATUSES, ProductionJob, TechnicianRobot
        from app.models.order import Order, OrderStatus
        closed = (OrderStatus.DRAFT, OrderStatus.REJECTED, OrderStatus.CANCELLED, OrderStatus.COMPLETED)
        s = self.session
        work = {
            "orders": list(s.scalars(select(Order.id).where(Order.assigned_staff_id == account_id,
                                                           Order.order_status.not_in(closed)).order_by(Order.id))),
            "jobs": list(s.scalars(select(ProductionJob.id).where(ProductionJob.technician_id == account_id,
                                                                  ProductionJob.status.in_(ACTIVE_JOB_STATUSES)).order_by(ProductionJob.id))),
            "robots": list(s.scalars(select(TechnicianRobot.robot_id).where(TechnicianRobot.technician_id == account_id)
                                     .order_by(TechnicianRobot.robot_id))),
        }
        return {k: v for k, v in work.items() if v}

    def _revoke_agent_keys(self, account_id: int) -> int:
        """The workstation keys a technician's app holds stop with the account (TP-06): they act AS that technician."""
        from app.models.ops import RobotAgent
        from app.services.robot_link import hub
        n = 0
        for key in self.session.scalars(select(RobotAgent).where(RobotAgent.account_id == account_id, RobotAgent.revoked_at.is_(None))):
            key.revoked_at, n = utcnow(), n + 1
            hub.forget_robot_keys(key.robot_id)
        return n

    def update(self, account_id: int, *, status: AccountStatus | None, role_code: str | None,
               reason: str | None, force: bool = False) -> Account:
        acc = self.repo.get(account_id)
        if acc is None:
            raise AppError(404, "ACCOUNT_NOT_FOUND", "Không tìm thấy tài khoản.")
        if acc.role.code == RoleCode.ADMIN.value:
            raise AppError(403, "ADMIN_PROTECTED", "Không thể thay đổi tài khoản Admin.")
        if acc.id == self.actor.id:
            raise AppError(403, "SELF_CHANGE", "Không thể tự thay đổi tài khoản của chính mình.")

        old: dict[str, Any] = {}
        new: dict[str, Any] = {}
        action = "ACCOUNT_UPDATE"
        # D05 (audit 2026-11-27): taking an account out of its job must not strand the work it holds. Until now locking a
        # Staff left their orders, refunds and ETA changes with nobody (only the assigned Staff may do those), and a locked
        # technician's started jobs could not be taken over by anyone.
        leaving = (status is not None and status != AccountStatus.ACTIVE and acc.status == AccountStatus.ACTIVE) or (
            role_code is not None and role_code != acc.role.code)
        left_behind: dict[str, list[int]] = {}
        if leaving:
            left_behind = self.open_work(acc.id)
            if left_behind and not force:
                raise AppError(409, "ACCOUNT_HAS_OPEN_WORK",
                               "Tài khoản này còn đang giữ việc. Quản lý phân công lại đơn / job / robot trước, hoặc gửi "
                               "force = true kèm lý do trong trường hợp khẩn cấp.", left_behind)
            if left_behind and not (reason or "").strip():
                raise AppError(422, "REASON_REQUIRED", "Khoá hoặc đổi vai trò khi còn việc đang giữ cần ghi rõ lý do.")
        if role_code is not None and role_code != acc.role.code:
            if role_code not in INTERNAL_ROLES or acc.role.code not in INTERNAL_ROLES:
                raise AppError(422, "ROLE_NOT_ALLOWED", "Chỉ đổi vai trò giữa Staff, Technical Staff và Manager.")
            role = self.repo.role_by_code(role_code)
            assert role is not None
            old["role"], new["role"], action = acc.role.code, role_code, "ROLE_CHANGE"
            acc.role_id, acc.role = role.id, role
        if status is not None and status != acc.status:
            old["status"], new["status"] = acc.status.value, status.value
            action = "ACCOUNT_LOCK" if status != AccountStatus.ACTIVE else "ACCOUNT_UNLOCK"
            acc.status = status
            if status == AccountStatus.ACTIVE:
                acc.failed_login_count, acc.locked_until = 0, None
        if new and leaving:
            revoked = self._revoke_agent_keys(acc.id)
            if revoked:
                new["agent_keys_revoked"] = revoked
            if left_behind:
                new["forced_with_open_work"] = left_behind       # what the Manager now has to reassign
        if new:
            audit.record(self.session, actor_id=self.actor.id, action=action, entity_type="account",
                         entity_id=acc.id, old=old, new=new, reason=reason, ip=self.ip)
        return acc


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
