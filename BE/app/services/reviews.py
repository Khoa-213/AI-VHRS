"""Customer reviews (FR-58, UC-20/59) and the workshop showcase (FR-54, UC-55). Phase 5c.

Reviews
* One review per order, only for the customer's own COMPLETED order (also enforced by the DB trigger `trg_reviews_guard`).
* 1-5 stars, an optional comment (<= 2000 characters), up to 5 photos (jpg/png <= 5 MB) uploaded straight to storage and
  referenced by path (same pattern as chat attachments: the path must live under the order's review folder of the customer).
* The customer may edit it for EDIT_DAYS days after posting (ASSUMPTION, owner to confirm); a PUT replaces the whole review.
* A Manager may hide a review (abuse, personal data) and show it again; the reason goes to the audit log. A hidden review is
  still visible to its author, marked hidden, and can no longer be edited.
* The public list shows the shown reviews newest first with the customer's name shortened ("Nguyễn V. A."), never an e-mail.

Showcase
* Staff and Manager post sample products for the home page: an image they upload themselves (never a customer's product photo:
  there is no customer consent for that), a title, a description, the order type, visible or not, a sort order.
* The public list shows the visible posts by `sort_order`, newest first; who posted it is not shown.

Photos are private in storage: every list hands out signed links (PUBLIC_URL_TTL), signed in one request when the storage can.
"""
from __future__ import annotations  # a method named `list` would otherwise shadow the builtin in later annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.integrations.storage import ObjectStorage, UploadTarget
from app.models.account import Account
from app.models.order import Order, OrderStatus, OrderType
from app.models.review import Review, ReviewPhoto, ShowcasePost
from app.repositories.orders import OrderRepository
from app.services import audit, notifications
from app.services.handwriting_image import sniff_mime

EDIT_DAYS = 30
MAX_COMMENT = 2000
MAX_PHOTOS = 5
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_SHOWCASE_BYTES = 10 * 1024 * 1024
IMAGE_MIMES = {"image/jpeg": "jpg", "image/png": "png"}
PUBLIC_URL_TTL = 3600
PUBLIC_PAGE_MAX = 50


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _storage(storage: ObjectStorage | None) -> ObjectStorage:
    if storage is None:
        raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
    return storage


def sign_all(storage: ObjectStorage | None, paths: list[str], ttl: int = PUBLIC_URL_TTL) -> dict[str, str]:
    """Signed download links for many paths; one request when the storage supports it, else one per path."""
    if storage is None or not paths:
        return {}
    unique = list(dict.fromkeys(paths))
    batch = getattr(storage, "create_download_urls", None)
    if batch is not None:
        try:
            return batch(unique, ttl)
        except AppError:
            pass                                                   # fall back to one by one
    out = {}
    for p in unique:
        try:
            out[p] = storage.create_download_url(p, ttl)
        except AppError:
            continue
    return out


def short_name(full_name: str | None) -> str:
    """'Nguyễn Văn An' -> 'Nguyễn V. A.': the family name and initials, enough to read as a person, not to identify one."""
    words = (full_name or "").split()
    if not words:
        return "Khách hàng"
    return " ".join([words[0]] + [w[0].upper() + "." for w in words[1:]])


def _check_image(storage: ObjectStorage, path: str, prefix: str, max_bytes: int, what: str) -> str:
    if not path.startswith(prefix) or ".." in path:
        raise AppError(422, "INVALID_PHOTO", f"Đường dẫn {what} không hợp lệ.")
    data = storage.read(path)
    if data is None:
        raise AppError(422, "PHOTO_NOT_UPLOADED", f"{what.capitalize()} chưa được tải lên.")
    if sniff_mime(data) not in IMAGE_MIMES or len(data) > max_bytes:
        storage.delete(path)
        raise AppError(422, "INVALID_PHOTO", f"{what.capitalize()} phải là jpg/png ≤ {max_bytes // (1024 * 1024)} MB.")
    return path


def _upload(storage: ObjectStorage | None, path_stem: str, mime: str, size: int, max_bytes: int) -> tuple[str, UploadTarget]:
    if mime not in IMAGE_MIMES:
        raise AppError(422, "UNSUPPORTED_FILE", "Chỉ nhận ảnh jpg hoặc png.")
    if size > max_bytes:
        raise AppError(422, "FILE_TOO_LARGE", f"Ảnh tối đa {max_bytes // (1024 * 1024)} MB.")
    path = f"{path_stem}/{uuid.uuid4().hex}.{IMAGE_MIMES[mime]}"
    return path, _storage(storage).create_upload_target(path)


# ============================================================================================ the customer's review
class ReviewService:
    def __init__(self, session: Session, customer: Account, storage: ObjectStorage | None, ip: str | None = None):
        self.session, self.customer, self.storage, self.ip = session, customer, storage, ip
        self.orders = OrderRepository(session)

    def _order(self, order_id: int) -> Order:
        order = self.orders.get_owned(order_id, self.customer.id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        return order

    def _completed(self, order_id: int) -> Order:
        order = self._order(order_id)
        if order.order_status != OrderStatus.COMPLETED:
            raise AppError(409, "ORDER_NOT_COMPLETED", "Chỉ đánh giá được đơn đã hoàn thành.")
        return order

    def _prefix(self, order: Order) -> str:
        return f"orders/{order.id}/review/{self.customer.id}/"

    def _review(self, order_id: int) -> Review | None:
        return self.session.scalar(select(Review).where(Review.order_id == order_id))

    def get(self, order_id: int) -> Review:
        self._order(order_id)
        row = self._review(order_id)
        if row is None:
            raise AppError(404, "REVIEW_NOT_FOUND", "Đơn này chưa có đánh giá.")
        return row

    def request_upload(self, order_id: int, mime: str, size: int) -> tuple[str, UploadTarget]:
        order = self._completed(order_id)
        return _upload(self.storage, self._prefix(order).rstrip("/"), mime, size, MAX_PHOTO_BYTES)

    def _photos(self, order: Order, paths: list[str]) -> list[str]:
        if len(paths) > MAX_PHOTOS:
            raise AppError(422, "TOO_MANY_PHOTOS", f"Tối đa {MAX_PHOTOS} ảnh mỗi đánh giá.")
        if len(set(paths)) != len(paths):
            raise AppError(422, "INVALID_PHOTO", "Một ảnh được gửi hai lần.")
        if not paths:
            return []
        store = _storage(self.storage)
        return [_check_image(store, p, self._prefix(order), MAX_PHOTO_BYTES, "ảnh đánh giá") for p in paths]

    @staticmethod
    def _comment(comment: str | None) -> str | None:
        text = (comment or "").strip()
        if len(text) > MAX_COMMENT:
            raise AppError(422, "COMMENT_TOO_LONG", f"Nhận xét tối đa {MAX_COMMENT} ký tự.")
        return text or None

    def create(self, order_id: int, rating: int, comment: str | None, photos: list[str]) -> Review:
        order = self._completed(order_id)
        self.orders.get(order.id, lock=True)                       # a double tap: the second waits and sees the first review
        if self._review(order.id) is not None:
            raise AppError(409, "REVIEW_EXISTS", "Đơn này đã có đánh giá; hãy sửa đánh giá cũ.")
        text, paths = self._comment(comment), self._photos(order, photos)
        row = Review(order_id=order.id, customer_id=self.customer.id, rating=rating, comment=text,
                     photos=[ReviewPhoto(url=p, sort_order=i) for i, p in enumerate(paths)])
        self.session.add(row)
        self.session.flush()
        audit.record(self.session, actor_id=self.customer.id, action="REVIEW_CREATE", entity_type="review", entity_id=row.id,
                     new={"order_id": order.id, "rating": rating, "photos": len(paths)}, ip=self.ip)
        if order.assigned_staff_id:
            notifications.notify(self.session, account_id=order.assigned_staff_id, order_id=order.id, msg_code="REVIEW_POSTED",
                                 code=order.code, rating=rating)
        return row

    def update(self, order_id: int, rating: int, comment: str | None, photos: list[str]) -> Review:
        order = self._completed(order_id)
        self.orders.get(order.id, lock=True)
        row = self._review(order.id)
        if row is None:
            raise AppError(404, "REVIEW_NOT_FOUND", "Đơn này chưa có đánh giá.")
        if row.hidden_at is not None:
            raise AppError(409, "REVIEW_HIDDEN", "Đánh giá đã bị ẩn nên không sửa được. Hãy liên hệ xưởng.")
        if _now() > editable_until(row):
            raise AppError(409, "REVIEW_EDIT_CLOSED", f"Chỉ sửa được đánh giá trong {EDIT_DAYS} ngày sau khi đăng.")
        text, paths = self._comment(comment), self._photos(order, photos)
        old = {"rating": row.rating, "photos": len(row.photos)}
        dropped = [p.url for p in row.photos if p.url not in paths]
        row.rating, row.comment = rating, text
        row.photos = [ReviewPhoto(url=p, sort_order=i) for i, p in enumerate(paths)]
        row.updated_at = _now()
        self.session.flush()
        for path in dropped if self.storage is not None else []:   # photos no longer used leave storage too
            self.storage.delete(path)
        audit.record(self.session, actor_id=self.customer.id, action="REVIEW_UPDATE", entity_type="review", entity_id=row.id,
                     old=old, new={"rating": rating, "photos": len(paths)}, ip=self.ip)
        return row


def editable_until(row: Review) -> datetime:
    return row.created_at + timedelta(days=EDIT_DAYS)


def review_out(row: Review, storage: ObjectStorage | None, ttl: int = 600) -> dict[str, Any]:
    urls = sign_all(storage, [p.url for p in row.photos], ttl)
    return {"id": row.id, "order_id": row.order_id, "rating": row.rating, "comment": row.comment,
            "photos": [{"id": p.id, "path": p.url, "url": urls.get(p.url)} for p in row.photos],
            "hidden": row.hidden_at is not None, "created_at": row.created_at, "updated_at": row.updated_at,
            "editable_until": editable_until(row)}


# ============================================================================================ Manager moderation
class ReviewModeration:
    def __init__(self, session: Session, manager: Account, storage: ObjectStorage | None, ip: str | None = None):
        self.session, self.manager, self.storage, self.ip = session, manager, storage, ip

    def list(self, *, hidden: bool | None, rating: int | None, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
        q = select(Review, Order.code, Order.order_type, Account.full_name).join(Order, Order.id == Review.order_id) \
            .join(Account, Account.id == Review.customer_id)
        if hidden is not None:
            q = q.where(Review.hidden_at.is_not(None) if hidden else Review.hidden_at.is_(None))
        if rating is not None:
            q = q.where(Review.rating == rating)
        total = self.session.scalar(select(func.count()).select_from(q.subquery()))
        rows = self.session.execute(q.order_by(Review.created_at.desc(), Review.id.desc())
                                    .offset((page - 1) * page_size).limit(page_size)).all()
        urls = sign_all(self.storage, [p.url for r in rows for p in r[0].photos], 600)
        items = []
        for review, code, order_type, name in rows:
            items.append({**review_out(review, None), "order_code": code, "order_type": order_type, "customer_name": name,
                          "hidden_at": review.hidden_at,
                          "photos": [{"id": p.id, "path": p.url, "url": urls.get(p.url)} for p in review.photos]})
        return items, total or 0

    def set_hidden(self, review_id: int, hidden: bool, reason: str) -> Review:
        row = self.session.get(Review, review_id, with_for_update=True)
        if row is None:
            raise AppError(404, "REVIEW_NOT_FOUND", "Không tìm thấy đánh giá.")
        if (row.hidden_at is not None) == hidden:
            return row                                             # already so: nothing to record
        row.hidden_at = _now() if hidden else None
        self.session.flush()
        audit.record(self.session, actor_id=self.manager.id, action="REVIEW_HIDE" if hidden else "REVIEW_UNHIDE",
                     entity_type="review", entity_id=row.id, new={"order_id": row.order_id}, reason=reason, ip=self.ip)
        return row


# ============================================================================================ public reads
def public_reviews(session: Session, storage: ObjectStorage | None, *, limit: int, before_id: int | None,
                   order_type: OrderType | None) -> dict[str, Any]:
    shown = Review.hidden_at.is_(None)
    base = select(Review).join(Order, Order.id == Review.order_id).where(shown)
    if order_type is not None:
        base = base.where(Order.order_type == order_type)
    sub = base.subquery()
    stats = session.execute(select(sub.c.rating, func.count()).group_by(sub.c.rating))
    by_star = {str(n): 0 for n in range(1, 6)}
    for rating, n in stats:
        by_star[str(rating)] = n
    count = sum(by_star.values())
    average = round(sum(int(k) * v for k, v in by_star.items()) / count, 2) if count else None

    q = select(Review, Order.order_type, Account.full_name).join(Order, Order.id == Review.order_id) \
        .join(Account, Account.id == Review.customer_id).where(shown)
    if order_type is not None:
        q = q.where(Order.order_type == order_type)
    if before_id is not None:
        anchor = session.get(Review, before_id)
        if anchor is not None:
            q = q.where((Review.created_at < anchor.created_at)
                        | ((Review.created_at == anchor.created_at) & (Review.id < anchor.id)))
    rows = session.execute(q.order_by(Review.created_at.desc(), Review.id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    urls = sign_all(storage, [p.url for r in rows for p in r[0].photos])
    items = [{"id": r.id, "rating": r.rating, "comment": r.comment, "customer_name": short_name(name),
              "order_type": order_type_, "photos": [urls[p.url] for p in r.photos if p.url in urls],
              "created_at": r.created_at}
             for r, order_type_, name in rows]
    return {"average": average, "count": count, "by_star": by_star, "items": items,
            "next_before_id": items[-1]["id"] if more and items else None}


# ============================================================================================ showcase
class ShowcaseService:
    def __init__(self, session: Session, actor: Account, storage: ObjectStorage | None, ip: str | None = None):
        self.session, self.actor, self.storage, self.ip = session, actor, storage, ip

    PREFIX = "showcase/"

    def request_upload(self, mime: str, size: int) -> tuple[str, UploadTarget]:
        return _upload(self.storage, f"showcase/{self.actor.id}", mime, size, MAX_SHOWCASE_BYTES)

    def _image(self, path: str) -> str:
        return _check_image(_storage(self.storage), path, f"{self.PREFIX}{self.actor.id}/", MAX_SHOWCASE_BYTES, "ảnh showcase")

    def _get(self, post_id: int) -> ShowcasePost:
        row = self.session.get(ShowcasePost, post_id, with_for_update=True)
        if row is None:
            raise AppError(404, "SHOWCASE_NOT_FOUND", "Không tìm thấy bài showcase.")
        return row

    def list(self) -> list[ShowcasePost]:
        return list(self.session.scalars(select(ShowcasePost).order_by(ShowcasePost.sort_order, ShowcasePost.created_at.desc(),
                                                                       ShowcasePost.id.desc())))

    def create(self, data: dict[str, Any]) -> ShowcasePost:
        row = ShowcasePost(image_url=self._image(data["image_path"]), title=data["title"].strip(),
                           description=(data.get("description") or "").strip() or None, order_type=data.get("order_type"),
                           posted_by=self.actor.id, is_visible=data.get("is_visible", True),
                           sort_order=data.get("sort_order", 0))
        if not row.title:
            raise AppError(422, "VALIDATION_ERROR", "Tiêu đề không được để trống.")
        self.session.add(row)
        self.session.flush()
        audit.record(self.session, actor_id=self.actor.id, action="SHOWCASE_CREATE", entity_type="showcase_post",
                     entity_id=row.id, new={"title": row.title, "is_visible": row.is_visible}, ip=self.ip)
        return row

    def update(self, post_id: int, data: dict[str, Any]) -> ShowcasePost:
        row = self._get(post_id)
        old_image = row.image_url
        changed: dict[str, Any] = {}
        if "image_path" in data and data["image_path"] != row.image_url:
            row.image_url = self._image(data["image_path"])
            changed["image"] = True
        if "title" in data:
            title = (data["title"] or "").strip()
            if not title:
                raise AppError(422, "VALIDATION_ERROR", "Tiêu đề không được để trống.")
            row.title = changed["title"] = title
        if "description" in data:
            row.description = (data["description"] or "").strip() or None
            changed["description"] = True
        for key in ("order_type", "is_visible", "sort_order"):
            if key in data:
                setattr(row, key, data[key])
                changed[key] = data[key].value if isinstance(data[key], OrderType) else data[key]
        row.updated_at = _now()
        self.session.flush()
        if changed.get("image") and old_image != row.image_url:
            _storage(self.storage).delete(old_image)
        audit.record(self.session, actor_id=self.actor.id, action="SHOWCASE_UPDATE", entity_type="showcase_post",
                     entity_id=row.id, new=changed, ip=self.ip)
        return row

    def delete(self, post_id: int) -> None:
        row = self._get(post_id)
        path, title = row.image_url, row.title
        self.session.delete(row)
        self.session.flush()
        if self.storage is not None:
            self.storage.delete(path)
        audit.record(self.session, actor_id=self.actor.id, action="SHOWCASE_DELETE", entity_type="showcase_post",
                     entity_id=post_id, old={"title": title}, ip=self.ip)


def showcase_out(row: ShowcasePost, urls: dict[str, str], *, staff: bool) -> dict[str, Any]:
    out = {"id": row.id, "image_url": urls.get(row.image_url), "title": row.title, "description": row.description,
           "order_type": row.order_type, "sort_order": row.sort_order, "created_at": row.created_at}
    if staff:
        out.update({"image_path": row.image_url, "is_visible": row.is_visible, "posted_by": row.posted_by,
                    "updated_at": row.updated_at})
    return out


def public_showcase(session: Session, storage: ObjectStorage | None, *, order_type: OrderType | None,
                    limit: int) -> list[dict[str, Any]]:
    q = select(ShowcasePost).where(ShowcasePost.is_visible.is_(True))
    if order_type is not None:
        q = q.where(ShowcasePost.order_type == order_type)
    rows = list(session.scalars(q.order_by(ShowcasePost.sort_order, ShowcasePost.created_at.desc(), ShowcasePost.id.desc())
                                .limit(limit)))
    urls = sign_all(storage, [r.image_url for r in rows])
    return [showcase_out(r, urls, staff=False) for r in rows if r.image_url in urls]
