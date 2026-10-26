"""FR-04, FR-09 (UC-06, UC-11): read-only catalog. Lists are already filtered by compatibility (BR-05)."""
import unicodedata
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import SessionDep, require_roles
from app.api.order_schemas import (InkOut, PaperOut, PenOut, PenWithInksOut, StyleOut, SuggestMaterialsOut,
                                   TemplateOut)
from app.api.schemas import ErrorOut
from app.core.ratelimit import rate_limit
from app.domain import text_layout
from app.models.account import Account, RoleCode
from app.models.order import HandwritingStyle, StyleStatus
from app.core.errors import AppError
from app.repositories.catalog import CatalogRepository
from app.api.v1.orders import optional_storage
from app.services.stroke_ai import outline_font, styled_text, text_to_stroke
from app.services.stroke_ai.trajectory import render_preview

router = APIRouter(prefix="/catalog", tags=["Catalog"])


@router.get("/papers", response_model=list[PaperOut], summary="Loại giấy và khổ đang bán (tối đa A4)")
def papers(session: SessionDep) -> list[PaperOut]:
    return [PaperOut.model_validate(p) for p in CatalogRepository(session).papers()]


@router.get("/pens", response_model=list[PenOut], summary="Bút, lọc theo giấy đã chọn (BR-05, BR-06)")
def pens(session: SessionDep, paper_id: int | None = Query(default=None)) -> list[PenOut]:
    repo = CatalogRepository(session)
    rows = repo.pens_for_paper(paper_id) if paper_id is not None else repo.pens()
    return [PenOut.model_validate(p) for p in rows]


@router.get("/suggest-materials", response_model=SuggestMaterialsOut,
            summary="Gợi ý vật tư theo giấy đã chọn: các bút tương thích kèm màu mực (BR-05, BR-06)",
            responses={404: {"description": "PAPER_NOT_FOUND"}})
def suggest_materials(session: SessionDep, paper_type_id: int = Query(ge=1)) -> SuggestMaterialsOut:
    repo = CatalogRepository(session)
    paper = repo.paper(paper_type_id)
    if paper is None or not paper.is_active:
        raise AppError(404, "PAPER_NOT_FOUND", "Không tìm thấy loại giấy.")
    pens = []
    for pen in repo.pens_for_paper(paper.id):
        inks = repo.inks_for_pen(pen.id)
        if inks:                                           # a pen without any active ink cannot be ordered
            pens.append(PenWithInksOut(**PenOut.model_validate(pen).model_dump(),
                                       inks=[InkOut.model_validate(i) for i in inks]))
    return SuggestMaterialsOut(paper=PaperOut.model_validate(paper), pens=pens)


@router.get("/pens/{pen_id}/inks", response_model=list[InkOut], summary="Màu mực của bút (BR-05)")
def inks(pen_id: int, session: SessionDep) -> list[InkOut]:
    return [InkOut.model_validate(i) for i in CatalogRepository(session).inks_for_pen(pen_id)]


@router.get("/templates", response_model=list[TemplateOut], summary="Thư viện mẫu chữ đang bật")
def templates(session: SessionDep) -> list[TemplateOut]:
    return [TemplateOut.model_validate(t) for t in CatalogRepository(session).templates()]


def _template_preview(tpl, text: str, *, size: float = 9.0, alignment: str = "LEFT", layout: dict | None = None) -> Response:
    """PNG of the first page of `text` in a template, optionally with sizes and styles of parts of it."""
    parsed = None
    if layout:
        try:
            parsed = text_layout.parse(layout, len(unicodedata.normalize("NFC", text)))
        except text_layout.TextLayoutError as exc:
            raise AppError(422, "INVALID_LAYOUT", exc.message, exc.details) from exc
        parsed = None if parsed.is_plain else parsed
    if tpl.font_uri.startswith(outline_font.OUTLINE_PREFIX):
        if len(text) > 80:                                  # public endpoint: keep the work per request small
            raise AppError(422, "PREVIEW_TEXT_TOO_LONG", "Xem thử mẫu chữ này tối đa 80 ký tự.")
        store = optional_storage()
        if store is None:
            raise AppError(503, "STORAGE_NOT_CONFIGURED", "Chưa cấu hình dịch vụ lưu trữ file.")
        source, name = outline_font.load_source(tpl.font_uri[len(outline_font.OUTLINE_PREFIX):], store.read), None
    else:
        source, name = None, text_to_stroke.font_name_from_uri(tpl.font_uri)
    if parsed:
        pages = styled_text.compose_styled(text, parsed, font_name=name, source=source, paper_size="A5",
                                           font_size_mm=size, alignment=alignment)
    else:
        pages = text_to_stroke.compose_text(text, font_name=name, source=source, paper_size="A5", font_size_mm=size,
                                            alignment=alignment)
    return Response(render_preview(pages[0], px_per_mm=4.0), media_type="image/png")


def _active_template(session, template_id: int):
    tpl = CatalogRepository(session).template(template_id)
    if tpl is None or not tpl.is_active:
        raise AppError(404, "TEMPLATE_NOT_FOUND", "Không tìm thấy mẫu chữ.")
    return tpl


@router.get("/templates/{template_id}/preview", response_class=Response,
            responses={200: {"content": {"image/png": {}}}},
            summary="FR-04 Xem thử mẫu chữ với nội dung tự gõ (ảnh PNG, không cần đăng nhập)")
def template_preview(template_id: int, session: SessionDep,
                     text: Annotated[str, Query(min_length=1, max_length=200)] = "Nét Việt") -> Response:
    return _template_preview(_active_template(session, template_id), text)


class PreviewIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    font_size_mm: float = Field(default=9.0, ge=text_layout.MIN_FONT_SIZE_MM, le=text_layout.MAX_FONT_SIZE_MM)
    alignment: Literal["LEFT", "CENTER", "RIGHT", "JUSTIFY"] = "LEFT"
    layout: dict[str, Any] | None = Field(default=None, description="Như `layout` của `PUT /orders/{id}/inputs/text`.")


@router.post("/templates/{template_id}/preview", response_class=Response,
             dependencies=[Depends(rate_limit("template_preview", 60, 60))],
             responses={200: {"content": {"image/png": {}}}, 422: {"model": ErrorOut, "description": "INVALID_LAYOUT / UNSUPPORTED_CHARS / FONT_TOO_LARGE"}},
             summary="FR-08 Xem thử mẫu chữ với cỡ chữ, căn lề và kiểu chữ theo đoạn (ảnh PNG, không cần đăng nhập)",
             description="Trang đầu (khổ A5) của nội dung. Dùng để khách xem trước nghiêng / gạch chân / cỡ chữ trước khi lưu đơn.")
def template_preview_styled(template_id: int, body: PreviewIn, session: SessionDep) -> Response:
    return _template_preview(_active_template(session, template_id), body.text, size=body.font_size_mm,
                             alignment=body.alignment, layout=body.layout)


@router.get("/text-styles", summary="FR-08 Cỡ chữ và kiểu chữ được phép (để dựng thanh công cụ soạn chữ)",
            description="Giới hạn cỡ chữ, giãn dòng, các kiểu (nghiêng, gạch chân đơn/đôi, gạch ngang), số đoạn tối đa. Không có chữ đậm. "
                        "Kiểu chữ không làm đổi giá.")
def text_styles() -> dict:
    return text_layout.capabilities()


@router.get("/my-styles", response_model=list[StyleOut], summary="UC-09 Bộ nét đã lưu (đã duyệt) của tôi")
def my_styles(session: SessionDep, customer: Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
              ) -> list[StyleOut]:
    rows = session.scalars(select(HandwritingStyle).where(
        HandwritingStyle.owner_id == customer.id, HandwritingStyle.status == StyleStatus.APPROVED)
        .order_by(HandwritingStyle.name))
    return [StyleOut.model_validate(r) for r in rows]
