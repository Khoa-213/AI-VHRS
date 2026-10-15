"""Object storage port for customer uploads (BR-04, NFR-12). The DB keeps only the object path.

Flow: the API signs a short-lived upload URL, the client PUTs the file straight to storage, then
calls the confirm endpoint; the API reads the object back to validate and analyse it.
"""
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import AppError


@dataclass(frozen=True)
class UploadTarget:
    url: str
    method: str
    expires_in: int


class ObjectStorage(Protocol):
    def create_upload_target(self, path: str) -> UploadTarget: ...
    def read(self, path: str) -> bytes | None: ...
    def delete(self, path: str) -> None: ...
    def create_download_url(self, path: str, ttl_seconds: int = 600) -> str: ...


class SupabaseStorage:
    def __init__(self, base_url: str, service_key: str, bucket: str, ttl: int):
        self.base = base_url.rstrip("/") + "/storage/v1"
        self.bucket, self.ttl = bucket, ttl
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        r = httpx.post(f"{self.base}/bucket", headers=self._headers, timeout=15,
                       json={"id": self.bucket, "name": self.bucket, "public": False})
        if r.status_code >= 500 or r.status_code in (401, 403):  # "already exists" (400/409) is fine
            raise AppError(503, "STORAGE_UNAVAILABLE", "Dịch vụ lưu trữ tạm thời không khả dụng.")
        self._bucket_ready = True

    def create_upload_target(self, path: str) -> UploadTarget:
        self._ensure_bucket()
        r = httpx.post(f"{self.base}/object/upload/sign/{self.bucket}/{path}", headers=self._headers, timeout=15)
        if r.status_code >= 400:
            raise AppError(503, "STORAGE_UNAVAILABLE", "Không tạo được liên kết tải lên.")
        return UploadTarget(url=f"{self.base}{r.json()['url']}", method="PUT", expires_in=self.ttl)

    def read(self, path: str) -> bytes | None:
        r = httpx.get(f"{self.base}/object/{self.bucket}/{path}", headers=self._headers, timeout=60)
        if r.status_code in (400, 404):
            return None
        if r.status_code >= 400:
            raise AppError(503, "STORAGE_UNAVAILABLE", "Không đọc được file đã tải lên.")
        return r.content

    def delete(self, path: str) -> None:
        httpx.delete(f"{self.base}/object/{self.bucket}/{path}", headers=self._headers, timeout=15)

    def create_download_url(self, path: str, ttl_seconds: int = 600) -> str:
        r = httpx.post(f"{self.base}/object/sign/{self.bucket}/{path}", headers=self._headers, timeout=15,
                       json={"expiresIn": ttl_seconds})
        if r.status_code >= 400:
            raise AppError(503, "STORAGE_UNAVAILABLE", "Không tạo được liên kết xem file.")
        return f"{self.base}{r.json()['signedURL']}"


class InMemoryStorage:
    """Test double. Never used in production wiring."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def create_upload_target(self, path: str) -> UploadTarget:
        return UploadTarget(url=f"memory://{path}", method="PUT", expires_in=60)

    def put(self, path: str, data: bytes) -> None:
        self.objects[path] = data

    def read(self, path: str) -> bytes | None:
        return self.objects.get(path)

    def delete(self, path: str) -> None:
        self.objects.pop(path, None)

    def create_download_url(self, path: str, ttl_seconds: int = 600) -> str:
        return f"memory://{path}"


_instance: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    global _instance
    if _instance is None:
        s = get_settings()
        if not (s.supabase_url and s.supabase_service_key):
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        _instance = SupabaseStorage(s.supabase_url, s.supabase_service_key, s.storage_bucket, s.upload_url_ttl_seconds)
    return _instance
