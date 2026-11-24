"""Public address of catalog media (migration 0030): the workshop's own photos of papers, pens and inks, and template previews.

They live in a PUBLIC storage bucket (`CATALOG_MEDIA_BUCKET`), apart from the private bucket of customer uploads: a
product photo is not personal data, and a public object is served by the storage CDN without a signed link that expires.
The database keeps only the object path; the address is built here, so moving the bucket never touches a row.
"""
from urllib.parse import quote

from app.core.config import get_settings


def public_url(path: str | None) -> str | None:
    """Address of an object of the catalog media bucket (None: no image, or storage is not configured)."""
    s = get_settings()
    if not path or not s.supabase_url:
        return None
    return f"{s.supabase_url.rstrip('/')}/storage/v1/object/public/{s.catalog_media_bucket}/{quote(path)}"


def api_url(path: str) -> str:
    """Address of a route of this API (`path` after /api/v1). Absolute when PUBLIC_BASE_URL is set (the deployed API);
    otherwise from the site root, which the web app's dev proxy forwards."""
    base = (get_settings().public_base_url or "").rstrip("/")
    return f"{base}/api/v1{path}"
