"""FR-01 authentication use cases: register, login, refresh, password reset."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.mailer import Mailer
from app.models.account import Account, AccountStatus, AuthSession, RoleCode
from app.repositories.accounts import AccountRepository
from app.repositories.sessions import SessionRepository

_BAD_CREDENTIALS = AppError(401, "INVALID_CREDENTIALS", "Email hoặc mật khẩu không đúng.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sid(payload: dict) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload.get("sid")))
    except ValueError as exc:
        raise AppError(401, "TOKEN_INVALID", "Token không hợp lệ.") from exc


class AuthService:
    def __init__(self, session: Session, mailer: Mailer):
        self.session = session
        self.repo = AccountRepository(session)
        self.sessions = SessionRepository(session)
        self.mailer = mailer
        self.cfg = get_settings()

    # UC-05 / BR-01: customers self-register; internal roles are created by Admin.
    def register_customer(self, *, email: str, password: str, full_name: str, phone: str | None) -> Account:
        security.validate_password_strength(password)
        if self.repo.get_by_email(email):
            raise AppError(409, "EMAIL_TAKEN", "Email đã được đăng ký.")
        role = self.repo.role_by_code(RoleCode.CUSTOMER.value)
        assert role is not None, "roles seed missing"
        return self.repo.add(Account(
            role_id=role.id, email=email.strip(), password_hash=security.hash_password(password),
            full_name=full_name.strip(), phone=phone))

    # UC-01
    def login(self, email: str, password: str, *, ip: str | None = None,
              user_agent: str | None = None) -> tuple[Account, str, str]:
        acc = self.repo.get_by_email(email)
        if acc is None:
            security.verify_password(password, security.hash_password("x"))  # equalise timing
            raise _BAD_CREDENTIALS
        now = _now()
        if acc.status != AccountStatus.ACTIVE:
            raise AppError(403, "ACCOUNT_DISABLED", "Tài khoản đã bị khoá hoặc vô hiệu hoá.")
        if acc.locked_until and acc.locked_until > now:
            raise AppError(423, "ACCOUNT_TEMP_LOCKED", "Tài khoản tạm khoá do nhập sai nhiều lần. Vui lòng thử lại sau.")
        if not security.verify_password(password, acc.password_hash):
            acc.failed_login_count += 1
            if acc.failed_login_count >= self.cfg.max_failed_logins:
                acc.locked_until = now + timedelta(minutes=self.cfg.lockout_minutes)
                acc.failed_login_count = 0
            self.session.commit()  # persist the counter even though we answer 401
            raise _BAD_CREDENTIALS
        acc.failed_login_count, acc.locked_until, acc.last_login_at = 0, None, now
        sid = self.sessions.add(AuthSession(
            account_id=acc.id, expires_at=now + timedelta(days=self.cfg.refresh_token_ttl_days),
            ip_address=ip, user_agent=(user_agent or "")[:255] or None)).id
        return acc, *self._issue_pair(acc, sid)

    def refresh(self, refresh_token: str) -> tuple[Account, str, str]:
        payload = security.decode_token(refresh_token, security.REFRESH)
        acc = self.repo.get(int(payload["sub"]))
        sid = _sid(payload)
        if acc is None or acc.status != AccountStatus.ACTIVE or self.sessions.get_active(sid, acc.id) is None:
            raise AppError(401, "TOKEN_INVALID", "Token không hợp lệ.")
        return acc, *self._issue_pair(acc, sid)

    # UC-03: always answers the same way so emails cannot be enumerated.
    def request_password_reset(self, email: str) -> None:
        acc = self.repo.get_by_email(email)
        if acc is None or acc.status != AccountStatus.ACTIVE:
            return
        token = security.create_token(
            acc.id, security.RESET, timedelta(minutes=self.cfg.reset_token_ttl_min),
            fp=security.password_fingerprint(acc.password_hash))
        self.mailer.send(acc.email, "Đặt lại mật khẩu AI-VHRS",
                         f"Dùng mã sau để đặt lại mật khẩu (hết hạn sau {self.cfg.reset_token_ttl_min} phút): {token}")

    def confirm_password_reset(self, token: str, new_password: str) -> None:
        payload = security.decode_token(token, security.RESET)
        acc = self.repo.get(int(payload["sub"]))
        if acc is None or payload.get("fp") != security.password_fingerprint(acc.password_hash):
            raise AppError(401, "TOKEN_INVALID", "Liên kết không hợp lệ hoặc đã được sử dụng.")
        security.validate_password_strength(new_password)
        acc.password_hash = security.hash_password(new_password)
        acc.failed_login_count, acc.locked_until = 0, None
        self.sessions.revoke_all(acc.id)  # a reset must sign out every device

    def logout(self, session_id: uuid.UUID) -> None:
        self.sessions.revoke(session_id)

    def _issue_pair(self, acc: Account, sid: uuid.UUID) -> tuple[str, str]:
        role = acc.role.code
        return (
            security.create_token(acc.id, security.ACCESS, timedelta(minutes=self.cfg.access_token_ttl_min),
                                  role=role, sid=str(sid)),
            security.create_token(acc.id, security.REFRESH, timedelta(days=self.cfg.refresh_token_ttl_days),
                                  sid=str(sid)),
        )
