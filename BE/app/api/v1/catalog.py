"""FR-04, FR-09 (UC-06, UC-11): read-only catalog. Lists are already filtered by compatibility (BR-05)."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from app.api.deps import SessionDep, require_roles
from app.api.order_schemas import (InkOut, PaperOut, PenOut, PenWithInksOut, StyleOut, SuggestMaterialsOut,
                                   TemplateOut)
from app.models.account import Account, RoleCode
from app.models.order import HandwritingStyle, StyleStatus
from app.core.errors import AppError
from app.repositories.catalog import CatalogRepository
from app.services.stroke_ai import text_to_stroke
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


@router.get("/templates/{template_id}/preview", response_class=Response,
            responses={200: {"content": {"image/png": {}}}},
            summary="FR-04 Xem thử mẫu chữ với nội dung tự gõ (ảnh PNG, không cần đăng nhập)")
def template_preview(template_id: int, session: SessionDep,
                     text: Annotated[str, Query(min_length=1, max_length=200)] = "Nét Việt") -> Response:
    tpl = CatalogRepository(session).template(template_id)
    if tpl is None or not tpl.is_active:
        raise AppError(404, "TEMPLATE_NOT_FOUND", "Không tìm thấy mẫu chữ.")
    pages = text_to_stroke.compose_text(text, font_name=text_to_stroke.font_name_from_uri(tpl.font_uri),
                                        paper_size="A5", font_size_mm=9.0)
    return Response(render_preview(pages[0], px_per_mm=4.0), media_type="image/png")


@router.get("/my-styles", response_model=list[StyleOut], summary="UC-09 Bộ nét đã lưu (đã duyệt) của tôi")
def my_styles(session: SessionDep, customer: Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
              ) -> list[StyleOut]:
    rows = session.scalars(select(HandwritingStyle).where(
        HandwritingStyle.owner_id == customer.id, HandwritingStyle.status == StyleStatus.APPROVED)
        .order_by(HandwritingStyle.name))
    return [StyleOut.model_validate(r) for r in rows]
