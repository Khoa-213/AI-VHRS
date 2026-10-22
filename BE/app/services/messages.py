"""Order chat between the customer and the workshop: UC-27 (FR-16).

Participants: the order's customer, the assigned Staff and any Manager. A Staff who has not claimed the
order may read it (pool) but not post. Images are uploaded straight to storage (signed URL, same pattern
as order inputs) and referenced by path; the path must live under the sender's own folder.
"""
from __future__ import annotations  # methods named `list` would otherwise shadow the builtin in later annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.integrations.storage import ObjectStorage, UploadTarget
from app.models.account import Account, AccountStatus, RoleCode
from app.models.order import Order, OrderStatus
from app.models.sketch import Message
from app.repositories.orders import OrderRepository
from app.repositories.workshop import ConversationRepository, MessageRepository
from app.services import notifications
from app.services.handwriting_image import sniff_mime
from app.services.workshop_access import WorkshopAccess

MAX_BODY = 2000
MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
IMAGE_MIMES = {"image/jpeg": "jpg", "image/png": "png"}
CLOSED = {OrderStatus.REJECTED, OrderStatus.CANCELLED}        # COMPLETED stays open on purpose: the customer can still complain
CARD_WINDOW = timedelta(minutes=10)                              # one order card per order per window (anti-spam)


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
    def post(self, order_id: int, body: str | None, attachments: list[dict[str, str]],
             kind: str = "TEXT") -> tuple[Message, Order, bool]:
        """Returns (message, order, created). `created` is False when an order card was asked for again within the window and
        the earlier card is handed back instead of a new one."""
        order = self._order(order_id, write=True)
        if kind == "ORDER_CARD":
            return self._post_card(order, body, attachments)
        text = (body or "").strip()
        if len(text) > MAX_BODY:
            raise AppError(422, "MESSAGE_TOO_LONG", f"Tin nhắn tối đa {MAX_BODY} ký tự.")
        files = self._validate_attachments(order, attachments)
        if not text and not files:
            raise AppError(422, "EMPTY_MESSAGE", "Tin nhắn trống.")
        row = self.repo.add(Message(order_id=order.id, sender_id=self.actor.id, body=text or None, attachments=files))
        self._notify(order)
        return row, order, True

    def _post_card(self, order: Order, body: str | None, attachments: list[dict[str, str]]) -> tuple[Message, Order, bool]:
        if self.role != RoleCode.CUSTOMER.value:
            raise AppError(403, "CARD_CUSTOMER_ONLY", "Chỉ khách hàng gửi được thẻ đơn hàng.")
        if (body or "").strip() or attachments:
            raise AppError(422, "INVALID_CARD", "Thẻ đơn hàng không kèm nội dung hoặc ảnh.")
        self.orders.get(order.id, lock=True)                      # two simultaneous requests (a double tap) take turns: one card
        recent = self.repo.recent_card(order.id, datetime.now(timezone.utc) - CARD_WINDOW)
        if recent is not None:
            return recent, order, False                           # asked again too soon: the same card, no new message, no new alert
        row = self.repo.add(Message(order_id=order.id, sender_id=self.actor.id, body=None, attachments=[], kind="ORDER_CARD"))
        self._notify(order)
        return row, order, True

    def _notify(self, order: Order) -> None:
        if self.role != RoleCode.CUSTOMER.value:
            notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="MESSAGE", code=order.code)
        elif order.assigned_staff_id:
            notifications.notify(account_id=order.assigned_staff_id, order_id=order.id, msg_code="MESSAGE", code=order.code)
        else:
            # Nobody has claimed the order, so there is no assigned Staff to tell. Every active Manager is told instead (they may
            # answer any order); otherwise the customer's message would sit unseen until someone happened to open the pool.
            for manager_id in self._managers():
                notifications.notify(account_id=manager_id, order_id=order.id, msg_code="MESSAGE_UNCLAIMED", code=order.code)

    def _managers(self) -> list[int]:
        return list(self.session.scalars(select(Account.id).join(Account.role).where(
            Account.status == AccountStatus.ACTIVE, Account.role.has(code=RoleCode.MANAGER.value))))

    def list(self, order_id: int, page: int, page_size: int) -> tuple[list[Message], int, int, Order]:
        order = self._order(order_id, write=False)
        rows, total = self.repo.list(order.id, offset=(page - 1) * page_size, limit=page_size)
        return rows, total, self.repo.unread_count(order.id, self.actor.id), order

    def mark_read(self, order_id: int) -> int:
        order = self._order(order_id, write=False)
        return self.repo.mark_read(order.id, self.actor.id, datetime.now(timezone.utc))

    def attachment_urls(self, row: Message) -> list[dict[str, str]]:
        if self.storage is None:
            return []
        return [{"url": self.storage.create_download_url(a["path"], 600), "mime": a["mime"]} for a in row.attachments]

    # ---- the chat lists (no order id: the caller's whole inbox) ----
    def conversations(self, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
        rows, total = ConversationRepository(self.session).page(self.role, self.actor.id, offset=(page - 1) * page_size,
                                                                 limit=page_size)
        if self.role == RoleCode.CUSTOMER.value:
            for r in rows:
                r["customer_name"] = None                         # the customer knows who they are
        return rows, total

    def unread_total(self) -> int:
        return ConversationRepository(self.session).unread_total(self.role, self.actor.id)

