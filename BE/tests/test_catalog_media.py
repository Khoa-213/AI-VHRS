"""Catalog images (migration 0030): the workshop's own photo of a paper, a pen and an ink, served from the public media
bucket, and the address of a template's preview.

The media bucket is an in-memory double here (the last test alone talks to the real public bucket, when storage is
configured). Everything created carries a 'pytest_' code and is removed by conftest.
"""
import struct
import uuid

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core import media as media_urls
from app.core.config import get_settings
from app.integrations.storage import InMemoryStorage, get_media_storage, optional_media_storage
from app.main import app
from app.services import catalog_media as cm
from app.services import manager_catalog
from tests.conftest import fresh_code
from tests.test_api_manager_ops import M, _paper, mgr  # noqa: F401
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import _err, _user, store, wcat  # noqa: F401


@pytest.fixture(autouse=True)
def bucket():
    mem = InMemoryStorage()
    app.dependency_overrides[optional_media_storage] = lambda: mem
    yield mem
    app.dependency_overrides.pop(optional_media_storage, None)


# ---------------------------------------------------------------------------------------------------------- images
def _exif(orientation: int, make: bytes = b"SECRETCAM\x00") -> bytes:
    """An EXIF block (APP1) with the camera maker and the orientation: what a phone writes into a photo."""
    entries, first_ifd = 2, 8
    data_at = first_ifd + 2 + entries * 12 + 4
    tiff = b"MM\x00\x2a" + struct.pack(">I", first_ifd) + struct.pack(">H", entries)
    tiff += struct.pack(">HHII", 0x010F, 2, len(make), data_at)
    tiff += struct.pack(">HHI", 0x0112, 3, 1) + struct.pack(">HH", orientation, 0)
    tiff += struct.pack(">I", 0) + make
    body = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(body) + 2) + body


def _picture(w: int = 1600, h: int = 1200, text: str = "GIAY", tone: int = 235) -> np.ndarray:
    img = np.full((h, w, 3), tone, np.uint8)
    cv2.putText(img, text, (w // 20, h // 2), cv2.FONT_HERSHEY_SIMPLEX, max(1.0, w / 200), (30, 60, 200), max(2, w // 80))
    return img


def _jpeg(orientation: int | None = None, **kw) -> bytes:
    data = cv2.imencode(".jpg", _picture(**kw))[1].tobytes()
    return data if orientation is None else data[:2] + _exif(orientation) + data[2:]


def _png_cutout() -> bytes:
    rgba = np.zeros((300, 500, 4), np.uint8)
    rgba[50:250, 100:400] = (10, 20, 30, 255)                     # a dark shape on a transparent background
    return cv2.imencode(".png", rgba)[1].tobytes()


def _put(client, h, kind: str, row_id: int, data, mime: str = "image/jpeg"):
    return client.put(f"{M}/{kind}/{row_id}/image", headers={**h, "Content-Type": mime}, content=data)


def _decoded(data: bytes) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)


def _logged(action: str, entity: str, entity_id: int) -> int:
    """Audit rows of one row of one table (paper, pen and ink ids come from different sequences and can be equal)."""
    return _sql("select count(*) from audit_logs where action=:a and entity_type=:e and entity_id=:i",
                a=action, e=entity, i=entity_id)


# ---------------------------------------------------------------------------------------------------------- upload
def test_a_paper_photo_is_stored_upright_small_without_exif_and_the_catalog_serves_it(client, mgr, bucket):
    paper = _paper(client, mgr)
    assert paper["image_url"] is None
    r = _put(client, mgr, "papers", paper["id"], _jpeg(orientation=6))    # a phone photo held upright: 1600x1200 + "rotate"
    assert r.status_code == 200, r.text
    (path, stored), = bucket.objects.items()
    assert path.startswith(f"papers/{paper['id']}/") and path.endswith(".webp")
    assert r.json()["image_url"] == media_urls.public_url(path)
    assert "/storage/v1/object/public/" + get_settings().catalog_media_bucket + "/" in r.json()["image_url"]
    assert cm.sniff(stored) == "webp" and _decoded(stored).shape[:2] == (800, 600)        # upright, longer side 800
    assert b"SECRETCAM" not in stored and b"Exif" not in stored and b"EXIF" not in stored
    # public catalog and the Manager list carry the same address
    listed = next(p for p in client.get(f"{API}/catalog/papers").json() if p["id"] == paper["id"])
    assert listed["image_url"] == r.json()["image_url"]
    assert next(p for p in client.get(f"{M}/papers", headers=mgr).json() if p["id"] == paper["id"])["image_url"] == listed["image_url"]
    assert _logged("CATALOG_IMAGE_SET", "paper_type", paper["id"]) == 1
    assert _sql("select image_updated_at is not null from paper_types where id=:i", i=paper["id"])


def test_a_new_photo_replaces_the_old_file_the_same_photo_is_kept_and_removing_deletes_it(client, mgr, bucket):
    paper = _paper(client, mgr)
    first = _put(client, mgr, "papers", paper["id"], _jpeg(text="MOT")).json()["image_url"]
    second = _put(client, mgr, "papers", paper["id"], _jpeg(text="HAI")).json()["image_url"]
    assert second != first and len(bucket.objects) == 1                    # the address changes, the old file is gone
    assert second == media_urls.public_url(next(iter(bucket.objects)))
    again = _put(client, mgr, "papers", paper["id"], _jpeg(text="HAI"))
    assert again.json()["image_url"] == second and len(bucket.objects) == 1   # same photo: same object, not deleted
    r = client.delete(f"{M}/papers/{paper['id']}/image", headers=mgr)
    assert r.status_code == 200 and r.json()["image_url"] is None and not bucket.objects
    assert _sql("select image_path is null from paper_types where id=:i", i=paper["id"])
    assert client.delete(f"{M}/papers/{paper['id']}/image", headers=mgr).status_code == 200   # asked twice
    assert _logged("CATALOG_IMAGE_REMOVE", "paper_type", paper["id"]) == 1
    assert _logged("CATALOG_IMAGE_SET", "paper_type", paper["id"]) == 3


def test_pen_and_ink_photos_reach_every_catalog_answer_and_a_cutout_keeps_its_transparency(client, mgr, wcat, bucket):
    assert _put(client, mgr, "papers", wcat["paper"], _jpeg()).status_code == 200
    pen = _put(client, mgr, "pens", wcat["gel"], _png_cutout(), "image/png")
    assert pen.status_code == 200, pen.text
    ink = _put(client, mgr, "inks", wcat["gel_ink"], cv2.imencode(".webp", _picture(400, 120, "MUC"))[1].tobytes(), "image/webp")
    assert ink.status_code == 200, ink.text
    pen_path = next(p for p in bucket.objects if p.startswith(f"pens/{wcat['gel']}/"))
    cut = _decoded(bucket.objects[pen_path])
    assert cut.shape == (300, 500, 4) and int(cut[:, :, 3].min()) == 0 and int(cut[:, :, 3].max()) == 255
    assert _decoded(next(v for k, v in bucket.objects.items() if k.startswith("inks/"))).shape[:2] == (120, 400)   # not enlarged
    pens = client.get(f"{API}/catalog/pens", params={"paper_id": wcat["paper"]}).json()
    assert next(p for p in pens if p["id"] == wcat["gel"])["image_url"] == pen.json()["image_url"]
    inks = client.get(f"{API}/catalog/pens/{wcat['gel']}/inks").json()
    assert next(i for i in inks if i["id"] == wcat["gel_ink"])["image_url"] == ink.json()["image_url"]
    s = client.get(f"{API}/catalog/suggest-materials", params={"paper_type_id": wcat["paper"]}).json()
    assert s["paper"]["image_url"] == media_urls.public_url(next(p for p in bucket.objects if p.startswith("papers/")))
    gel = next(p for p in s["pens"] if p["id"] == wcat["gel"])
    assert gel["image_url"] == pen.json()["image_url"] and gel["inks"][0]["image_url"] == ink.json()["image_url"]
    other = next(p for p in s["pens"] if p["id"] == wcat["fountain"])
    assert other["image_url"] is None and other["inks"][0]["image_url"] is None        # no photo yet: null, never a guess
    assert _logged("CATALOG_IMAGE_SET", "pen_type", wcat["gel"]) == 1 and _logged("CATALOG_IMAGE_SET", "ink_color", wcat["gel_ink"]) == 1


# ---------------------------------------------------------------------------------------------------------- refusals
def test_what_is_not_a_usable_image_is_refused_and_nothing_is_stored(client, mgr, bucket):
    paper = _paper(client, mgr)
    bomb = bytearray(cv2.imencode(".png", np.zeros((40, 40), np.uint8))[1].tobytes())
    bomb[16:24] = struct.pack(">II", 30000, 30000)                          # a small file that claims 900 megapixels
    megabyte = b"\x00" * (1024 * 1024)
    cases = [
        (b"GIF89a" + b"0" * 200, "image/gif", "UNSUPPORTED_FILE"),
        (b"%PDF-1.7 not an image", "image/jpeg", "UNSUPPORTED_FILE"),          # the declared type is not believed
        (b"\xff\xd8\xff" + b"\x00" * 60, "image/jpeg", "INVALID_IMAGE"),
        (b"", "image/jpeg", "INVALID_IMAGE"),
        (bytes(bomb), "image/png", "IMAGE_TOO_MANY_PIXELS"),
        (cv2.imencode(".png", np.zeros((10, 10, 3), np.uint8))[1].tobytes(), "image/png", "IMAGE_TOO_SMALL"),
        (b"\xff\xd8\xff" + megabyte * 5, "image/jpeg", "FILE_TOO_LARGE"),      # Content-Length says it
        ((megabyte for _ in range(6)), "image/jpeg", "FILE_TOO_LARGE"),       # no Content-Length: cut while streaming
    ]
    for data, mime, code in cases:
        r = _put(client, mgr, "papers", paper["id"], data, mime)
        assert r.status_code == 422 and _err(r) == code, (code, r.status_code, r.text[:200])
    assert not bucket.objects and _sql("select image_path is null from paper_types where id=:i", i=paper["id"])
    assert _logged("CATALOG_IMAGE_SET", "paper_type", paper["id"]) == 0
    for kind in ("papers", "pens", "inks"):
        r = _put(client, mgr, kind, 999999999, _jpeg())
        assert r.status_code == 404 and _err(r) == "NOT_FOUND", r.text
        assert client.delete(f"{M}/{kind}/999999999/image", headers=mgr).status_code == 404


def test_only_the_manager_sets_or_removes_a_photo(client, mgr, bucket):
    paper = _paper(client, mgr)
    url = f"{M}/papers/{paper['id']}/image"
    assert client.put(url, content=_jpeg(), headers={"Content-Type": "image/jpeg"}).status_code == 401
    assert client.delete(url).status_code == 401
    for role in ("CUSTOMER", "STAFF", "TECHNICAL_STAFF", "ADMIN"):
        h = _user(client, role)[0]
        r = _put(client, h, "papers", paper["id"], _jpeg())
        assert r.status_code == 403 and _err(r) == "FORBIDDEN", (role, r.text)
        assert client.delete(url, headers=h).status_code == 403
    assert not bucket.objects


def test_without_storage_an_upload_answers_503_and_a_failed_save_keeps_the_previous_photo(client, mgr, bucket, monkeypatch):
    paper = _paper(client, mgr)
    before = _put(client, mgr, "papers", paper["id"], _jpeg(text="CU")).json()["image_url"]
    kept = dict(bucket.objects)
    # the change is not saved (the audit store fails): the row still shows the old photo and its file is still there
    loose = TestClient(app, raise_server_exceptions=False)
    with monkeypatch.context() as m:
        def audit_down(*a, **k):
            raise RuntimeError("audit store down")
        m.setattr(manager_catalog.audit, "record", audit_down)
        assert _put(loose, mgr, "papers", paper["id"], _jpeg(text="MOI")).status_code == 500
    now = next(p for p in client.get(f"{M}/papers", headers=mgr).json() if p["id"] == paper["id"])
    assert now["image_url"] == before and all(bucket.objects.get(k) == v for k, v in kept.items())
    # storage not configured: a clear 503, and removing still clears the row
    app.dependency_overrides[optional_media_storage] = lambda: None
    r = _put(client, mgr, "papers", paper["id"], _jpeg(text="MOI"))
    assert r.status_code == 503 and _err(r) == "STORAGE_NOT_CONFIGURED"
    assert client.delete(f"{M}/papers/{paper['id']}/image", headers=mgr).json()["image_url"] is None


# ---------------------------------------------------------------------------------------------------------- templates
def test_a_template_preview_address_can_always_be_opened(client, mgr, wcat):
    code = fresh_code()
    stored = _sql("""insert into templates (code,name,kind,font_uri,preview_url) values (:c,'Mau co anh','SINGLE_LINE_FONT',
                     'hershey:futural','fonts/mau-co-anh/preview.png') returning id""", c=code + "_tp")
    full = _sql("""insert into templates (code,name,kind,font_uri,preview_url) values (:c,'Mau url','SINGLE_LINE_FONT',
                   'hershey:futural','https://example.org/p.png') returning id""", c=code + "_tu")
    rows = {t["id"]: t for t in client.get(f"{API}/catalog/templates").json()}
    drawn = rows[wcat["tpl"]]["preview_url"]                                 # no stored preview: the sample this API draws
    assert drawn == media_urls.api_url(f"/catalog/templates/{wcat['tpl']}/preview")
    r = client.get(drawn[drawn.index("/api/v1"):])
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert rows[stored]["preview_url"] == media_urls.public_url("fonts/mau-co-anh/preview.png")
    assert rows[full]["preview_url"] == "https://example.org/p.png"
    admin = {t["id"]: t for t in client.get(f"{M}/templates", headers=mgr).json()}
    assert admin[stored]["preview_url"] == rows[stored]["preview_url"] and admin[wcat["tpl_off"]]["preview_url"]


# ---------------------------------------------------------------------------------------------------------- file headers
def test_the_size_is_read_from_the_header_of_every_accepted_format():
    img = _picture(640, 360)
    assert cm.header_size(cv2.imencode(".png", img)[1].tobytes(), "png") == (640, 360)
    assert cm.header_size(_jpeg(orientation=6, w=640, h=360), "jpeg") == (640, 360)          # stored size, before turning
    lossy = cv2.imencode(".webp", img, [cv2.IMWRITE_WEBP_QUALITY, 80])[1].tobytes()
    lossless = cv2.imencode(".webp", img, [cv2.IMWRITE_WEBP_QUALITY, 101])[1].tobytes()
    assert (lossy[12:16], lossless[12:16]) == (b"VP8 ", b"VP8L")
    assert cm.header_size(lossy, "webp") == cm.header_size(lossless, "webp") == (640, 360)
    extended = cm.normalise(_png_cutout())[0]                                # with transparency: the extended layout
    assert extended[12:16] == b"VP8X" and cm.header_size(extended, "webp") == (500, 300)
    assert cm.header_size(b"\x89PNG\r\n\x1a\n" + b"\x00" * 4, "png") is None
    assert cm.object_path("ink", 7, b"abc") == cm.object_path("ink", 7, b"abc") != cm.object_path("ink", 8, b"abc")


# ---------------------------------------------------------------------------------------------------------- real bucket
@pytest.mark.skipif(not get_settings().supabase_service_key, reason="storage not configured")
def test_the_real_media_bucket_serves_a_stored_file_to_anyone_by_its_address():
    real = get_media_storage()
    path = f"selftest/{uuid.uuid4().hex}.webp"
    stored = cm.normalise(_jpeg(w=400, h=300))[0]
    real.write(path, stored, cm.CONTENT_TYPE, max_age=0)
    try:
        r = httpx.get(real.public_url(path), timeout=30)                     # no key, no signature
        assert r.status_code == 200 and r.content == stored and r.headers["content-type"] == "image/webp"
    finally:
        real.delete(path)
