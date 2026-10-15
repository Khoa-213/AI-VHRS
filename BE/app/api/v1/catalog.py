"""FR-04, FR-09 (UC-06, UC-11): read-only catalog. Lists are already filtered by compatibility (BR-05)."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import SessionDep, require_roles
from app.api.order_schemas import InkOut, PaperOut, PenOut, StyleOut, TemplateOut
from app.models.account import Account, RoleCode
from app.models.order import HandwritingStyle, StyleStatus
from app.repositories.catalog import CatalogRepository

router = APIRouter(prefix="/catalog", tags=["Catalog"])


@router.get("/papers", response_model=list[PaperOut], summary="Loại giấy và khổ đang bán (tối đa A4)")
def papers(session: SessionDep) -> list[PaperOut]:
    return [PaperOut.model_validate(p) for p in CatalogRepository(session).papers()]


@router.get("/pens", response_model=list[PenOut], summary="Bút, lọc theo giấy đã chọn (BR-05, BR-06)")
def pens(session: SessionDep, paper_id: int | None = Query(default=None)) -> list[PenOut]:
    repo = CatalogRepository(session)
    rows = repo.pens_for_paper(paper_id) if paper_id is not None else repo.pens()
    return [PenOut.model_validate(p) for p in rows]


@router.get("/pens/{pen_id}/inks", response_model=list[InkOut], summary="Màu mực của bút (BR-05)")
def inks(pen_id: int, session: SessionDep) -> list[InkOut]:
    return [InkOut.model_validate(i) for i in CatalogRepository(session).inks_for_pen(pen_id)]


@router.get("/templates", response_model=list[TemplateOut], summary="Thư viện mẫu chữ đang bật")
def templates(session: SessionDep) -> list[TemplateOut]:
    return [TemplateOut.model_validate(t) for t in CatalogRepository(session).templates()]


@router.get("/my-styles", response_model=list[StyleOut], summary="UC-09 Bộ nét đã lưu (đã duyệt) của tôi")
def my_styles(session: SessionDep, customer: Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
              ) -> list[StyleOut]:
    rows = session.scalars(select(HandwritingStyle).where(
        HandwritingStyle.owner_id == customer.id, HandwritingStyle.status == StyleStatus.APPROVED)
        .order_by(HandwritingStyle.name))
    return [StyleOut.model_validate(r) for r in rows]
