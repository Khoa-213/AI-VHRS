"""V2 Phase B: the customer's working sketch of an order (DRAFT / NEED_INFO), edited through the Geometry Engine.

GET  /orders/{id}/sketch                  current revision + vhrs-sketch/2 document (ids of pages / words / strokes)
POST /orders/{id}/sketch/generate         draw it from the order's inputs (engine; a new revision; {discard_edits})
POST /orders/{id}/sketch/edit             one structured edit {base_revision_id, op, stroke_ids | word_ids | line_ids |
                                          paragraph_ids, params}
POST /orders/{id}/sketch/undo | redo      move the cursor
GET  /orders/{id}/sketch/revisions        history
GET  /orders/{id}/sketch/preview?page=    JPEG in the order's ink / paper, with the AI mark
GET  /orders/{id}/sketch/read-text        V2 Phase E2b (OT-1): can the photos be read, the consent wording, pages read
POST /orders/{id}/sketch/read-text        read the photos with the AI ({consent: true}); hints then come with the sketch
"""
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.schemas import ErrorOut
from app.api.v1.orders import optional_storage
from app.core.ratelimit import rate_limit
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.services import htr_hints
from app.services import sketch_geometry as geo
from app.services.sketch_work import SketchWorkService

router = APIRouter(tags=["Order sketch (V2)"])
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
_ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}}


def _svc(session: SessionDep, customer: CustomerDep, request: Request,
         storage: Annotated[ObjectStorage | None, Depends(optional_storage)]) -> SketchWorkService:
    return SketchWorkService(session, customer, storage, client_ip(request))


Svc = Annotated[SketchWorkService, Depends(_svc)]


class SketchRevisionOut(BaseModel):
    id: int
    seq: int
    parent_id: int | None
    author: str = Field(description="ENGINE | CUSTOMER | AI | STAFF")
    tool_name: str | None
    provider: str | None
    model: str | None
    note: str | None
    operation: dict[str, Any] | None = Field(description="the structured edit {op, stroke_ids, word_ids, params}")
    geometry_hash: str = Field(description="SHA-256 of the strokes; equal to the official v1 when the Staff took it as is")
    metrics: dict[str, Any] | None
    validation: dict[str, Any] | None = Field(description="engine warnings, or the edit report {changed, added, removed, ...}")
    created_at: datetime


class WorkingSketchOut(BaseModel):
    revision: SketchRevisionOut
    is_current: bool
    can_undo: bool
    can_redo: bool
    inputs_changed: bool = Field(description="the order's text / images / paper changed after this drawing: draw it again")
    limits: dict[str, Any] = Field(description="how far one edit may go for this order type (FE sliders)")
    document: dict[str, Any] = Field(description="vhrs-sketch/2: pages -> strokes {id, kind, points, word, provenance} + words "
                                                 "+ lines {id, word_ids, bbox, paragraph} + paragraphs {id, line_ids, bbox, source}")
    warnings: list[str] = []
    report: dict[str, Any] | None = Field(default=None, description="edit: the Geometry Engine report, with Phase F "
                                                                    "affected {strokes, words, lines}")
    redraw: dict[str, Any] | None = Field(default=None, description=(
        "V2 Phase F, generate over an earlier drawing: ids {matched_by: TEXT | POSITION, words_kept, words_new, "
        "words_gone, strokes_kept}, reapplied [{op, word_ids, line_ids, paragraph_ids, params, author}], dropped [same + "
        "reason: OP_NOT_REAPPLIED | NOT_WHOLE_WORDS | GONE | <edit error code>]"))
    inputs_restored: bool = Field(default=False, description="V2 Phase D: undo / redo put the order form (text, layout, "
                                                             "canvas, materials) back to what this revision was drawn from")
    text_hints: dict[str, Any] | None = Field(default=None, description=(
        "V2 Phase E2b, OT-1 only (null otherwise): AI text hints of the word regions, from the photos read with the "
        "customer's consent. {state: NOT_READ | READY | PARTIAL | FAILED | SKETCH_OUTDATED, pages: [{no, status: READ | "
        "FAILED | NOT_READ, provider}], words: {word id: {text | null, status: READ | UNREAD}}}. A hint can be wrong; it "
        "never changes strokes, price or what is approved"))


class ReadTextIn(BaseModel):
    consent: bool = Field(default=False, description="the customer agreed to `consent_text` (asked every time)")


class ReadTextOut(BaseModel):
    enabled: bool = Field(description="Admin switch htr_enabled")
    available: bool = Field(description="enabled and a reader is configured")
    providers: list[str] = Field(description="who may receive the photos, in the order tried (gemini, anthropic)")
    consent_text: str = Field(description="show this before asking; it names the providers")
    daily_cap: int
    used_today: int = Field(description="pages read today, whole system")
    pages: list[dict[str, Any]] = Field(description="[{page_no, input_id, status: READ | FAILED | NOT_READ, provider, read_at}]")
    read_now: list[dict[str, Any]] = Field(default=[], description="POST: the pages sent this time [{input_id, status, provider}]")


class GenerateIn(BaseModel):
    discard_edits: bool = Field(default=False, description="V2 Phase D: the current sketch has edited strokes -> 409 "
                                                           "SKETCH_HAS_EDITS unless true (they stay in the history). "
                                                           "Phase F: whole-word translate / rotate / scale / slant edits "
                                                           "are applied again to the new drawing (see `redraw`)")


class MoveIn(BaseModel):
    discard_input_changes: bool = Field(default=False, description="V2 Phase D: form changes not drawn yet would be "
                                                                   "replaced -> 409 UNDRAWN_INPUT_CHANGES unless true")


class SketchEditIn(BaseModel):
    base_revision_id: int = Field(description="the revision the customer was looking at; another one is current -> 409")
    op: Literal[geo.OPS]  # type: ignore[valid-type]
    stroke_ids: list[str] = Field(default=[], max_length=geo.MAX_SELECTION)
    word_ids: list[str] = Field(default=[], max_length=200, description="select whole words (region level)")
    line_ids: list[str] = Field(default=[], max_length=100, description="V2 Phase F: select whole lines")
    paragraph_ids: list[str] = Field(default=[], max_length=50, description="V2 Phase F: select whole paragraphs")
    params: dict[str, Any] = {}
    note: str | None = Field(default=None, max_length=300)


def _out(svc: SketchWorkService, order_id: int, *, revision_id: int | None = None, warnings: list[str] | None = None,
         report: dict[str, Any] | None = None, inputs_restored: bool = False,
         redraw: dict[str, Any] | None = None) -> WorkingSketchOut:
    data = svc.view(order_id, revision_id)
    lim = geo.limits_for(data["order"].order_type.value)
    hints = htr_hints.hints_for(svc.session, data["order"], data["document"], outdated=data["inputs_changed"])
    return WorkingSketchOut(revision=SketchRevisionOut.model_validate(data["revision"], from_attributes=True),
                            is_current=data["is_current"], can_undo=data["can_undo"], can_redo=data["can_redo"],
                            inputs_changed=data["inputs_changed"], limits=lim.__dict__, document=data["document"],
                            warnings=warnings or [], report=report, inputs_restored=inputs_restored, text_hints=hints,
                            redraw=redraw)


@router.get("/orders/{order_id}/sketch", response_model=WorkingSketchOut, responses=_ERR,
            summary="V2 Phác thảo làm việc hiện tại của đơn (hoặc một revision cũ, ?revision_id=)")
def get_sketch(order_id: int, svc: Svc, revision_id: Annotated[int | None, Query()] = None) -> WorkingSketchOut:
    return _out(svc, order_id, revision_id=revision_id)


@router.post("/orders/{order_id}/sketch/generate", response_model=WorkingSketchOut, status_code=status.HTTP_201_CREATED,
             responses=_ERR, summary="V2 Sinh phác thảo từ nội dung đơn (engine như của xưởng; một revision mới)")
def generate(order_id: int, svc: Svc,
             _limit: Annotated[None, Depends(rate_limit("sketch_generate", 20, 60))],
             body: GenerateIn | None = None) -> WorkingSketchOut:
    rev, _, warnings = svc.generate(order_id, discard_edits=bool(body and body.discard_edits))
    return _out(svc, order_id, warnings=warnings, redraw=svc.last_redraw)


@router.post("/orders/{order_id}/sketch/edit", response_model=WorkingSketchOut, responses=_ERR,
             summary="V2 Một lệnh sửa có cấu trúc (dời / xoay / co giãn / nghiêng / độ cong / mượt / kéo dài / cắt / nối / tách / xoá)")
def edit(order_id: int, body: SketchEditIn, svc: Svc,
         _limit: Annotated[None, Depends(rate_limit("sketch_edit", 120, 60))]) -> WorkingSketchOut:
    rev, _, report = svc.edit(order_id, base_revision_id=body.base_revision_id, op=body.op, stroke_ids=body.stroke_ids,
                              word_ids=body.word_ids, params=body.params, note=body.note, line_ids=body.line_ids,
                              paragraph_ids=body.paragraph_ids)
    return _out(svc, order_id, report=report)


@router.post("/orders/{order_id}/sketch/undo", response_model=WorkingSketchOut, responses=_ERR, summary="V2 Hoàn tác")
def undo(order_id: int, svc: Svc, body: MoveIn | None = None) -> WorkingSketchOut:
    svc.undo(order_id, discard_input_changes=bool(body and body.discard_input_changes))
    return _out(svc, order_id, inputs_restored=svc.inputs_restored)


@router.post("/orders/{order_id}/sketch/redo", response_model=WorkingSketchOut, responses=_ERR, summary="V2 Làm lại")
def redo(order_id: int, svc: Svc, body: MoveIn | None = None) -> WorkingSketchOut:
    svc.redo(order_id, discard_input_changes=bool(body and body.discard_input_changes))
    return _out(svc, order_id, inputs_restored=svc.inputs_restored)


@router.get("/orders/{order_id}/sketch/revisions", response_model=list[SketchRevisionOut], responses=_ERR,
            summary="V2 Lịch sử phác thảo làm việc")
def revisions(order_id: int, svc: Svc) -> list[SketchRevisionOut]:
    _, rows = svc.revisions(order_id)
    return [SketchRevisionOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/orders/{order_id}/sketch/preview", response_class=Response, responses={200: {"content": {"image/jpeg": {}}}, **_ERR},
            summary="V2 Ảnh xem trước một trang (màu mực, độ rộng nét, mặt giấy; có dấu AI)")
def preview(order_id: int, svc: Svc, _limit: Annotated[None, Depends(rate_limit("sketch_preview", 60, 60))],
            page: Annotated[int, Query(ge=1, le=20)] = 1,
            revision_id: Annotated[int | None, Query()] = None) -> Response:
    return Response(svc.preview(order_id, page, revision_id), media_type="image/jpeg", headers={"Cache-Control": "no-store"})



def _htr(session: SessionDep, customer: CustomerDep, request: Request,
         storage: Annotated[ObjectStorage | None, Depends(optional_storage)]) -> htr_hints.HtrService:
    return htr_hints.HtrService(session, customer, storage, ip=client_ip(request))


Htr = Annotated[htr_hints.HtrService, Depends(_htr)]
_HTR_ERR = {**_ERR, 400: {"model": ErrorOut}, 429: {"model": ErrorOut}, 503: {"model": ErrorOut}}


@router.get("/orders/{order_id}/sketch/read-text", response_model=ReadTextOut, responses=_HTR_ERR,
            summary="V2 E2b Đọc chữ trên ảnh (OT-1): bật chưa, câu xin đồng ý, trang đã đọc")
def read_text_status(order_id: int, svc: Htr) -> ReadTextOut:
    return ReadTextOut(**svc.status(order_id))


@router.post("/orders/{order_id}/sketch/read-text", response_model=ReadTextOut, responses=_HTR_ERR,
             summary="V2 E2b Gửi ảnh cho AI đọc chữ (cần consent=true mỗi lần); gợi ý chữ đi kèm phác thảo")
def read_text(order_id: int, body: ReadTextIn, svc: Htr,
              _limit: Annotated[None, Depends(rate_limit("sketch_read_text", 10, 60))]) -> ReadTextOut:
    return ReadTextOut(**svc.read(order_id, consent=body.consent))
