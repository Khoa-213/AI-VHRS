"""UC-27 (FR-16): chat inside an order between the customer, the assigned Staff and the Manager.

The Manager takes part in a conversation to resolve complaints. TECHNICAL_STAFF and ADMIN have no access."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.staff_schemas import (AttachmentOut, MessageIn, MessageOut, MessagePage, MessageUploadIn,
                                   MessageUploadOut)
from app.api.v1.orders import optional_storage
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.models.sketch import Message
from app.services.messages import MessageService

router = APIRouter(prefix="/orders/{order_id}/messages", tags=["Messages"])
Reader = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value, RoleCode.STAFF.value,
                                                  RoleCode.MANAGER.value))]
Writer = Reader


def _svc(session: SessionDep, actor: Reader, request: Request,
         storage: Annotated[ObjectStorage | None, Depends(optional_storage)]) -> MessageService:
    return MessageService(session, actor, storage, client_ip(request))


def _writer_svc(session: SessionDep, actor: Writer, request: Request,
                storage: Annotated[ObjectStorage | None, Depends(optional_storage)]) -> MessageService:
    return MessageService(session, actor, storage, client_ip(request))


Svc = Annotated[MessageService, Depends(_svc)]                  # read
WriteSvc = Annotated[MessageService, Depends(_writer_svc)]      # post / upload / mark read


def _out(svc: MessageService, row: Message) -> MessageOut:
    return MessageOut(id=row.id, sender_id=row.sender_id, mine=row.sender_id == svc.actor.id, body=row.body,
                      attachments=[AttachmentOut(**a) for a in svc.attachment_urls(row)], read_at=row.read_at,
                      created_at=row.created_at)


@router.get("", response_model=MessagePage, summary="Tin nhắn của đơn (cũ → mới) + số tin chưa đọc")
def list_messages(order_id: int, svc: Svc, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)) -> MessagePage:
    rows, total, unread = svc.list(order_id, page, page_size)
    return MessagePage(items=[_out(svc, r) for r in rows], total=total, page=page, page_size=page_size, unread=unread)


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED, summary="Gửi tin nhắn (có thể kèm ảnh)")
def post_message(order_id: int, body: MessageIn, svc: WriteSvc) -> MessageOut:
    return _out(svc, svc.post(order_id, body.body, [a.model_dump() for a in body.attachments]))


@router.post("/upload-url", response_model=MessageUploadOut, status_code=status.HTTP_201_CREATED,
             summary="Xin liên kết tải ảnh đính kèm (jpg/png ≤ 5 MB); sau đó gửi `path` trong tin nhắn")
def upload_url(order_id: int, body: MessageUploadIn, svc: WriteSvc) -> MessageUploadOut:
    path, target = svc.request_upload(order_id, body.mime_type, body.size_bytes)
    return MessageUploadOut(path=path, upload_url=target.url, method=target.method, expires_in=target.expires_in)


@router.post("/read", status_code=status.HTTP_200_OK, summary="Đánh dấu đã đọc các tin của bên kia")
def mark_read(order_id: int, svc: WriteSvc) -> dict[str, int]:
    return {"marked": svc.mark_read(order_id)}
