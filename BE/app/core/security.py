"""Password hashing and signed tokens (JWT)."""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.errors import AppError

BCRYPT_MAX_BYTES = 72
ACCESS, REFRESH, RESET = "access", "refresh", "reset"
_PASSWORD_RULE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")  # assumption: >= 8, letter + digit


def validate_password_strength(password: str) -> None:
    if not _PASSWORD_RULE.match(password) or len(password.encode()) > BCRYPT_MAX_BYTES:
        raise AppError(422, "WEAK_PASSWORD",
                       "Mật khẩu cần 8–72 ký tự, gồm ít nhất một chữ cái và một chữ số.")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:BCRYPT_MAX_BYTES], password_hash.encode())
    except ValueError:
        return False


def password_fingerprint(password_hash: str) -> str:
    """Short digest embedded in reset tokens so a token dies once the password changes."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def create_token(subject: int, token_type: str, ttl: timedelta, **claims: Any) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(subject), "typ": token_type, "iat": now, "exp": now + ttl, **claims}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AppError(401, "TOKEN_EXPIRED", "Phiên hoặc liên kết đã hết hạn.") from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(401, "TOKEN_INVALID", "Token không hợp lệ.") from exc
    if payload.get("typ") != expected_type:
        raise AppError(401, "TOKEN_INVALID", "Token không hợp lệ.")
    return payload
