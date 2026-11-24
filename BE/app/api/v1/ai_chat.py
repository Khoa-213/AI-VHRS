"""The AI chat data policy, the customer's consent to it, and the list of the customer's AI conversations (migration 0031).

GET    /privacy-policy/ai-chat      the policy in force (public)
GET    /me/assistant/consent        has the customer agreed to the version in force
POST   /me/assistant/consent        agree to that version {policy_version}
DELETE /me/assistant/consent        take the consent back: the assistant refuses until the customer agrees again
GET    /me/assistant/sessions       every AI conversation of the customer, most recently used first (sidebar)
The conversations of one order, renaming and deleting are under /orders/{id}/assistant/sessions (order_assistant.py).
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, client_ip, require_roles
from app.core.errors import AppError
from app.models.account import Account, RoleCode
from app.services.ai import chat_policy, chat_sessions

router = APIRouter(tags=["AI chat"])
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]


class PolicySectionOut(BaseModel):
    title: str = Field(description="đề mục, vd '1. Phạm vi hỗ trợ của trợ lý AI'")
    body: str = Field(description="đoạn văn cách nhau bằng dòng trống, gạch đầu dòng '- '")


class AiChatPolicyOut(BaseModel):
    title: str
    version: str = Field(description="phiên bản khách phải đồng ý (gửi lại trong POST /me/assistant/consent)")
    body: str = Field(description="toàn văn (xuống dòng thật, hiện với white-space: pre-line); mục 7 ghi nhà cung cấp AI đang dùng")
    sections: list[PolicySectionOut] = Field(description="toàn văn tách theo đề mục, để hiện đề mục đậm")
    providers: list[str] = Field(description="nhà cung cấp AI đang bật, vd ['Google (Gemini)']")
    retention_days: int = Field(description="số ngày sau khi đơn hoàn tất / huỷ thì nội dung chat bị xoá")
    retention_enforced: bool = Field(description="việc tự xoá đang bật (system_settings.photo_purge_enabled)")
    is_draft: bool = Field(description="false: văn bản đã được chủ dự án duyệt (2026-11-24)")


class ConsentOut(BaseModel):
    policy_version: str = Field(description="phiên bản chính sách đang áp dụng")
    accepted: bool = Field(description="khách đã đồng ý đúng phiên bản này và chưa rút lại")
    accepted_at: datetime | None


class ConsentIn(BaseModel):
    policy_version: str = Field(min_length=1, max_length=20, description="phiên bản khách vừa đọc (từ GET /privacy-policy/ai-chat)")


class SessionItemOut(BaseModel):
    id: int
    order_id: int
    order_code: str
    order_type: str
    order_status: str
    title: str | None = Field(description="tên khách đặt, hoặc câu đầu tiên của cuộc chat (title_is_custom = false)")
    title_is_custom: bool
    preview: str | None = Field(description="tin cuối của cuộc chat, tối đa 140 ký tự")
    message_count: int
    created_at: datetime
    last_message_at: datetime | None
    can_chat: bool = Field(description="đơn còn sửa được (DRAFT / NEED_INFO): nhắn tiếp được; đơn đã gửi: chỉ xem")
    can_delete: bool = Field(description="đơn còn là bản nháp (DRAFT): khách xoá được cuộc chat")


class SessionPageOut(BaseModel):
    items: list[SessionItemOut]
    next_cursor: str | None = Field(description="gửi lại trong `cursor` để lấy trang sau; null: hết")


def _consent(session, customer: Account) -> ConsentOut:
    return ConsentOut(**chat_policy.status(session, customer.id))


@router.get("/privacy-policy/ai-chat", response_model=AiChatPolicyOut,
            summary="Chính sách dữ liệu khi chat với trợ lý AI (không cần đăng nhập)")
def ai_chat_policy(session: SessionDep) -> AiChatPolicyOut:
    return AiChatPolicyOut(**chat_policy.current(session))


@router.get("/me/assistant/consent", response_model=ConsentOut, summary="Khách đã đồng ý chính sách dữ liệu chat AI chưa")
def consent(session: SessionDep, customer: CustomerDep) -> ConsentOut:
    return _consent(session, customer)


@router.post("/me/assistant/consent", response_model=ConsentOut,
             summary="Đồng ý chính sách dữ liệu chat AI (một lần cho tài khoản; hỏi lại khi đổi phiên bản)",
             description="`policy_version` phải đúng phiên bản đang áp dụng, khác thì `409 POLICY_VERSION_CHANGED` "
                         "(`details.policy_version`: phiên bản mới, tải lại chính sách cho khách đọc).")
def give_consent(body: ConsentIn, session: SessionDep, customer: CustomerDep, request: Request) -> ConsentOut:
    current = chat_policy.version(session)
    if body.policy_version != current:
        raise AppError(409, "POLICY_VERSION_CHANGED", "Chính sách vừa được cập nhật; hãy đọc bản mới rồi đồng ý.",
                       {"policy_version": current})
    chat_policy.accept(session, customer, current, ip=client_ip(request))
    return _consent(session, customer)


@router.delete("/me/assistant/consent", response_model=ConsentOut,
               summary="Rút lại đồng ý: trợ lý AI ngừng trả lời cho tới khi khách đồng ý lại (gọi lại không lỗi)")
def withdraw_consent(session: SessionDep, customer: CustomerDep, request: Request) -> ConsentOut:
    chat_policy.withdraw(session, customer, ip=client_ip(request))
    return _consent(session, customer)


@router.get("/me/assistant/sessions", response_model=SessionPageOut,
            summary="Mọi cuộc chat với trợ lý AI của khách, mới dùng gần nhất trước (thanh bên kiểu ChatGPT)")
def my_sessions(session: SessionDep, customer: CustomerDep, limit: Annotated[int, Query(ge=1, le=100)] = 20,
                cursor: Annotated[str | None, Query(max_length=64)] = None) -> SessionPageOut:
    page = chat_sessions.of_customer(session, customer.id, limit=limit, cursor=cursor)
    return SessionPageOut(items=[SessionItemOut(**i) for i in page["items"]], next_cursor=page["next_cursor"])
