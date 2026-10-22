"""The chat inbox: one row per order that has messages, plus the unread badge. Replaces calling /messages once per order.

Same visibility as the per-order chat: a customer sees their own submitted orders, a Staff the orders assigned to them plus the
unclaimed pool, a Manager every submitted order. TECHNICAL_STAFF and ADMIN have no chat."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.staff_schemas import ConversationOut, ConversationPage, LastMessageOut, UnreadCountOut
from app.models.account import Account, RoleCode
from app.services.messages import MessageService

customer_router = APIRouter(prefix="/me/conversations", tags=["Messages"])
workshop_router = APIRouter(prefix="/workshop/conversations", tags=["Messages"])

CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
WorkshopDep = Annotated[Account, Depends(require_roles(RoleCode.STAFF.value, RoleCode.MANAGER.value))]


def _page(session, actor: Account, request: Request, page: int, page_size: int) -> ConversationPage:
    rows, total = MessageService(session, actor, None, client_ip(request)).conversations(page, page_size)
    items = [ConversationOut(order_id=r["order_id"], code=r["code"], order_type=r["order_type"], order_status=r["order_status"],
                             customer_name=r["customer_name"], unread=r["unread"],
                             last_message=LastMessageOut(body=r["last_body"], kind=r["last_kind"],
                                                         has_attachment=bool(r["last_has_attachment"]),
                                                         created_at=r["last_created_at"], mine=bool(r["last_mine"])))
             for r in rows]
    return ConversationPage(items=items, total=total, page=page, page_size=page_size)


@customer_router.get("", response_model=ConversationPage,
                     summary="Danh sách cuộc chat của khách (mỗi đơn đã có tin nhắn một dòng), mới nhất trước")
def my_conversations(session: SessionDep, customer: CustomerDep, request: Request, page: int = Query(1, ge=1),
                     page_size: int = Query(20, ge=1, le=100)) -> ConversationPage:
    return _page(session, customer, request, page, page_size)


@customer_router.get("/unread-count", response_model=UnreadCountOut,
                     summary="Số tin chưa đọc của khách trên mọi đơn (cho badge nút chat; một truy vấn đếm)")
def my_unread(session: SessionDep, customer: CustomerDep, request: Request) -> UnreadCountOut:
    return UnreadCountOut(unread=MessageService(session, customer, None, client_ip(request)).unread_total())


@workshop_router.get("", response_model=ConversationPage,
                     summary="Danh sách cuộc chat phía xưởng (Staff: đơn của mình + đơn chưa ai nhận; Manager: mọi đơn), mới nhất trước")
def workshop_conversations(session: SessionDep, actor: WorkshopDep, request: Request, page: int = Query(1, ge=1),
                           page_size: int = Query(20, ge=1, le=100)) -> ConversationPage:
    return _page(session, actor, request, page, page_size)


@workshop_router.get("/unread-count", response_model=UnreadCountOut,
                     summary="Số tin chưa đọc phía xưởng (cho badge nút chat của Staff / Manager)")
def workshop_unread(session: SessionDep, actor: WorkshopDep, request: Request) -> UnreadCountOut:
    return UnreadCountOut(unread=MessageService(session, actor, None, client_ip(request)).unread_total())
