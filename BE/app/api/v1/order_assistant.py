"""V2 Phase C: the AI assistant on an order DRAFT (owner decision D1: the order is where the customer composes and edits).

GET  /orders/{id}/assistant/messages          the conversation of the order + flags for the Staff
POST /orders/{id}/assistant/messages          one message -> the assistant's answer (tools change the order / its sketch)
POST /orders/{id}/assistant/messages/stream   the same as Server-Sent Events (progress of each tool)

CUSTOMER only, the caller's own order, only while it is editable (DRAFT / NEED_INFO). The caps, the consent and the providers
are the studio's (U5, `GET /studio/assistant/status`); the studio assistant stays as it is until the FE moves (D1).
"""
import logging
import queue
import threading
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.schemas import ErrorOut
from app.api.v1.orders import optional_storage
from app.api.v1.studio import STREAM_PING_S, MessageOut, ToolCallOut, _sse, assistant_providers
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.db.session import _factory
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.models.order import Order
from app.services.ai.assistant import AssistantService

router = APIRouter(tags=["Order assistant (V2)"])
log = logging.getLogger(__name__)
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
_ERR = {404: {"model": ErrorOut, "description": "ORDER_NOT_FOUND"},
        409: {"model": ErrorOut, "description": "ORDER_NOT_EDITABLE / STALE_REVISION / AI_TURN_IN_PROGRESS"},
        422: {"model": ErrorOut, "description": "AI_CONSENT_REQUIRED / EMPTY_MESSAGE"},
        429: {"model": ErrorOut, "description": "AI_DAILY_LIMIT / RATE_LIMITED"},
        503: {"model": ErrorOut, "description": "AI_UNAVAILABLE / AI_DISABLED / AI_BUDGET_EXHAUSTED"}}


class Selection(BaseModel):
    stroke_ids: list[str] = Field(default_factory=list, max_length=500)
    word_ids: list[str] = Field(default_factory=list, max_length=500)
    line_ids: list[str] = Field(default_factory=list, max_length=200, description="V2 Phase F")
    paragraph_ids: list[str] = Field(default_factory=list, max_length=100, description="V2 Phase F")


class OrderMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    ai_consent: bool = Field(default=False, description=(
        "Bắt buộc true ở tin nhắn đầu tiên của đơn: khách đồng ý gửi tin nhắn và nội dung đơn (chữ, vật tư, số đo phác thảo) "
        "cho nhà cung cấp AI bên ngoài. Ảnh không bao giờ được gửi."))
    base_revision_id: int | None = Field(default=None, description=(
        "Revision phác thảo khách đang nhìn. Khác bản hiện tại → 409 STALE_REVISION, không gọi AI."))
    selection: Selection | None = Field(default=None, description=(
        "Nét / từ khách đang chọn trên canvas. Có selection thì trợ lý chỉ được sửa trong vùng đó."))
    client_ref: str | None = Field(default=None, max_length=64, description=(
        "Id FE tự sinh cho tin nhắn (vd UUID). Gửi lại cùng id → trả lại câu trả lời đã lưu (`replayed: true`), không gọi AI lần hai."))


class OrderTurnOut(BaseModel):
    user: MessageOut
    reply: MessageOut
    replayed: bool
    sketch_revision_id: int | None = Field(description="Revision phác thảo hiện tại sau lượt này (tải lại GET /orders/{id}/sketch nếu khác)")


class OrderConversationOut(BaseModel):
    consented_at: datetime | None
    flags: list[dict[str, Any]]
    messages: list[MessageOut]


def _assistant(session: SessionDep, customer: CustomerDep, request: Request,
               storage: Annotated[ObjectStorage | None, Depends(optional_storage)],
               providers=Depends(assistant_providers)) -> AssistantService:
    return AssistantService(session, customer, None, providers, storage=storage, ip=client_ip(request))


Assistant = Annotated[AssistantService, Depends(_assistant)]


def message_out(m, calls) -> MessageOut:
    return MessageOut(id=m.id, role=m.role, content=m.content, status=m.status, provider=m.provider, model=m.model,
                      tool_calls=[ToolCallOut(name=c.name, ok=c.ok, revision_id=c.sketch_revision_id) for c in calls],
                      created_at=m.created_at)


def _turn_out(a: AssistantService, order_id: int, out: dict[str, Any]) -> OrderTurnOut:
    order = a.session.get(Order, order_id)
    a.session.refresh(order)
    return OrderTurnOut(user=message_out(out["user"], []), reply=message_out(out["reply"], out["tool_calls"]),
                        replayed=out["replayed"], sketch_revision_id=order.current_sketch_revision_id)


def _owned(a: AssistantService, order_id: int) -> None:
    from app.services.sketch_work import SketchWorkService
    SketchWorkService(a.session, a.customer, None).order(order_id)          # 404 for another customer's order


@router.get("/orders/{order_id}/assistant/messages", response_model=OrderConversationOut, responses=_ERR,
            summary="V2 Hội thoại với trợ lý AI của đơn")
def messages(order_id: int, assistant: Assistant) -> OrderConversationOut:
    _owned(assistant, order_id)
    sess = assistant.session_of_order(order_id)
    return OrderConversationOut(consented_at=sess.consented_at if sess else None, flags=(sess.flags or []) if sess else [],
                                messages=[message_out(m, c) for m, c in assistant.session_messages(sess)])


@router.post("/orders/{order_id}/assistant/messages", response_model=OrderTurnOut, responses=_ERR,
             summary="V2 Nhắn trợ lý AI của đơn: trợ lý sửa đơn / phác thảo bằng công cụ của hệ thống",
             description=("Mỗi sửa nét của trợ lý là một revision `author = AI` (hoàn tác được). Khi mọi nhà cung cấp AI đều lỗi, "
                          "trả 200 với `reply.status = FAILED`. `tool_calls[].revision_id` là id revision phác thảo trợ lý tạo."))
def send_message(order_id: int, body: OrderMessageIn, assistant: Assistant,
                 _limit: Annotated[None, Depends(rate_limit("studio_ai", 10, 60))]) -> OrderTurnOut:
    # the "studio_ai" bucket is shared with the studio and counted after the role check (a refused role never uses it)
    out = assistant.send_order(order_id, body.text, consent=body.ai_consent, base_revision_id=body.base_revision_id,
                               selection=body.selection.model_dump() if body.selection else None, client_ref=body.client_ref)
    return _turn_out(assistant, order_id, out)


@router.post("/orders/{order_id}/assistant/messages/stream",
             responses={200: {"content": {"text/event-stream": {}}}, **_ERR},
             summary="V2 Nhắn trợ lý AI của đơn, nhận tiến trình tức thời (Server-Sent Events)",
             description=("Như `POST /orders/{id}/assistant/messages` nhưng trả `text/event-stream`: `user_saved`, `provider`, "
                          "`tool` (kèm `revision_id` phác thảo), `failover`, rồi `reply` (đúng `OrderTurnOut`) hoặc `error`; cuối "
                          "cùng `done`. Lỗi trước khi gọi mô hình vẫn trả HTTP lỗi thường."))
def send_message_stream(order_id: int, body: OrderMessageIn, session: SessionDep, assistant: Assistant,
                        _limit: Annotated[None, Depends(rate_limit("studio_ai", 10, 60))]) -> StreamingResponse:
    assistant.lock_order(order_id)
    if assistant.replay(order_id, body.client_ref) is None:
        assistant.precheck_order(order_id, body.text, consent=body.ai_consent, base_revision_id=body.base_revision_id)
    customer_id, storage, ip, providers = assistant.customer.id, assistant._storage, assistant._ip, assistant._providers
    session.commit()                                     # frees the order row and the lock before the worker takes them
    events: queue.Queue = queue.Queue()

    def work() -> None:
        s = _factory()()
        try:
            a = AssistantService(s, s.get(Account, customer_id), None, providers, storage=storage, ip=ip)
            out = a.send_order(order_id, body.text, consent=body.ai_consent, base_revision_id=body.base_revision_id,
                               selection=body.selection.model_dump() if body.selection else None, client_ref=body.client_ref,
                               on_event=lambda name, data: events.put((name, data)))
            turn = _turn_out(a, order_id, out)
            s.commit()
            events.put(("reply", turn.model_dump(mode="json")))
        except AppError as exc:
            s.rollback()
            events.put(("error", {"code": exc.code, "message": exc.message}))
        except Exception:
            s.rollback()
            log.exception("order assistant stream failed (order %s)", order_id)
            events.put(("error", {"code": "INTERNAL_ERROR", "message": "Có lỗi khi xử lý tin nhắn. Vui lòng thử lại."}))
        finally:
            s.close()
            events.put(None)

    threading.Thread(target=work, name=f"order-ai-{order_id}", daemon=True).start()

    def stream():
        yield "retry: 5000\n\n"
        while True:
            try:
                item = events.get(timeout=STREAM_PING_S)
            except queue.Empty:
                yield ": ping\n\n"
                continue
            if item is None:
                yield _sse("done", {})
                return
            yield _sse(*item)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

