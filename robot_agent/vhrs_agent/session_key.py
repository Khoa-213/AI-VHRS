"""The agent's credential when a technician logs in (the desktop app): a short-lived key from the backend instead of a key file.

Flow: log in with the technician's own account -> find the robot they hold a live job on -> `POST /technician/robots/{id}/agent-session`
-> use that key for the link to the backend. The key lives only in memory. Shortly before it expires (renew_after_s) a new key is
requested with the SAME instance_id; the backend lets the old key live a couple of minutes more, so the swap never looks like a lost
link. If another app (or person) controls the robot the backend answers 409 ROBOT_IN_USE and this module refuses to start: nobody is
pushed out. The password is kept in memory only for the day's re-logins and is never written anywhere.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable

import httpx


class SessionKeyError(Exception):
    def __init__(self, code: str, message: str, status: int = 0):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.status = code, message, status


class SessionKeyProvider:
    def __init__(self, backend_url: str, email: str, password: str, *, robot_id: int | None = None, instance_id: str | None = None,
                 transport: httpx.BaseTransport | None = None, clock: Callable[[], float] = time.monotonic):
        self.http = httpx.Client(base_url=backend_url.rstrip("/") + "/api/v1", transport=transport, timeout=15.0)
        self._email, self._password = email, password
        self.robot_id, self.instance_id = robot_id, instance_id or uuid.uuid4().hex
        self.clock = clock
        self._lock = threading.Lock()
        self._access: str | None = None
        self._refresh: str | None = None
        self._key: str | None = None
        self._renew_at = 0.0
        self.expires_in = 0.0
        self.renewals = 0

    # ---- backend calls
    def _call(self, method: str, path: str, *, auth: bool = True, **kw: Any) -> Any:
        for attempt in (0, 1):
            headers = {"Authorization": f"Bearer {self._access}"} if auth and self._access else {}
            r = self.http.request(method, path, headers=headers, **kw)
            if r.status_code == 401 and auth and attempt == 0:
                self._login()                                         # the access token expired: log in again once
                continue
            break
        if r.status_code >= 400:
            err = (r.json().get("error") if r.headers.get("content-type", "").startswith("application/json") else None) or {}
            raise SessionKeyError(err.get("code", "HTTP_ERROR"), err.get("message", r.text[:200]), r.status_code)
        return r.json() if r.content else None

    def _login(self) -> None:
        if self._refresh:
            r = self.http.post("/auth/refresh", json={"refresh_token": self._refresh})
            if r.status_code == 200:
                self._access, self._refresh = r.json()["access_token"], r.json()["refresh_token"]
                return
        r = self.http.post("/auth/login", json={"email": self._email, "password": self._password})
        if r.status_code != 200:
            raise SessionKeyError("LOGIN_FAILED", "Đăng nhập thất bại (sai email/mật khẩu hoặc tài khoản bị khoá).", r.status_code)
        body = r.json()
        if body["account"]["role"] != "TECHNICAL_STAFF":
            raise SessionKeyError("NOT_TECHNICIAN", "Chỉ tài khoản Technical Staff điều khiển được robot.", 403)
        self._access, self._refresh = body["access_token"], body["refresh_token"]

    def _resolve_robot(self) -> int:
        if self.robot_id is not None:
            return self.robot_id
        robots = self._call("GET", "/technician/robot-status")
        ids = [r["robot_id"] for r in robots]
        if len(ids) == 1:
            return ids[0]
        raise SessionKeyError("ROBOT_AMBIGUOUS" if ids else "NO_ROBOT",
                              f"Bạn đang phụ trách {len(ids)} robot ({ids}); hãy chỉ định robot_id." if ids else
                              "Bạn chưa có job đang hoạt động trên robot nào.")

    def _issue(self) -> None:
        out = self._call("POST", f"/technician/robots/{self.robot_id}/agent-session", json={"instance_id": self.instance_id})
        self._key = out["key"]
        self.expires_in = float(out["renew_after_s"])
        self._renew_at = self.clock() + float(out["renew_after_s"])

    # ---- lifecycle
    def start(self) -> str:
        """Log in and obtain the first key. Raises SessionKeyError (ROBOT_IN_USE, LOGIN_FAILED, ...): the caller must not run then."""
        with self._lock:
            self._login()
            self.robot_id = self._resolve_robot()
            self._issue()
            return self._key

    def current(self) -> str:
        """The key to use right now; asks for a new one first when it is time (never raises: a failed renewal is retried next call)."""
        with self._lock:
            if self.clock() >= self._renew_at:
                self._renew_locked()
            return self._key

    def renew_now(self) -> bool:
        with self._lock:
            return self._renew_locked(force=True)

    def _renew_locked(self, force: bool = False) -> bool:
        try:
            self._issue()
            self.renewals += 1
            return True
        except Exception:                                              # noqa: BLE001 - keep the old key; try again in 30 s (it still has its grace)
            self._renew_at = self.clock() + 30.0
            return False

    def release(self) -> None:
        with self._lock:
            if self._key is None:
                return
            try:
                self._call("DELETE", f"/technician/robots/{self.robot_id}/agent-session", params={"instance_id": self.instance_id})
            except Exception:                                          # noqa: BLE001 - e.g. RUN_OPEN: the key simply expires
                pass
            self._key = None
