"""FR-53 / UC-54 (Phase 5e): verify the account's phone number by SMS OTP, and recover the account with that number.

Two flows on the same `phone_otps` table:
* verification (signed in): `send_verification` -> `confirm_verification` sets `accounts.phone_verified_at`. One number can be
  verified for one account only (unique index `ux_accounts_verified_phone`, answered 409 `PHONE_TAKEN`).
* recovery (signed out): `request_reset` sends a code only to a VERIFIED number of an ACTIVE account and always answers the
  same way, so numbers cannot be enumerated; `verify_reset` turns a right code into the same reset token the e-mail flow
  uses, and the password is set with `POST /auth/password-reset/confirm` (strength check, every device signed out,
  token single use).

Rules (assumptions: the SRS text of FR-53 is not in the repo; approved with the 5e plan on 2026-11-11), all in settings:
6 digits, only an HMAC stored, 5 minutes, 5 wrong guesses then burned, a new code closes the older ones, 60 s between two
codes and at most 5 codes per number in 24 hours. Numbers are stored as 0xxxxxxxxx; +84xxxxxxxxx is accepted.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.sms import SmsSender, mask
from app.models.account import Account, AccountStatus, PhoneOtp
from app.services import audit

log = logging.getLogger("app.otp")
CODE_DIGITS = 6
_BAD_CODE = "Mã OTP không đúng hoặc đã hết hạn."
_TAKEN = "Số điện thoại này đã được xác minh cho một tài khoản khác."
VERIFY_SMS = ("AI-VHRS: ma xac minh so dien thoai cua ban la {code}, hieu luc {minutes} phut. "
              "Khong chia se ma nay cho bat ky ai.")
RESET_SMS = ("AI-VHRS: ma dat lai mat khau cua ban la {code}, hieu luc {minutes} phut. "
             "Neu ban khong yeu cau, hay bo qua tin nhan nay.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_phone(phone: str) -> str:
    p = phone.strip().replace(" ", "")
    return "0" + p[3:] if p.startswith("+84") else p


def phone_variants(phone: str) -> tuple[str, str]:
    n = normalize_phone(phone)
    return n, "+84" + n[1:]


def _digest(account_id: int, phone: str, code: str) -> str:
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, f"otp:{account_id}:{phone}:{code}".encode(), hashlib.sha256).hexdigest()


class PhoneOtpService:
    def __init__(self, session: Session, sms: SmsSender, ip: str | None = None):
        self.session, self.sms, self.ip = session, sms, ip
        self.cfg = get_settings()

    # ------------------------------------------------------------------ shared
    def _lock_account(self, account_id: int) -> None:
        self.session.execute(select(Account.id).where(Account.id == account_id).with_for_update())

    def verified_owner(self, phone: str) -> Account | None:
        return self.session.execute(select(Account).where(
            Account.phone.in_(phone_variants(phone)), Account.phone_verified_at.is_not(None))).scalars().first()

    def _issue(self, account_id: int, phone: str, text: str) -> dict:
        """Create and send a code. The account row is locked first so two clicks cannot both pass the resend wait."""
        self._lock_account(account_id)
        now = _now()
        recent = self.session.execute(select(PhoneOtp.created_at).where(
            PhoneOtp.phone == phone, PhoneOtp.created_at > now - timedelta(days=1))
            .order_by(PhoneOtp.created_at.desc())).scalars().all()
        if recent and (now - recent[0]).total_seconds() < self.cfg.otp_resend_seconds:
            wait = max(1, self.cfg.otp_resend_seconds - int((now - recent[0]).total_seconds()))
            raise AppError(429, "OTP_RESEND_TOO_SOON", f"Vui lòng chờ {wait} giây rồi gửi lại mã.", {"retry_after": wait})
        if len(recent) >= self.cfg.otp_daily_limit:
            raise AppError(429, "OTP_DAILY_LIMIT", "Số điện thoại này đã nhận quá nhiều mã trong 24 giờ. Vui lòng thử lại sau.",
                           {"limit": self.cfg.otp_daily_limit})
        self.session.execute(update(PhoneOtp).where(PhoneOtp.account_id == account_id, PhoneOtp.used_at.is_(None))
                             .values(used_at=now))                     # a new code closes the older ones
        code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
        self.session.add(PhoneOtp(account_id=account_id, phone=phone, otp_hash=_digest(account_id, phone, code),
                                  expires_at=now + timedelta(seconds=self.cfg.otp_ttl_seconds), attempt_count=0,
                                  max_attempts=self.cfg.otp_max_attempts, created_at=now))
        self.session.flush()
        self.sms.send(phone, text.format(code=code, minutes=max(1, self.cfg.otp_ttl_seconds // 60)))
        return {"phone_masked": mask(phone), "expires_in": self.cfg.otp_ttl_seconds,
                "resend_after": self.cfg.otp_resend_seconds, "mode": self.sms.mode}

    def _check(self, account_id: int, phone: str, code: str) -> None:
        """Consume the newest open code of (account, number). A wrong guess is counted and COMMITTED before answering."""
        now = _now()
        row = self.session.execute(select(PhoneOtp).where(
            PhoneOtp.account_id == account_id, PhoneOtp.phone == phone, PhoneOtp.used_at.is_(None))
            .order_by(PhoneOtp.created_at.desc()).limit(1).with_for_update()).scalar_one_or_none()
        if row is None:
            raise AppError(400, "OTP_INVALID", _BAD_CODE)
        if row.expires_at <= now:
            raise AppError(400, "OTP_EXPIRED", "Mã OTP đã hết hạn. Vui lòng gửi lại mã mới.")
        if not hmac.compare_digest(row.otp_hash, _digest(account_id, phone, code)):
            row.attempt_count += 1
            left = row.max_attempts - row.attempt_count
            if left <= 0:
                row.used_at = now                                       # burned
            self.session.commit()                                      # keep the count even though we answer 400
            if left <= 0:
                raise AppError(400, "OTP_TOO_MANY_ATTEMPTS", "Nhập sai quá số lần cho phép. Vui lòng gửi lại mã mới.")
            raise AppError(400, "OTP_INVALID", _BAD_CODE, {"attempts_left": left})
        row.used_at = now

    # ------------------------------------------------------------------ verification (signed in)
    def _own_phone(self, acc: Account) -> str:
        if not acc.phone:
            raise AppError(422, "PHONE_MISSING", "Tài khoản chưa có số điện thoại. Hãy cập nhật hồ sơ trước.")
        if acc.phone_verified_at is not None:
            raise AppError(409, "PHONE_ALREADY_VERIFIED", "Số điện thoại đã được xác minh.")
        phone = normalize_phone(acc.phone)
        other = self.verified_owner(phone)
        if other is not None and other.id != acc.id:
            raise AppError(409, "PHONE_TAKEN", _TAKEN)
        return phone

    def send_verification(self, acc: Account) -> dict:
        return self._issue(acc.id, self._own_phone(acc), VERIFY_SMS)

    def confirm_verification(self, acc: Account, code: str) -> Account:
        phone = self._own_phone(acc)
        self._check(acc.id, phone, code)
        try:
            with self.session.begin_nested():
                acc.phone, acc.phone_verified_at = phone, _now()
                self.session.flush()
        except IntegrityError as exc:                                  # another account verified it a moment ago
            raise AppError(409, "PHONE_TAKEN", _TAKEN) from exc
        audit.record(self.session, actor_id=acc.id, action="PHONE_VERIFY", entity_type="account", entity_id=acc.id,
                     new={"phone": mask(phone)}, ip=self.ip)
        return acc

    # ------------------------------------------------------------------ recovery (signed out)
    def _reset_owner(self, phone: str) -> Account | None:
        acc = self.verified_owner(phone)
        return acc if acc is not None and acc.status == AccountStatus.ACTIVE else None

    def request_reset(self, phone: str) -> None:
        """Same answer whatever happens: unknown or unverified number, resend wait, daily limit, SMS failure."""
        acc = self._reset_owner(phone)
        if acc is None:
            return
        try:
            with self.session.begin_nested():
                self._issue(acc.id, normalize_phone(acc.phone or phone), RESET_SMS)
        except AppError as exc:
            log.info("phone reset not sent to %s: %s", mask(phone), exc.code)

    def verify_reset(self, phone: str, code: str) -> tuple[str, int]:
        acc = self._reset_owner(phone)
        if acc is None:
            raise AppError(400, "OTP_INVALID", _BAD_CODE)
        self._check(acc.id, normalize_phone(acc.phone or phone), code)
        audit.record(self.session, actor_id=acc.id, action="PASSWORD_RESET_PHONE", entity_type="account", entity_id=acc.id,
                     ip=self.ip)
        ttl = timedelta(minutes=self.cfg.reset_token_ttl_min)
        token = security.create_token(acc.id, security.RESET, ttl, fp=security.password_fingerprint(acc.password_hash))
        return token, int(ttl.total_seconds())
