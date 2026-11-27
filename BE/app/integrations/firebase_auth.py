"""Firebase phone sign-in as the proof that a person holds a phone number (owner's choice 2026-11-27: SpeedSMS gave the
account no sender, and a phone used as an SMS gateway cannot be kept on).

The web app runs Firebase Authentication's phone flow (Google sends the SMS, the customer types the code) and gets a
Firebase **ID token**; it sends that token here. Nothing else about the browser is trusted. Checked, as Firebase's
"Verify ID tokens using a third-party JWT library" says (firebase.google.com/docs/auth/admin/verify-id-tokens, read 2026-11-27):
RS256, `kid` among Google's certificates, signature, `exp` / `iat`, `aud` = our project id, `iss` =
https://securetoken.google.com/<project id>, a non-empty `sub`, `auth_time` in the past. On top of that, ours:
* the sign-in was by phone (`firebase.sign_in_provider == "phone"`) and the token carries `phone_number`;
* the sign-in is recent (`FIREBASE_PHONE_MAX_AGE_SECONDS`, 10 minutes): an ID token lives an hour and is refreshed for
  weeks, but a phone proof here must be the SMS the person just received.
The certificates are fetched from Google and kept for the `max-age` Google gives.

VERIFICATION: covered by tests with a locally made key and certificate. 2026-11-27: the owner verified a real number on the
deployed site (SMS from Google's sender "CloudOTP", then `POST /me/phone/verify-firebase` accepted the real ID token), which
confirms the claim names `phone_number` and `sign_in_provider: "phone"`. The password-reset path has not been tried live yet.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import httpx
import jwt
from cryptography import x509

from app.core.config import get_settings
from app.core.errors import AppError

log = logging.getLogger("app.firebase")

CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
_MAX_AGE = re.compile(r"max-age=(\d+)")


@dataclass(frozen=True)
class PhoneProof:
    uid: str
    phone: str                    # as Firebase gives it: +84...
    auth_time: int                # when the SMS code was accepted (epoch seconds)


class FirebaseVerifier(Protocol):
    def verify_phone(self, id_token: str) -> PhoneProof: ...


def _fetch_certs() -> tuple[dict[str, str], float]:
    """{kid: PEM certificate} and how many seconds they may be kept."""
    r = httpx.get(CERTS_URL, timeout=5.0)
    r.raise_for_status()
    m = _MAX_AGE.search(r.headers.get("cache-control", ""))
    return r.json(), float(m.group(1)) if m else 3600.0


class CertVerifier:
    def __init__(self, project_id: str | None = None, fetch: Callable[[], tuple[dict[str, str], float]] = _fetch_certs,
                 max_age: int | None = None):
        self._project_id, self._fetch, self._max_age = project_id, fetch, max_age
        self._certs: dict[str, str] = {}
        self._until = 0.0
        self._lock = threading.Lock()

    def _key(self, kid: str) -> Any:
        with self._lock:
            if kid not in self._certs or time.monotonic() >= self._until:
                try:
                    self._certs, ttl = self._fetch()
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("Firebase certificates not fetched: %s", type(exc).__name__)
                    raise AppError(503, "FIREBASE_UNAVAILABLE", "Không kết nối được Google, vui lòng thử lại.") from exc
                self._until = time.monotonic() + max(60.0, ttl)
            pem = self._certs.get(kid)
        if not pem:
            raise _bad()
        return x509.load_pem_x509_certificate(pem.encode()).public_key()

    def verify_phone(self, id_token: str) -> PhoneProof:
        cfg = get_settings()
        project = self._project_id or (cfg.firebase_project_id or "").strip()
        if not project:
            raise AppError(503, "FIREBASE_NOT_CONFIGURED", "Chưa cấu hình xác minh số điện thoại bằng Firebase.")
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError as exc:
            raise _bad() from exc
        if header.get("alg") != "RS256" or not header.get("kid"):
            raise _bad()
        key = self._key(str(header["kid"]))
        try:
            claims = jwt.decode(id_token, key, algorithms=["RS256"], audience=project,
                                issuer=f"https://securetoken.google.com/{project}", leeway=30,
                                options={"require": ["exp", "iat", "aud", "iss", "sub", "auth_time"]})
        except jwt.PyJWTError as exc:
            log.info("Firebase token refused: %s", type(exc).__name__)
            raise _bad() from exc
        now = time.time()
        try:
            auth_time = int(claims["auth_time"])
        except (TypeError, ValueError) as exc:
            raise _bad() from exc
        firebase = claims.get("firebase") if isinstance(claims.get("firebase"), dict) else {}
        phone = claims.get("phone_number")
        if not claims.get("sub") or auth_time > now + 30 or firebase.get("sign_in_provider") != "phone" \
                or not isinstance(phone, str) or not re.fullmatch(r"\+\d{8,15}", phone):
            log.info("Firebase token refused: not a phone sign-in (provider=%s)", firebase.get("sign_in_provider"))
            raise _bad()
        max_age = self._max_age if self._max_age is not None else cfg.firebase_phone_max_age_seconds
        if now - auth_time > max_age:
            raise AppError(401, "FIREBASE_TOKEN_EXPIRED", "Phiên xác minh số điện thoại đã cũ. Hãy nhận mã mới và thử lại.")
        return PhoneProof(uid=str(claims["sub"]), phone=phone, auth_time=auth_time)


def _bad() -> AppError:
    return AppError(401, "FIREBASE_TOKEN_INVALID", "Phiên xác minh số điện thoại không hợp lệ hoặc đã hết hạn.")


_verifier: FirebaseVerifier = CertVerifier()


def get_firebase_verifier() -> FirebaseVerifier:
    return _verifier


def firebase_configured() -> bool:
    return bool((get_settings().firebase_project_id or "").strip())
