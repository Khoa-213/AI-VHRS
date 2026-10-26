"""Profile (FR-02) and account administration (FR-51, BR-01)."""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AppError
from app.integrations.locations import normalize_address
from app.models.account import Account, AccountStatus, RoleCode
from app.repositories.accounts import AccountRepository
from app.services import audit

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

    def update(self, account_id: int, *, status: AccountStatus | None, role_code: str | None,
               reason: str | None) -> Account:
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
        if new:
            audit.record(self.session, actor_id=self.actor.id, action=action, entity_type="account",
                         entity_id=acc.id, old=old, new=new, reason=reason, ip=self.ip)
        return acc


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
