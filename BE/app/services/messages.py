"""Order chat between the customer and the workshop: UC-27 (FR-16).

Participants: the order's customer, the assigned Staff and any Manager. A Staff who has not claimed the
order may read it (pool) but not post. Images are uploaded straight to storage (signed URL, same pattern
as order inputs) and referenced by path; the path must live under the sender's own folder.
"""
from __future__ import annotations  # methods named `list` would otherwise shadow the builtin in later annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.integrations.storage import ObjectStorage, UploadTarget
from app.models.account import Account, RoleCode
from app.models.order import Order, OrderStatus
from app.models.sketch import Message
from app.repositories.orders import OrderRepository
from app.repositories.workshop import MessageRepository
from app.services import notifications
from app.services.handwriting_image import sniff_mime
from app.services.workshop_access import WorkshopAccess

MAX_BODY = 2000
MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
IMAGE_MIMES = {"image/jpeg": "jpg", "image/png": "png"}
CLOSED = {OrderStatus.REJECTED, OrderStatus.CANCELLED}


class MessageService:
    def __init__(self, session: Session, actor: Account, storage: ObjectStorage | None, ip: str | None = None):
        self.session, self.actor, self.storage, self.ip = session, actor, storage, ip
        self.repo = MessageRepository(session)
        self.orders = OrderRepository(session)

    @property
    def role(self) -> str:
        return self.actor.role.code

    def _order(self, order_id: int, *, write: bool) -> Order:
        if self.role == RoleCode.CUSTOMER.value:
            order = self.orders.get_owned(order_id, self.actor.id)
            if order is None:
                raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
            if order.order_status == OrderStatus.DRAFT:
                raise AppError(409, "ORDER_NOT_SUBMITTED", "Chỉ trao đổi được sau khi đã gửi đơn.")
        else:
            order = WorkshopAccess(self.session, self.actor).order(order_id)       # 404 for anyone without access
            if write and not (self.role == RoleCode.MANAGER.value or order.assigned_staff_id == self.actor.id):
                raise AppError(409, "ORDER_NOT_CLAIMED", "Hãy nhận đơn trước khi nhắn tin cho khách.")
        if write and order.order_status in CLOSED:
            raise AppError(409, "ORDER_CLOSED", "Đơn đã đóng, không thể nhắn thêm.")
        return order

    def _storage(self) -> ObjectStorage:
        if self.storage is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        return self.storage

    # ---- attachments ----
    def request_upload(self, order_id: int, mime: str, size: int) -> tuple[str, UploadTarget]:
        order = self._order(order_id, write=True)
        if mime not in IMAGE_MIMES:
            raise AppError(422, "UNSUPPORTED_FILE", "Chỉ đính kèm ảnh jpg hoặc png.")
        if size > MAX_ATTACHMENT_BYTES:
            raise AppError(422, "FILE_TOO_LARGE", "Ảnh đính kèm tối đa 5 MB.")
        path = f"orders/{order.id}/messages/{self.actor.id}/{uuid.uuid4().hex}.{IMAGE_MIMES[mime]}"
        return path, self._storage().create_upload_target(path)

    def _validate_attachments(self, order: Order, items: list[dict[str, str]]) -> list[dict[str, Any]]:
        if len(items) > MAX_ATTACHMENTS:
            raise AppError(422, "TOO_MANY_ATTACHMENTS", f"Tối đa {MAX_ATTACHMENTS} ảnh mỗi tin nhắn.")
        prefix = f"orders/{order.id}/messages/{self.actor.id}/"
        out = []
        for it in items:
            path = it.get("path", "")
            if not path.startswith(prefix) or ".." in path:
                raise AppError(422, "INVALID_ATTACHMENT", "Đường dẫn ảnh đính kèm không hợp lệ.")
            data = self._storage().read(path)
            if data is None:
                raise AppError(422, "ATTACHMENT_NOT_UPLOADED", "Ảnh đính kèm chưa được tải lên.")
            mime = sniff_mime(data)
            if mime not in IMAGE_MIMES or len(data) > MAX_ATTACHMENT_BYTES:
                self._storage().delete(path)
                raise AppError(422, "INVALID_ATTACHMENT", "Ảnh đính kèm phải là jpg/png ≤ 5 MB.")
            out.append({"path": path, "mime": mime})
        return out

    # ---- chat ----
    def post(self, order_id: int, body: str | None, attachments: list[dict[str, str]]) -> Message:
        order = self._order(order_id, write=True)
        text = (body or "").strip()
        if len(text) > MAX_BODY:
            raise AppError(422, "MESSAGE_TOO_LONG", f"Tin nhắn tối đa {MAX_BODY} ký tự.")
        files = self._validate_attachments(order, attachments)
        if not text and not files:
            raise AppError(422, "EMPTY_MESSAGE", "Tin nhắn trống.")
        row = self.repo.add(Message(order_id=order.id, sender_id=self.actor.id, body=text or None, attachments=files))
        recipient = order.customer_id if self.role != RoleCode.CUSTOMER.value else order.assigned_staff_id
        if recipient:
            notifications.notify(account_id=recipient, order_id=order.id, msg_code="MESSAGE", code=order.code)
        return row

    def list(self, order_id: int, page: int, page_size: int) -> tuple[list[Message], int, int]:
        order = self._order(order_id, write=False)
        rows, total = self.repo.list(order.id, offset=(page - 1) * page_size, limit=page_size)
        return rows, total, self.repo.unread_count(order.id, self.actor.id)

    def mark_read(self, order_id: int) -> int:
        order = self._order(order_id, write=False)
        return self.repo.mark_read(order.id, self.actor.id, datetime.now(timezone.utc))

    def attachment_urls(self, row: Message) -> list[dict[str, str]]:
        if self.storage is None:
            return []
        return [{"url": self.storage.create_download_url(a["path"], 600), "mime": a["mime"]} for a in row.attachments]
