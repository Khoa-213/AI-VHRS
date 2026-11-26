"""FR-01 authentication use cases: register, login, refresh, password reset."""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.google_auth import GoogleIdentity
from app.integrations.mailer import Mailer
from app.models.account import Account, AccountStatus, AuthSession, RoleCode
from app.repositories.accounts import AccountRepository
from app.repositories.sessions import SessionRepository
from app.services import audit
from app.services import phone_reminders
from app.services.phone_otp import EMAIL_OTP_SECONDS, EMAIL_RESET, PhoneOtpService, email_key

log = logging.getLogger("app.auth")

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
        self.reminders: list[str] = []          # set by a sign-in: the phone reminders just created

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
        return self._open_session(acc, now, ip, user_agent)

    def _open_session(self, acc: Account, now: datetime, ip: str | None,
                      user_agent: str | None) -> tuple[Account, str, str]:
        acc.failed_login_count, acc.locked_until, acc.last_login_at = 0, None, now
        self.reminders = phone_reminders.on_sign_in(self.session, acc)       # add / verify the phone number (2026-11-26)
        sid = self.sessions.add(AuthSession(
            account_id=acc.id, expires_at=now + timedelta(days=self.cfg.refresh_token_ttl_days),
            ip_address=ip, user_agent=(user_agent or "")[:255] or None)).id
        return acc, *self._issue_pair(acc, sid)

    # Google sign-in. No schema change: an account is matched by its (Google-verified) e-mail. Customers only:
    # internal roles are created by the Admin (BR-01) and sign in with their password.
    def login_google(self, identity: GoogleIdentity, *, ip: str | None = None,
                     user_agent: str | None = None) -> tuple[Account, str, str]:
        now = _now()
        acc = self.repo.get_by_email(identity.email)
        if acc is None:
            role = self.repo.role_by_code(RoleCode.CUSTOMER.value)
            assert role is not None, "roles seed missing"
            name = (identity.name or identity.email.split("@")[0]).strip()[:150] or "Khách hàng"
            acc = self.repo.add(Account(role_id=role.id, email=identity.email,
                                        password_hash=security.hash_password(secrets.token_urlsafe(32)),
                                        full_name=name))     # unusable random password; "forgot password" can set one
            audit.record(self.session, actor_id=acc.id, action="ACCOUNT_REGISTER_GOOGLE", entity_type="account",
                         entity_id=acc.id, ip=ip)
        elif acc.role.code != RoleCode.CUSTOMER.value:
            raise AppError(403, "GOOGLE_NOT_ALLOWED", "Tài khoản nội bộ đăng nhập bằng email và mật khẩu.")
        if acc.status != AccountStatus.ACTIVE:
            raise AppError(403, "ACCOUNT_DISABLED", "Tài khoản đã bị khoá hoặc vô hiệu hoá.")
        if acc.locked_until and acc.locked_until > now:
            raise AppError(423, "ACCOUNT_TEMP_LOCKED", "Tài khoản tạm khoá do nhập sai nhiều lần. Vui lòng thử lại sau.")
        return self._open_session(acc, now, ip, user_agent)

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
        link = f"{web_url(self.cfg)}/reset-password"         # the page where the code is typed; no token (2026-11-26)
        otp = PhoneOtpService(self.session, None)
        try:
            with self.session.begin_nested():
                otp._issue(acc.id, email_key(acc.id), EMAIL_RESET.replace("{link}", link),
                           deliver=lambda body: self.mailer.send(acc.email, "Mã đặt lại mật khẩu AI-VHRS", body),
                           ttl_seconds=EMAIL_OTP_SECONDS)
        except AppError as exc:                    # resend wait / daily limit: same answer, nothing sent
            log.info("password reset mail not sent: %s", exc.code)

    def confirm_password_reset_code(self, email: str, code: str, new_password: str) -> None:
        """The 6-digit code of the reset e-mail (2026-11-26). Wrong guesses are counted (5, then the code is burned)."""
        acc = self.repo.get_by_email(email)
        if acc is None or acc.status != AccountStatus.ACTIVE:
            raise AppError(400, "OTP_INVALID", "Mã OTP không đúng hoặc đã hết hạn.")
        security.validate_password_strength(new_password)          # before the code is used up
        PhoneOtpService(self.session, None)._check(acc.id, email_key(acc.id), code)
        self._set_password(acc, new_password)

    def confirm_password_reset_phone(self, phone: str, code: str, new_password: str, *, ip: str | None = None) -> None:
        """The 6-digit code sent by SMS to the account's verified number (UC-54; no token since 2026-11-26)."""
        security.validate_password_strength(new_password)          # before the code is used up
        acc = PhoneOtpService(self.session, None, ip).confirm_reset(phone, code)
        self._set_password(acc, new_password)

    def _set_password(self, acc: Account, new_password: str) -> None:
        acc.password_hash = security.hash_password(new_password)
        acc.failed_login_count, acc.locked_until = 0, None
        self.sessions.revoke_all(acc.id)  # a reset must sign out every device
        self.mailer.send(acc.email, "Mật khẩu AI-VHRS đã được đổi",
                         "Mật khẩu tài khoản của bạn vừa được đặt lại và mọi thiết bị đã bị đăng xuất. "
                         "Nếu không phải bạn thực hiện, hãy liên hệ xưởng ngay.")

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


def web_url(cfg) -> str:
    """Root of the web app for links in e-mails: PUBLIC_WEB_URL, else the origin of PAYMENT_RETURN_URL."""
    from urllib.parse import urlsplit
    if cfg.public_web_url:
        return cfg.public_web_url.rstrip("/")
    u = urlsplit(cfg.payment_return_url)
    return f"{u.scheme}://{u.netloc}"
