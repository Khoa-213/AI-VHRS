"""Object storage port for customer uploads (BR-04, NFR-12). The DB keeps only the object path.

Flow: the API signs a short-lived upload URL, the client PUTs the file straight to storage, then
calls the confirm endpoint; the API reads the object back to validate and analyse it.
"""
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core import media
from app.core.config import get_settings
from app.core.errors import AppError


@dataclass(frozen=True)
class UploadTarget:
    url: str
    method: str
    expires_in: int


class ObjectStorage(Protocol):
    def create_upload_target(self, path: str) -> UploadTarget: ...
    def write(self, path: str, data: bytes, content_type: str) -> None: ...
    def read(self, path: str) -> bytes | None: ...
    def delete(self, path: str) -> None: ...
    def create_download_url(self, path: str, ttl_seconds: int = 600) -> str: ...
    def create_download_urls(self, paths: list[str], ttl_seconds: int = 600) -> dict[str, str]: ...


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

    def write(self, path: str, data: bytes, content_type: str) -> None:
        """Server-side upload (generated sketches, quotation PDFs); overwrites an existing object."""
        self._ensure_bucket()
        r = httpx.post(f"{self.base}/object/{self.bucket}/{path}", content=data, timeout=60,
                       headers={**self._headers, "Content-Type": content_type, "x-upsert": "true"})
        if r.status_code >= 400:
            raise AppError(503, "STORAGE_UNAVAILABLE", "Không lưu được file lên dịch vụ lưu trữ.")

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

    def create_download_urls(self, paths: list[str], ttl_seconds: int = 600) -> dict[str, str]:
        """Sign many objects in one request (public lists). Paths that cannot be signed are left out."""
        if not paths:
            return {}
        r = httpx.post(f"{self.base}/object/sign/{self.bucket}", headers=self._headers, timeout=15,
                       json={"expiresIn": ttl_seconds, "paths": paths})
        if r.status_code >= 400:
            raise AppError(503, "STORAGE_UNAVAILABLE", "Không tạo được liên kết xem file.")
        out = {}
        for item in r.json():
            if item.get("signedURL") and not item.get("error"):
                out[item["path"]] = f"{self.base}{item['signedURL']}"
        return out


class SupabaseMediaStorage(SupabaseStorage):
    """The PUBLIC bucket of catalog media (migration 0030). Anyone who has an object's address can read it; only this
    server writes. The bucket is created public; one that already exists and is private is never switched here (a wrong
    bucket name must not publish what is in it)."""
    MIME_TYPES = ["image/webp", "image/png", "image/jpeg"]

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        r = httpx.post(f"{self.base}/bucket", headers=self._headers, timeout=15,
                       json={"id": self.bucket, "name": self.bucket, "public": True, "allowed_mime_types": self.MIME_TYPES})
        if r.status_code >= 500 or r.status_code in (401, 403):
            raise AppError(503, "STORAGE_UNAVAILABLE", "Dịch vụ lưu trữ tạm thời không khả dụng.")
        if r.status_code >= 400:                               # it exists already: check that it is the public one
            info = httpx.get(f"{self.base}/bucket/{self.bucket}", headers=self._headers, timeout=15)
            if info.status_code >= 400 or info.json().get("public") is not True:
                raise AppError(503, "MEDIA_BUCKET_NOT_PUBLIC",
                               f"Bucket '{self.bucket}' đã có nhưng không công khai; kiểm tra CATALOG_MEDIA_BUCKET.")
        self._bucket_ready = True

    def write(self, path: str, data: bytes, content_type: str, *, max_age: int = 3600) -> None:
        """Upload (overwrites). `max_age`: seconds browsers and the CDN may keep the object."""
        self._ensure_bucket()
        r = httpx.post(f"{self.base}/object/{self.bucket}/{path}", content=data, timeout=60,
                       headers={**self._headers, "Content-Type": content_type, "x-upsert": "true",
                                "cache-control": f"max-age={int(max_age)}"})
        if r.status_code >= 400:
            raise AppError(503, "STORAGE_UNAVAILABLE", "Không lưu được file lên dịch vụ lưu trữ.")

    def public_url(self, path: str) -> str | None:
        return media.public_url(path)


class InMemoryStorage:
    """Test double. Never used in production wiring."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def create_upload_target(self, path: str) -> UploadTarget:
        return UploadTarget(url=f"memory://{path}", method="PUT", expires_in=60)

    def put(self, path: str, data: bytes) -> None:
        self.objects[path] = data

    def write(self, path: str, data: bytes, content_type: str, **_: object) -> None:
        self.objects[path] = data

    def public_url(self, path: str) -> str | None:
        return media.public_url(path)

    def read(self, path: str) -> bytes | None:
        return self.objects.get(path)

    def delete(self, path: str) -> None:
        self.objects.pop(path, None)

    def create_download_url(self, path: str, ttl_seconds: int = 600) -> str:
        return f"memory://{path}"

    def create_download_urls(self, paths: list[str], ttl_seconds: int = 600) -> dict[str, str]:
        return {p: f"memory://{p}" for p in paths if p in self.objects}


_instance: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    global _instance
    if _instance is None:
        s = get_settings()
        if not (s.supabase_url and s.supabase_service_key):
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        _instance = SupabaseStorage(s.supabase_url, s.supabase_service_key, s.storage_bucket, s.upload_url_ttl_seconds)
    return _instance


_media: SupabaseMediaStorage | None = None


def get_media_storage() -> SupabaseMediaStorage:
    """The public catalog media bucket (migration 0030)."""
    global _media
    if _media is None:
        s = get_settings()
        if not (s.supabase_url and s.supabase_service_key):
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        if s.catalog_media_bucket == s.storage_bucket:        # never publish the bucket of customer uploads
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "CATALOG_MEDIA_BUCKET phải khác STORAGE_BUCKET.")
        _media = SupabaseMediaStorage(s.supabase_url, s.supabase_service_key, s.catalog_media_bucket,
                                      s.upload_url_ttl_seconds)
    return _media


def optional_media_storage() -> ObjectStorage | None:
    """None when storage is not configured: only the endpoints that need it answer 503."""
    try:
        return get_media_storage()
    except AppError:
        return None
