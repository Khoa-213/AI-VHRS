"""Google sign-in port. The browser / app obtains a Google **ID token** (Google Identity Services) and sends it to
POST /auth/google; this module checks it with Google (tokeninfo endpoint) and returns who the person is.

Checked here: Google accepts the token (signature, expiry), `aud` is one of OUR client ids, `iss` is Google, the e-mail
is verified. Nothing else about the token is trusted.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import AppError

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    name: str | None


class GoogleVerifier(Protocol):
    def verify(self, id_token: str) -> GoogleIdentity: ...


class TokenInfoVerifier:
    def __init__(self, client_ids: list[str] | None = None, http: httpx.Client | None = None):
        self._client_ids, self._http = client_ids, http

    def verify(self, id_token: str) -> GoogleIdentity:
        client_ids = self._client_ids if self._client_ids is not None else get_settings().google_client_ids
        if not client_ids:
            raise AppError(503, "GOOGLE_NOT_CONFIGURED", "Chưa cấu hình đăng nhập bằng Google.")
        try:
            if self._http is not None:
                r = self._http.get(TOKENINFO_URL, params={"id_token": id_token})
            else:
                r = httpx.get(TOKENINFO_URL, params={"id_token": id_token}, timeout=5.0)
        except httpx.HTTPError as exc:
            raise AppError(503, "GOOGLE_UNAVAILABLE", "Không kết nối được Google, vui lòng thử lại.") from exc
        bad = AppError(401, "GOOGLE_TOKEN_INVALID", "Phiên đăng nhập Google không hợp lệ hoặc đã hết hạn.")
        if r.status_code != 200:
            raise bad
        data = r.json()
        try:
            expires = datetime.fromtimestamp(int(data["exp"]), timezone.utc)
        except (KeyError, ValueError, TypeError) as exc:
            raise bad from exc
        if (data.get("aud") not in client_ids or data.get("iss") not in _ISSUERS or expires <= datetime.now(timezone.utc)
                or not data.get("sub") or not data.get("email")):
            raise bad
        if str(data.get("email_verified")).lower() != "true":
            raise AppError(401, "GOOGLE_EMAIL_NOT_VERIFIED", "Email Google chưa được xác minh.")
        return GoogleIdentity(sub=data["sub"], email=data["email"].strip(), name=data.get("name"))


_verifier: GoogleVerifier = TokenInfoVerifier()


def get_google_verifier() -> GoogleVerifier:
    return _verifier
