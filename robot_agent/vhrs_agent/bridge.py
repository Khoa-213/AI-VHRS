"""Backend client: the agent talks to the existing /technician/* API as the logged-in Technical Staff. It adds no endpoint.

The access token comes from the environment (VHRS_TOKEN), never from a file in the repository. The agent cannot approve
anything the technician could not: BR-19 (own jobs only), the hash check, calibration and simulation gates all stay on
the server.
"""
from __future__ import annotations

import json
from typing import Any, Callable

import httpx

from app.services.stroke_ai import trajectory as tj
from app.services.stroke_ai.trajectory import Page

_EVENT_FIELDS = ("stroke_index", "progress_pct", "force_summary")
PACKAGE_READ_TIMEOUT_S = 90.0      # BE verifies the stored package; its storage read alone can take up to 60 s
TRAJECTORY_READ_TIMEOUT_S = 60.0


def _load_timeout(read_s: float) -> httpx.Timeout:
    return httpx.Timeout(connect=5.0, read=read_s, write=15.0, pool=5.0)


class BridgeError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code = status, code


class BackendBridge:
    """`token` is the access token string, or a callable returning the current one (so a long run can refresh it)."""

    def __init__(self, base_url: str, token: "str | Callable[[], str]", transport: httpx.BaseTransport | None = None,
                 timeout: float = 15.0, downloader: Callable[[str], bytes] | None = None):
        self._token: Callable[[], str] = token if callable(token) else (lambda: token)
        self.http = httpx.Client(base_url=base_url.rstrip("/") + "/api/v1/technician", transport=transport, timeout=timeout)
        self.root = httpx.Client(base_url=base_url.rstrip("/") + "/api/v1", transport=transport, timeout=timeout)
        self._download = downloader or self._download_trajectory

    @staticmethod
    def _download_trajectory(url: str) -> bytes:
        response = httpx.get(url, timeout=_load_timeout(TRAJECTORY_READ_TIMEOUT_S))
        response.raise_for_status()
        return response.content

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        try:
            r = self.http.request(method, path, headers={"Authorization": f"Bearer {self._token()}"}, **kw)
        except httpx.TimeoutException:
            raise BridgeError(504, "BACKEND_TIMEOUT", f"Hết thời gian chờ backend: {method} {path}. "
                              "Kiểm tra log cửa sổ BE; job package cần đọc và kiểm tra file trong kho lưu trữ.") from None
        except httpx.RequestError:
            raise BridgeError(502, "BACKEND_UNREACHABLE", f"Không kết nối được backend: {method} {path}.") from None
        if r.status_code >= 400:
            err = (r.json().get("error") if r.headers.get("content-type", "").startswith("application/json") else None) or {}
            raise BridgeError(r.status_code, err.get("code", "HTTP_ERROR"), err.get("message", r.text[:200]))
        return r.json() if r.content else None

    def root_req(self, method: str, path: str, *, auth: bool = True, **kw: Any) -> Any:
        """A call outside /technician (login, refresh, me)."""
        headers = {"Authorization": f"Bearer {self._token()}"} if auth else {}
        r = self.root.request(method, path, headers=headers, **kw)
        if r.status_code >= 400:
            err = (r.json().get("error") if r.headers.get("content-type", "").startswith("application/json") else None) or {}
            raise BridgeError(r.status_code, err.get("code", "HTTP_ERROR"), err.get("message", r.text[:200]))
        return r.json() if r.content else None

    # ---- job package (UC-32): the server checks the hash; the agent checks it again on the bytes it will use
    def fetch_job(self, job_id: int) -> dict[str, Any]:
        pkg = self._req("GET", f"/jobs/{job_id}/package", timeout=_load_timeout(PACKAGE_READ_TIMEOUT_S))
        try:
            raw = self._download(pkg["trajectory_url"])
        except httpx.TimeoutException:
            raise BridgeError(504, "TRAJECTORY_DOWNLOAD_TIMEOUT", "Đã lấy được gói từ backend nhưng tải file quỹ đạo "
                              "từ kho lưu trữ bị hết thời gian chờ. Kiểm tra Internet tới kho lưu trữ.") from None
        except httpx.HTTPStatusError as exc:
            # Do not include the signed download URL (it contains a temporary access token).
            raise BridgeError(502, "TRAJECTORY_DOWNLOAD_FAILED", f"Kho lưu trữ trả HTTP {exc.response.status_code} "
                              "khi tải file quỹ đạo. Chạy LOAD lại để lấy liên kết mới.") from None
        except httpx.RequestError:
            raise BridgeError(502, "TRAJECTORY_DOWNLOAD_FAILED", "Không kết nối được kho lưu trữ để tải file quỹ đạo.") from None
        actual = tj.content_hash(raw)
        if actual != pkg["package_hash"]:
            raise BridgeError(409, "JOB_HASH_MISMATCH", "File quỹ đạo tải về không khớp hash của gói job; không chạy.")
        pages: list[Page] = tj.parse(json.loads(raw))
        return {"package": pkg, "pages": pages, "hash": actual}

    def calibration(self, job_id: int, body: dict[str, Any]) -> dict[str, Any]:
        return self._req("POST", f"/jobs/{job_id}/calibration", json=body)

    def simulation(self, job_id: int, passed: bool, errors: list[str], report: dict[str, Any] | None) -> dict[str, Any]:
        return self._req("POST", f"/jobs/{job_id}/simulation", json={"passed": passed, "errors": errors, "report": report})

    def event(self, job_id: int | None, kind: str, **fields: Any) -> dict[str, Any]:
        body: dict[str, Any] = {"event_type": kind}
        for k in _EVENT_FIELDS:
            if fields.get(k) is not None:
                body[k] = fields.pop(k)
            else:
                fields.pop(k, None)
        if fields:
            body["payload"] = fields
        return self._req("POST", f"/jobs/{job_id}/events", json=body)

    def finish(self, job_id: int) -> dict[str, Any]:
        return self._req("POST", f"/jobs/{job_id}/finish")

    # ---- robot operations (runs, alerts, heartbeat)
    def open_run(self, job_id: int, **fields: Any) -> dict[str, Any]:
        return self._req("POST", f"/jobs/{job_id}/runs", json={k: v for k, v in fields.items() if v is not None})

    def close_run(self, run_id: str, **fields: Any) -> dict[str, Any]:
        return self._req("PATCH", f"/runs/{run_id}", json={k: v for k, v in fields.items() if v is not None})

    def alert(self, robot_id: int, code: str, *, job_id: int | None = None, run_id: str | None = None,
              details: dict[str, Any] | None = None) -> dict[str, Any]:
        body = {"robot_id": robot_id, "code": code, "job_id": job_id, "run_id": run_id, "details": details}
        return self._req("POST", "/alerts", json={k: v for k, v in body.items() if v is not None})

    def heartbeat(self, robot_id: int, **fields: Any) -> dict[str, Any]:
        return self._req("PUT", f"/robots/{robot_id}/heartbeat", json={k: v for k, v in fields.items() if v is not None})

    def job_detail(self, job_id: int) -> dict[str, Any]:
        return self._req("GET", f"/jobs/{job_id}")
