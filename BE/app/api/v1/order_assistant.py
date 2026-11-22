"""V2 Phase C: the AI assistant on an order DRAFT (owner decision D1: the order is where the customer composes and edits).

GET  /orders/{id}/assistant/messages          the conversation of the order + flags for the Staff
POST /orders/{id}/assistant/messages          one message -> the assistant's answer (tools change the order / its sketch)
POST /orders/{id}/assistant/messages/stream   the same as Server-Sent Events (progress of each tool)
GET  /orders/{id}/assistant/proposals          the assistant's proposals on the order (migration 0029)
POST /orders/{id}/assistant/proposals/{pid}/apply    write a proposal onto the order
POST /orders/{id}/assistant/proposals/{pid}/reject   dismiss it

Migration 0029 (owner request 2026-11-22): the assistant no longer changes the order; each turn that would change it returns a
proposal, and the order changes only when the customer applies it.

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
from app.services.ai.proposals import ProposalService

router = APIRouter(tags=["Order assistant (V2)"])
log = logging.getLogger(__name__)
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
_ERR = {404: {"model": ErrorOut, "description": "ORDER_NOT_FOUND"},
        409: {"model": ErrorOut, "description": "ORDER_NOT_EDITABLE / STALE_REVISION / AI_TURN_IN_PROGRESS / PROPOSAL_STALE / "
                                                "PROPOSAL_NOT_PENDING"},
        422: {"model": ErrorOut, "description": "AI_CONSENT_REQUIRED / EMPTY_MESSAGE"},
        429: {"model": ErrorOut, "description": "AI_DAILY_LIMIT / RATE_LIMITED"},
        503: {"model": ErrorOut, "description": "AI_UNAVAILABLE / AI_DISABLED / AI_BUDGET_EXHAUSTED"}}


class Selection(BaseModel):
    stroke_ids: list[str] = Field(default_factory=list, max_length=500)
    word_ids: list[str] = Field(default_factory=list, max_length=500)
    line_ids: list[str] = Field(default_factory=list, max_length=200, description="V2 Phase F")
    paragraph_ids: list[str] = Field(default_factory=list, max_length=100, description="V2 Phase F")


class OrderMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    ai_consent: bool = Field(default=False, description=(
        "Bắt buộc true ở tin nhắn đầu tiên của đơn: khách đồng ý gửi tin nhắn và nội dung đơn (chữ, vật tư, số đo phác thảo) "
        "cho nhà cung cấp AI bên ngoài. Ảnh không bao giờ được gửi."))
    base_revision_id: int | None = Field(default=None, description=(
        "Revision phác thảo khách đang nhìn. Khác bản hiện tại → 409 STALE_REVISION, không gọi AI."))
    selection: Selection | None = Field(default=None, description=(
        "Nét / từ khách đang chọn trên canvas. Có selection thì trợ lý chỉ được sửa trong vùng đó."))
    client_ref: str | None = Field(default=None, max_length=64, description=(
        "Id FE tự sinh cho tin nhắn (vd UUID). Gửi lại cùng id → trả lại câu trả lời đã lưu (`replayed: true`), không gọi AI lần hai."))
    base_proposal_id: int | None = Field(default=None, description=(
        "0029: tiếp tục từ đề xuất này (chưa áp dụng); đề xuất mới gồm cả phần cũ. Bỏ trống: tự tiếp tục đề xuất PENDING mới "
        "nhất còn áp dụng được. Đề xuất đã áp dụng / bỏ qua → 409 PROPOSAL_NOT_PENDING; đơn đã đổi → 409 PROPOSAL_STALE."))
    from_order: bool = Field(default=False, description="0029: true = bắt đầu từ đơn hiện tại, bỏ qua các đề xuất đang chờ")


class ProposalOut(BaseModel):
    id: int
    message_id: int = Field(description="tin trả lời của trợ lý chứa đề xuất này")
    parent_proposal_id: int | None = Field(description="đề xuất chưa áp dụng mà đề xuất này làm tiếp")
    status: str = Field(description="PENDING | APPLIED | REJECTED")
    applicable: bool = Field(description="bấm Áp dụng được ngay bây giờ")
    blocked_reason: str | None = Field(description="vì sao không áp dụng được: APPLIED | REJECTED | ORDER_NOT_EDITABLE | "
                                                   "ORDER_CHANGED (đơn đã đổi sau khi trợ lý đề xuất)")
    changes: list[dict[str, Any]] = Field(description=(
        "[{field, before, after}] theo thứ tự các bước tạo đơn. field: text | template_id | handwriting_style_id | "
        "font_size_mm | alignment | layout | paper_type_id | pen_type_id | ink_color_id | workshop_suggest_materials | "
        "quantity | physical_watermark | restoration_mode | customer_note | sketch. Vật tư / mẫu chữ có dạng {id, name}; "
        "sketch là id revision trước / sau"))
    estimate: dict[str, Any] | None = Field(description="giá ước tính sau khi áp dụng {price_min, price_max, currency, is_estimate}")
    sketch_revision_id: int | None = Field(description=(
        "revision phác thảo đơn sẽ hiển thị sau khi áp dụng (null: phác thảo không đổi). Ảnh: GET "
        "/orders/{id}/sketch/preview?revision_id=...&page=1; dữ liệu nét: GET /orders/{id}/sketch?revision_id=..."))
    created_at: datetime
    decided_at: datetime | None


class OrderMessageOut(MessageOut):
    proposal: ProposalOut | None = None


class ApplyOut(BaseModel):
    proposal: ProposalOut
    current_sketch_revision_id: int | None = Field(description="revision phác thảo hiện tại của đơn sau khi áp dụng")
    estimate: dict[str, Any] | None = Field(description="giá ước tính của đơn sau khi áp dụng (tính lại theo bảng giá hiện hành)")


class OrderTurnOut(BaseModel):
    user: OrderMessageOut
    reply: OrderMessageOut
    replayed: bool
    sketch_revision_id: int | None = Field(description=(
        "Revision phác thảo hiện tại của đơn sau lượt này. Từ 0029 trợ lý không đổi đơn nên thường không đổi; phác thảo "
        "mới nằm trong `proposal.sketch_revision_id`"))
    proposal: ProposalOut | None = Field(default=None, description="0029: đề xuất của lượt này (null: trợ lý chỉ trả lời / đọc)")


class OrderConversationOut(BaseModel):
    consented_at: datetime | None
    flags: list[dict[str, Any]]
    messages: list[OrderMessageOut]
    proposals: list[ProposalOut] = Field(default=[], description="0029: mọi đề xuất của đơn, cũ trước")


def _assistant(session: SessionDep, customer: CustomerDep, request: Request,
               storage: Annotated[ObjectStorage | None, Depends(optional_storage)],
               providers=Depends(assistant_providers)) -> AssistantService:
    return AssistantService(session, customer, None, providers, storage=storage, ip=client_ip(request))


Assistant = Annotated[AssistantService, Depends(_assistant)]


def proposal_out(props: ProposalService, order: Order, p, now_hash: str | None = None) -> ProposalOut:
    ok, why = props.applicability(order, p, now_hash)
    return ProposalOut(id=p.id, message_id=p.message_id, parent_proposal_id=p.parent_proposal_id, status=p.status,
                       applicable=ok, blocked_reason=why, changes=p.changes or [], estimate=p.estimate,
                       sketch_revision_id=p.sketch_revision_id, created_at=p.created_at, decided_at=p.decided_at)


def message_out(m, calls, proposal: ProposalOut | None = None) -> OrderMessageOut:
    return OrderMessageOut(id=m.id, role=m.role, content=m.content, status=m.status, provider=m.provider, model=m.model,
                           tool_calls=[ToolCallOut(name=c.name, ok=c.ok, revision_id=c.sketch_revision_id) for c in calls],
                           created_at=m.created_at, proposal=proposal)


def _turn_out(a: AssistantService, order_id: int, out: dict[str, Any]) -> OrderTurnOut:
    order = a.session.get(Order, order_id)
    a.session.refresh(order)
    prop = None
    if out.get("proposal") is not None:
        props = ProposalService(a.session, a.customer, a._ip)
        a.session.refresh(out["proposal"])
        prop = proposal_out(props, order, out["proposal"])
    return OrderTurnOut(user=message_out(out["user"], []), reply=message_out(out["reply"], out["tool_calls"], prop),
                        replayed=out["replayed"], sketch_revision_id=order.current_sketch_revision_id, proposal=prop)


def _owned(a: AssistantService, order_id: int) -> None:
    from app.services.sketch_work import SketchWorkService
    SketchWorkService(a.session, a.customer, None).order(order_id)          # 404 for another customer's order


@router.get("/orders/{order_id}/assistant/messages", response_model=OrderConversationOut, responses=_ERR,
            summary="V2 Hội thoại với trợ lý AI của đơn")
def messages(order_id: int, assistant: Assistant) -> OrderConversationOut:
    _owned(assistant, order_id)
    sess = assistant.session_of_order(order_id)
    order = assistant.session.get(Order, order_id)
    props = ProposalService(assistant.session, assistant.customer, assistant._ip)
    now = props.current_hash(order)
    rows = assistant.session_messages(sess)
    by_msg = {mid: proposal_out(props, order, p, now) for mid, p in props.of_messages([m.id for m, _ in rows]).items()}
    return OrderConversationOut(consented_at=sess.consented_at if sess else None, flags=(sess.flags or []) if sess else [],
                                messages=[message_out(m, c, by_msg.get(m.id)) for m, c in rows],
                                proposals=[proposal_out(props, order, p, now) for p in props.of_order(order_id)])


@router.post("/orders/{order_id}/assistant/messages", response_model=OrderTurnOut, responses=_ERR,
             summary="V2 Nhắn trợ lý AI của đơn: trợ lý sửa đơn / phác thảo bằng công cụ của hệ thống",
             description=("Mỗi sửa nét của trợ lý là một revision `author = AI` (hoàn tác được). Khi mọi nhà cung cấp AI đều lỗi, "
                          "trả 200 với `reply.status = FAILED`. `tool_calls[].revision_id` là id revision phác thảo trợ lý tạo."))
def send_message(order_id: int, body: OrderMessageIn, assistant: Assistant,
                 _limit: Annotated[None, Depends(rate_limit("order_ai", 30, 60))]) -> OrderTurnOut:
    # own bucket "order_ai" (30 / min per IP: customers behind one school / office NAT share an IP); counted after the role check
    out = assistant.send_order(order_id, body.text, consent=body.ai_consent, base_revision_id=body.base_revision_id,
                               selection=body.selection.model_dump() if body.selection else None, client_ref=body.client_ref,
                               base_proposal_id=body.base_proposal_id, from_order=body.from_order)
    return _turn_out(assistant, order_id, out)


@router.post("/orders/{order_id}/assistant/messages/stream",
             responses={200: {"content": {"text/event-stream": {}}}, **_ERR},
             summary="V2 Nhắn trợ lý AI của đơn, nhận tiến trình tức thời (Server-Sent Events)",
             description=("Như `POST /orders/{id}/assistant/messages` nhưng trả `text/event-stream`: `user_saved`, `provider`, "
                          "`tool` (kèm `revision_id` phác thảo), `failover`, `proposal` (0029: {id, sketch_revision_id, "
                          "fields}), rồi `reply` (đúng `OrderTurnOut`) hoặc `error`; cuối "
                          "cùng `done`. Lỗi trước khi gọi mô hình vẫn trả HTTP lỗi thường."))
def send_message_stream(order_id: int, body: OrderMessageIn, session: SessionDep, assistant: Assistant,
                        _limit: Annotated[None, Depends(rate_limit("order_ai", 30, 60))]) -> StreamingResponse:
    assistant.lock_order(order_id)
    if assistant.replay(order_id, body.client_ref) is None:
        assistant.precheck_order(order_id, body.text, consent=body.ai_consent, base_revision_id=body.base_revision_id,
                                 base_proposal_id=body.base_proposal_id, from_order=body.from_order)
    customer_id, storage, ip, providers = assistant.customer.id, assistant._storage, assistant._ip, assistant._providers
    session.commit()                                     # frees the order row and the lock before the worker takes them
    events: queue.Queue = queue.Queue()

    def work() -> None:
        s = _factory()()
        try:
            a = AssistantService(s, s.get(Account, customer_id), None, providers, storage=storage, ip=ip)
            out = a.send_order(order_id, body.text, consent=body.ai_consent, base_revision_id=body.base_revision_id,
                               selection=body.selection.model_dump() if body.selection else None, client_ref=body.client_ref,
                               base_proposal_id=body.base_proposal_id, from_order=body.from_order,
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



# ---------------------------------------------------------------------------------------------------------- proposals (0029)
def _proposals(session: SessionDep, customer: CustomerDep, request: Request) -> ProposalService:
    return ProposalService(session, customer, client_ip(request))


Proposals = Annotated[ProposalService, Depends(_proposals)]


@router.get("/orders/{order_id}/assistant/proposals", response_model=list[ProposalOut], responses=_ERR,
            summary="Đề xuất của trợ lý AI trên đơn (FR-08, áp dụng khi khách đồng ý)")
def list_proposals(order_id: int, props: Proposals) -> list[ProposalOut]:
    order = props._order(order_id)
    now = props.current_hash(order)
    return [proposal_out(props, order, p, now) for p in props.of_order(order_id)]


@router.post("/orders/{order_id}/assistant/proposals/{proposal_id}/apply", response_model=ApplyOut, responses=_ERR,
             summary="Áp dụng đề xuất của trợ lý AI vào đơn đang tạo",
             description=("Ghi nội dung / vật tư / tuỳ chọn / phác thảo của đề xuất vào đơn, tính lại giá ước tính. Chỉ khi đơn "
                          "còn đúng trạng thái lúc trợ lý đề xuất (khác → `409 PROPOSAL_STALE`, không đổi gì). Bấm lại đề xuất đã "
                          "áp dụng → trả lại kết quả cũ. Áp dụng xong, các đề xuất đang chờ khác thành không áp dụng được. "
                          "Phác thảo áp dụng là một revision bình thường: Hoàn tác đưa đơn về như trước."))
def apply_proposal(order_id: int, proposal_id: int, props: Proposals) -> ApplyOut:
    p, order = props.apply(order_id, proposal_id)
    props.session.refresh(order)
    props.session.refresh(p)
    est = None if order.estimated_price_min is None else {
        "price_min": int(order.estimated_price_min), "price_max": int(order.estimated_price_max or order.estimated_price_min),
        "currency": "VND", "is_estimate": True}
    return ApplyOut(proposal=proposal_out(props, order, p), current_sketch_revision_id=order.current_sketch_revision_id,
                    estimate=est)


@router.post("/orders/{order_id}/assistant/proposals/{proposal_id}/reject", response_model=ProposalOut, responses=_ERR,
             summary="Bỏ qua đề xuất của trợ lý AI")
def reject_proposal(order_id: int, proposal_id: int, props: Proposals) -> ProposalOut:
    p = props.reject(order_id, proposal_id)
    order = props._order(order_id)
    props.session.refresh(p)
    return proposal_out(props, order, p)
