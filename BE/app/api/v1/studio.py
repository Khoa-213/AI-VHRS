"""Upgrade U5: customer studio (drafts before an order, undo/redo, preview, send to the workshop) and its AI assistant.

Every route is CUSTOMER-only and scoped to the caller's own drafts (another customer's draft answers 404).
"""
import json
import logging
import queue
import threading
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.schemas import ErrorOut
from app.api.v1.orders import optional_storage
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.db.session import _factory
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.models.studio import StudioDraft
from app.services.ai.assistant import AssistantService
from app.services.studio import StudioService

router = APIRouter(prefix="/studio", tags=["Studio (U5)"])
log = logging.getLogger(__name__)
STREAM_PING_S = 10
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]


def _studio(session: SessionDep, customer: CustomerDep, request: Request,
            storage: Annotated[ObjectStorage | None, Depends(optional_storage)]) -> StudioService:
    return StudioService(session, customer, storage, client_ip(request))


def assistant_providers():
    """None = the providers configured in the environment. Tests override this dependency with scripted providers."""
    return None


Svc = Annotated[StudioService, Depends(_studio)]


# ---------------------------------------------------------------------------------------------------------- schemas
class DraftCreateIn(BaseModel):
    mode: Literal["TEXT", "RESTORE"] = Field(description="TEXT = soạn chữ theo mẫu (thành đơn OT-3); RESTORE = phục dựng ảnh (OT-1)")
    title: str | None = Field(default=None, max_length=150)


class DraftPatchIn(BaseModel):
    """Chỉ gửi trường cần đổi; mỗi lần đổi là một revision (hoàn tác được)."""
    title: str | None = Field(default=None, max_length=150)
    text: str | None = Field(default=None, max_length=20000)
    template_id: int | None = None
    font_size_mm: float | None = None
    alignment: Literal["LEFT", "CENTER", "RIGHT", "JUSTIFY"] | None = None
    layout: dict[str, Any] | None = Field(default=None, description="Như `layout` của `PUT /orders/{id}/inputs/text`")
    canvas: dict[str, Any] | None = Field(default=None, description='{"strokes": [{"points": [{"x": mm, "y": mm}, ...]}]}')
    paper_type_id: int | None = None
    pen_type_id: int | None = None
    ink_color_id: int | None = None
    workshop_suggest_materials: bool | None = None
    quantity: int | None = Field(default=None, ge=1, le=10000)
    physical_watermark: bool | None = None
    restoration_mode: Literal["FAITHFUL", "ASSISTED"] | None = None
    customer_note: str | None = Field(default=None, max_length=2000)


class ProblemOut(BaseModel):
    field: str
    code: str
    message: str


class EstimateOut(BaseModel):
    chars_min: int
    chars_max: int
    price_min: Decimal
    price_max: Decimal
    basis: str
    materials_priced: bool


class DraftOut(BaseModel):
    id: int
    mode: str
    status: str
    title: str | None
    order_id: int | None
    revision_id: int
    revision_seq: int
    content: dict[str, Any]
    can_undo: bool
    can_redo: bool
    ready: bool
    problems: list[ProblemOut]
    estimate: EstimateOut | None
    warnings: list[str] = []
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None


class DraftListItem(BaseModel):
    id: int
    mode: str
    status: str
    title: str | None
    order_id: int | None
    updated_at: datetime


class RevisionOut(BaseModel):
    id: int
    seq: int
    parent_id: int | None
    author: str
    tool_name: str | None
    note: str | None
    is_current: bool
    created_at: datetime


class CheckOut(BaseModel):
    ready: bool
    problems: list[ProblemOut]
    estimate: EstimateOut | None
    pages: int | None = Field(description="Số trang khi viết (null nếu chưa sinh được)")


class ImageUploadIn(BaseModel):
    mime_type: Literal["image/jpeg", "image/png", "application/pdf"]
    size_bytes: int = Field(gt=0)


class ImageUploadOut(BaseModel):
    image_id: str
    upload_url: str
    method: str
    expires_in: int


class ImageConfirmIn(BaseModel):
    image_id: str


class ImagePatchIn(BaseModel):
    rotation_deg: Literal[0, 90, 180, 270] | None = None
    crop_box: dict[str, float] | None = None


class StudioSubmitIn(BaseModel):
    terms_accepted: bool
    confirm_right_to_use: bool = False


class SubmitOut(BaseModel):
    draft_id: int
    order_id: int


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    ai_consent: bool = Field(default=False, description=(
        "Bắt buộc true ở tin nhắn đầu tiên của bản nháp: khách đồng ý gửi tin nhắn và nội dung bản nháp cho nhà cung cấp AI "
        "bên ngoài. Ảnh không bao giờ được gửi."))


class ToolCallOut(BaseModel):
    name: str
    ok: bool
    revision_id: int | None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    status: str
    provider: str | None
    model: str | None
    tool_calls: list[ToolCallOut] = []
    created_at: datetime


class TurnOut(BaseModel):
    user: MessageOut
    reply: MessageOut
    draft: DraftOut


class AssistantStatusOut(BaseModel):
    enabled: bool
    available: bool
    providers: list[str]
    messages_left_today: int
    daily_message_limit: int
    sends_photos: bool
    policy_version: str | None = Field(default=None, description=(
        "0031: phiên bản chính sách dữ liệu chat AI đang áp dụng (`GET /privacy-policy/ai-chat`)"))
    policy_accepted: bool = Field(default=False, description="0031: tài khoản đã đồng ý phiên bản đó (false: hiện ô đồng ý)")
    policy_accepted_at: datetime | None = None


class StudioRegionEditIn(BaseModel):
    action: Literal["REMOVE", "TEXT"] = Field(description="REMOVE = bỏ vùng (vết bẩn, chữ không muốn giữ); TEXT = viết chữ vào ô (chỉ chế độ ASSISTED, nhãn INFERRED)")
    text: str | None = Field(default=None, max_length=200)
    font: str | None = None
    note: str | None = Field(default=None, max_length=500)


class StudioRegionOut(BaseModel):
    page_no: int
    region_no: int
    bbox_mm: list[float]
    label: str
    confidence: float | None
    source: str
    text: str | None
    note: str | None


class StudioRegionsOut(BaseModel):
    restoration_mode: str
    edits: list[dict[str, Any]]
    regions: list[StudioRegionOut]


_ERR = {404: {"model": ErrorOut, "description": "DRAFT_NOT_FOUND"}, 409: {"model": ErrorOut, "description": "DRAFT_CLOSED"}}


# ---------------------------------------------------------------------------------------------------------- helpers
def _draft_out(svc: StudioService, draft: StudioDraft, warnings: list[str] | None = None) -> DraftOut:
    rev = svc.revision(draft)
    check = svc.check(draft, rev.content, render=False) if draft.status == "OPEN" else {
        "ready": False, "problems": [], "estimate": None}
    return DraftOut(id=draft.id, mode=draft.mode, status=draft.status, title=draft.title, order_id=draft.order_id,
                    revision_id=rev.id, revision_seq=rev.seq, content=rev.content, can_undo=svc.can_undo(draft),
                    can_redo=svc.can_redo(draft), ready=check["ready"], problems=check["problems"],
                    estimate=check["estimate"], warnings=warnings or [], created_at=draft.created_at,
                    updated_at=draft.updated_at, submitted_at=draft.submitted_at)


def _message_out(m, calls) -> MessageOut:
    return MessageOut(id=m.id, role=m.role, content=m.content, status=m.status, provider=m.provider, model=m.model,
                      tool_calls=[ToolCallOut(name=c.name, ok=c.ok, revision_id=c.revision_id) for c in calls],
                      created_at=m.created_at)


# ---------------------------------------------------------------------------------------------------------- drafts
@router.post("", response_model=DraftOut, status_code=status.HTTP_201_CREATED,
             summary="U5 Tạo bản nháp studio (chưa phải đơn hàng)")
def create_draft(body: DraftCreateIn, svc: Svc) -> DraftOut:
    return _draft_out(svc, svc.create(body.mode, body.title))


@router.get("", response_model=list[DraftListItem], summary="U5 Bản nháp studio của tôi")
def list_drafts(svc: Svc, status_: Annotated[Literal["OPEN", "SUBMITTED", "ABANDONED"] | None,
                                            Query(alias="status")] = None) -> list[DraftListItem]:
    return [DraftListItem(id=d.id, mode=d.mode, status=d.status, title=d.title, order_id=d.order_id, updated_at=d.updated_at)
            for d in svc.list(status_)]


@router.get("/{draft_id}", response_model=DraftOut, responses=_ERR,
            summary="U5 Chi tiết bản nháp: nội dung hiện tại, còn thiếu gì, giá ước tính, hoàn tác / làm lại được không")
def get_draft(draft_id: int, svc: Svc) -> DraftOut:
    return _draft_out(svc, svc.get(draft_id))


@router.patch("/{draft_id}", response_model=DraftOut, responses=_ERR,
              summary="U5 Sửa bản nháp (mỗi lần sửa là một revision)",
              description="Chỉ đổi các trường được gửi; gửi `null` để xoá giá trị. Quy tắc vật tư và chữ giống đơn hàng (BR-05, FR-08).")
def patch_draft(draft_id: int, body: DraftPatchIn, svc: Svc) -> DraftOut:
    draft = svc.get_open(draft_id)
    _, warnings = svc.revise(draft, body.model_dump(exclude_unset=True))
    return _draft_out(svc, draft, warnings)


@router.post("/{draft_id}/undo", response_model=DraftOut, responses=_ERR, summary="U5 Hoàn tác (NOTHING_TO_UNDO khi hết)")
def undo(draft_id: int, svc: Svc) -> DraftOut:
    draft = svc.get_open(draft_id)
    svc.undo(draft)
    return _draft_out(svc, draft)


@router.post("/{draft_id}/redo", response_model=DraftOut, responses=_ERR, summary="U5 Làm lại (NOTHING_TO_REDO khi hết)")
def redo(draft_id: int, svc: Svc) -> DraftOut:
    draft = svc.get_open(draft_id)
    svc.redo(draft)
    return _draft_out(svc, draft)


@router.get("/{draft_id}/revisions", response_model=list[RevisionOut], responses=_ERR, summary="U5 Lịch sử sửa của bản nháp")
def revisions(draft_id: int, svc: Svc) -> list[RevisionOut]:
    draft = svc.get(draft_id)
    return [RevisionOut(id=r.id, seq=r.seq, parent_id=r.parent_id, author=r.author, tool_name=r.tool_name, note=r.note,
                        is_current=r.id == draft.current_revision_id, created_at=r.created_at) for r in svc.revisions(draft)]


@router.post("/{draft_id}/check", response_model=CheckOut, responses=_ERR,
             dependencies=[Depends(rate_limit("studio_check", 30, 60))],
             summary="U5 Kiểm tra bản nháp như khi gửi xưởng (có chạy bộ sinh nét: vừa khổ giấy, ký tự không viết được, số trang)")
def check(draft_id: int, svc: Svc) -> CheckOut:
    return CheckOut(**svc.check(svc.get(draft_id)))


@router.get("/{draft_id}/preview", response_class=Response, responses={200: {"content": {"image/jpeg": {}}}, **_ERR},
            dependencies=[Depends(rate_limit("studio_preview", 30, 60))],
            summary="U5 Ảnh xem trước một trang (JPEG, có dấu AI; là ước tính, xưởng làm phác thảo chính thức)")
def preview(draft_id: int, svc: Svc, page: Annotated[int, Query(ge=1, le=20)] = 1) -> Response:
    return Response(svc.preview(svc.get(draft_id), page), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/{draft_id}/images/upload-url", response_model=ImageUploadOut, status_code=status.HTTP_201_CREATED,
             responses=_ERR, summary="U5 Xin URL tải ảnh bản gốc (bản nháp RESTORE)")
def image_upload_url(draft_id: int, body: ImageUploadIn, svc: Svc) -> ImageUploadOut:
    draft = svc.get_open(draft_id)
    image_id, target = svc.request_image_upload(draft, body.mime_type, body.size_bytes)
    return ImageUploadOut(image_id=image_id, upload_url=target.url, method=target.method, expires_in=target.expires_in)


@router.post("/{draft_id}/images/confirm", response_model=DraftOut, responses=_ERR,
             summary="U5 Xác nhận đã tải ảnh: kiểm tra loại file thật, phân tích chất lượng (FR-33), thêm vào bản nháp")
def image_confirm(draft_id: int, body: ImageConfirmIn, svc: Svc) -> DraftOut:
    draft = svc.get_open(draft_id)
    svc.confirm_image(draft, body.image_id)
    return _draft_out(svc, draft)


@router.patch("/{draft_id}/images/{image_id}", response_model=DraftOut, responses=_ERR, summary="U5 Xoay / cắt ảnh (phân tích lại)")
def image_patch(draft_id: int, image_id: str, body: ImagePatchIn, svc: Svc) -> DraftOut:
    draft = svc.get_open(draft_id)
    svc.patch_image(draft, image_id, body.model_dump(exclude_unset=True))
    return _draft_out(svc, draft)


@router.delete("/{draft_id}/images/{image_id}", response_model=DraftOut, responses=_ERR, summary="U5 Bỏ ảnh khỏi bản nháp")
def image_delete(draft_id: int, image_id: str, svc: Svc) -> DraftOut:
    draft = svc.get_open(draft_id)
    svc.remove_image(draft, image_id)
    return _draft_out(svc, draft)


@router.get("/{draft_id}/regions", response_model=StudioRegionsOut, responses=_ERR,
            dependencies=[Depends(rate_limit("studio_preview", 30, 60))],
            summary="U5 Các vùng (từng chữ) của bản xem trước phục dựng, đã áp chỉnh sửa của khách")
def regions(draft_id: int, svc: Svc) -> StudioRegionsOut:
    return StudioRegionsOut(**svc.regions(svc.get(draft_id)))


@router.put("/{draft_id}/regions/{page}/{region}", response_model=DraftOut,
            responses={**_ERR, 409: {"model": ErrorOut, "description": "REGION_MISMATCH / INFERRED_NOT_ALLOWED / DRAFT_CLOSED"},
                       422: {"model": ErrorOut, "description": "INVALID_REGION_TEXT / TOO_MANY_REGION_EDITS"}},
            summary="U5 Bỏ một vùng hoặc viết chữ vào vùng (một revision, hoàn tác được; xưởng nhận đúng chỉnh sửa này)")
def set_region(draft_id: int, page: Annotated[int, Path(ge=1, le=20)], region: Annotated[int, Path(ge=1)],
               body: StudioRegionEditIn, svc: Svc) -> DraftOut:
    draft = svc.get_open(draft_id)
    svc.set_region_edit(draft, page, region, body.action, text=body.text, font=body.font, note=body.note)
    return _draft_out(svc, draft)


@router.delete("/{draft_id}/regions/{page}/{region}", response_model=DraftOut,
               responses={**_ERR, 404: {"model": ErrorOut, "description": "DRAFT_NOT_FOUND / REGION_EDIT_NOT_FOUND"}},
               summary="U5 Bỏ chỉnh sửa của một vùng (vùng trở lại như bản phục dựng)")
def clear_region(draft_id: int, page: Annotated[int, Path(ge=1, le=20)], region: Annotated[int, Path(ge=1)],
                 svc: Svc) -> DraftOut:
    draft = svc.get_open(draft_id)
    svc.remove_region_edit(draft, page, region)
    return _draft_out(svc, draft)


@router.post("/{draft_id}/submit", response_model=SubmitOut, responses={**_ERR, 422: {"model": ErrorOut, "description": "ORDER_INCOMPLETE"}},
             summary="U5 Gửi xưởng: tạo đơn SUBMITTED từ bản nháp (đi qua đúng luật của đơn hàng)")
def submit(draft_id: int, body: StudioSubmitIn, svc: Svc) -> SubmitOut:
    draft = svc.get_open(draft_id)
    order_id = svc.submit(draft, terms_accepted=body.terms_accepted, confirm_right_to_use=body.confirm_right_to_use)
    return SubmitOut(draft_id=draft.id, order_id=order_id)


@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERR,
               summary="U5 Bỏ bản nháp (xoá ảnh đã tải của bản nháp)")
def abandon(draft_id: int, svc: Svc) -> Response:
    svc.abandon(svc.get_open(draft_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------------------------------------- assistant
def _assistant(svc: Svc, providers=Depends(assistant_providers)) -> AssistantService:
    return AssistantService(svc.session, svc.customer, svc, providers)


Assistant = Annotated[AssistantService, Depends(_assistant)]


@router.get("/assistant/status", response_model=AssistantStatusOut,
            summary="U5 Trợ lý AI có dùng được không, còn bao nhiêu lượt nhắn hôm nay (không trả khoá hay chi phí)")
def assistant_status(assistant: Assistant) -> AssistantStatusOut:
    return AssistantStatusOut(**assistant.status())


@router.get("/{draft_id}/messages", response_model=list[MessageOut], responses=_ERR, summary="U5 Hội thoại với trợ lý của bản nháp")
def messages(draft_id: int, svc: Svc, assistant: Assistant) -> list[MessageOut]:
    return [_message_out(m, calls) for m, calls in assistant.messages(svc.get(draft_id))]


@router.post("/{draft_id}/messages", response_model=TurnOut,
             responses={**_ERR, 422: {"model": ErrorOut, "description": "AI_CONSENT_REQUIRED"},
                        429: {"model": ErrorOut, "description": "AI_DAILY_LIMIT / RATE_LIMITED"},
                        503: {"model": ErrorOut, "description": "AI_UNAVAILABLE / AI_DISABLED / AI_BUDGET_EXHAUSTED"}},
             summary="U5 Nhắn trợ lý AI: trợ lý chỉ sửa bản nháp bằng công cụ của hệ thống (hoàn tác được)",
             description="Khi mọi nhà cung cấp AI đều lỗi, trả 200 với `reply.status = FAILED` và lời nhắn cho khách.")
def send_message(draft_id: int, body: MessageIn, svc: Svc, assistant: Assistant,
                 _limit: Annotated[None, Depends(rate_limit("studio_ai", 10, 60))]) -> TurnOut:
    # counted after the role check (V2 Phase C: a refused role used the shared bucket and later roles got 429, not 403)
    draft = svc.get_open(draft_id)
    out = assistant.send(draft, body.text, consent=body.ai_consent)
    return TurnOut(user=_message_out(out["user"], []), reply=_message_out(out["reply"], out["tool_calls"]),
                   draft=_draft_out(svc, draft))


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/{draft_id}/messages/stream",
             responses={200: {"content": {"text/event-stream": {}}}, **_ERR,
                        422: {"model": ErrorOut, "description": "AI_CONSENT_REQUIRED"},
                        429: {"model": ErrorOut, "description": "AI_DAILY_LIMIT / RATE_LIMITED"},
                        503: {"model": ErrorOut, "description": "AI_UNAVAILABLE / AI_DISABLED / AI_BUDGET_EXHAUSTED"}},
             summary="U5 Nhắn trợ lý AI, nhận tiến trình tức thời (Server-Sent Events)",
             description=("Như `POST /studio/{id}/messages` nhưng trả `text/event-stream`: `user_saved`, `provider`, `tool` (mỗi thao "
                          "trợ lý vừa làm, kèm `revision_id`), `failover`, rồi `reply` (đúng nội dung `TurnOut`) hoặc `error` "
                          "({code, message}); cuối cùng `done`. Lỗi trước khi gọi mô hình (đồng ý, trần lượt, chưa cấu hình) "
                          "vẫn trả HTTP lỗi thường. Câu trả lời đến một lần ở `reply`, không theo từng chữ."))
def send_message_stream(draft_id: int, body: MessageIn, session: SessionDep, svc: Svc, assistant: Assistant,
                        _limit: Annotated[None, Depends(rate_limit("studio_ai", 10, 60))]) -> StreamingResponse:
    # the shared "studio_ai" bucket (with POST /messages) is counted after the role check, so a refused role never uses it
    draft = svc.get(draft_id)
    if draft.status != "OPEN":
        svc.get_open(draft_id)                            # raises DRAFT_CLOSED with the usual message
    text = assistant.precheck(draft, body.text, consent=body.ai_consent)
    customer_id, storage, ip, providers = svc.customer.id, svc.storage, svc.ip, assistant._providers
    session.commit()                                     # saves a consent given now (0031); frees the row before the worker locks it
    events: queue.Queue = queue.Queue()

    def work() -> None:
        s = _factory()()
        try:
            customer = s.get(Account, customer_id)
            studio = StudioService(s, customer, storage, ip)
            a = AssistantService(s, customer, studio, providers)
            d = studio.get_open(draft_id)
            out = a.send(d, text, consent=body.ai_consent, on_event=lambda name, data: events.put((name, data)))
            turn = TurnOut(user=_message_out(out["user"], []), reply=_message_out(out["reply"], out["tool_calls"]),
                           draft=_draft_out(studio, d))
            s.commit()
            events.put(("reply", turn.model_dump(mode="json")))
        except AppError as exc:
            s.rollback()
            events.put(("error", {"code": exc.code, "message": exc.message}))
        except Exception:
            s.rollback()
            log.exception("studio assistant stream failed (draft %s)", draft_id)
            events.put(("error", {"code": "INTERNAL_ERROR", "message": "Có lỗi khi xử lý tin nhắn. Vui lòng thử lại."}))
        finally:
            s.close()
            events.put(None)

    threading.Thread(target=work, name=f"studio-ai-{draft_id}", daemon=True).start()

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
