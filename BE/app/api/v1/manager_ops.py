"""Manager-only administration of materials, templates, handwriting styles, robots and prices.

FR-30 (PricingConfig with versions), FR-39 (robots), FR-41 (papers / pens / inks / compatibility / stock),
FR-42 (templates active/inactive, approve handwriting styles). Rows are switched off, never deleted. Admin has no
access here (BR-02: Manager runs production, prices and materials; Admin only administers the system).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.ops_schemas import (CompatIn, CompatOut, InkIn, InkOut, InkPatch, PaperIn, PaperOut, PaperPatch, PenIn,
                                 PenOut, PenPatch, PricingOut, PricingSaveIn, RobotIn, RobotOut, RobotPatch, StockIn,
                                 StyleOut, TemplateAdminOut, TemplateIn, TemplatePatch)
from app.api.staff_schemas import ReasonIn
from app.models.account import Account, RoleCode
from app.models.ops import RobotStatus
from app.models.order import StyleStatus
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import RobotRepository
from app.services.manager_catalog import ManagerCatalogService

router = APIRouter(prefix="/manager", tags=["Manager"])
ManagerDep = Annotated[Account, Depends(require_roles(RoleCode.MANAGER.value))]


def _svc(session: SessionDep, manager: ManagerDep, request: Request) -> ManagerCatalogService:
    return ManagerCatalogService(session, manager, client_ip(request))


Svc = Annotated[ManagerCatalogService, Depends(_svc)]
RobotStatusQuery = Annotated[RobotStatus | None, Query(alias="status")]


# ---- papers --------------------------------------------------------------------------------------
@router.get("/papers", response_model=list[PaperOut], summary="FR-41 Danh sách giấy (kể cả đã ngừng) + tồn kho")
def papers(session: SessionDep, _: ManagerDep) -> list[PaperOut]:
    return [PaperOut.model_validate(p) for p in CatalogRepository(session).all_papers()]


@router.post("/papers", response_model=PaperOut, status_code=status.HTTP_201_CREATED, summary="Thêm loại giấy")
def create_paper(body: PaperIn, svc: Svc) -> PaperOut:
    return PaperOut.model_validate(svc.create_paper(body.model_dump()))


@router.patch("/papers/{paper_id}", response_model=PaperOut, summary="Sửa thông tin / giá / bật-tắt loại giấy")
def update_paper(paper_id: int, body: PaperPatch, svc: Svc) -> PaperOut:
    return PaperOut.model_validate(svc.update_paper(paper_id, body.model_dump(exclude_unset=True)))


@router.post("/papers/{paper_id}/stock", response_model=PaperOut, summary="Điều chỉnh tồn kho giấy (ghi audit, có lý do)")
def paper_stock(paper_id: int, body: StockIn, svc: Svc) -> PaperOut:
    return PaperOut.model_validate(svc.adjust_stock("paper", paper_id, body.mode, body.quantity, body.reason))


# ---- pens & inks ---------------------------------------------------------------------------------
@router.get("/pens", response_model=list[PenOut], summary="FR-41 Danh sách bút (kể cả đã ngừng) + hồ sơ lực + tồn kho")
def pens(session: SessionDep, _: ManagerDep) -> list[PenOut]:
    return [PenOut.model_validate(p) for p in CatalogRepository(session).all_pens()]


@router.post("/pens", response_model=PenOut, status_code=status.HTTP_201_CREATED, summary="Thêm loại bút")
def create_pen(body: PenIn, svc: Svc) -> PenOut:
    return PenOut.model_validate(svc.create_pen(body.model_dump()))


@router.patch("/pens/{pen_id}", response_model=PenOut, summary="Sửa bút (hồ sơ lực, phụ phí, bật-tắt)")
def update_pen(pen_id: int, body: PenPatch, svc: Svc) -> PenOut:
    return PenOut.model_validate(svc.update_pen(pen_id, body.model_dump(exclude_unset=True)))


@router.post("/pens/{pen_id}/stock", response_model=PenOut, summary="Điều chỉnh tồn kho bút")
def pen_stock(pen_id: int, body: StockIn, svc: Svc) -> PenOut:
    return PenOut.model_validate(svc.adjust_stock("pen", pen_id, body.mode, body.quantity, body.reason))


@router.get("/inks", response_model=list[InkOut], summary="Danh sách màu mực (lọc theo bút)")
def inks(session: SessionDep, _: ManagerDep, pen_id: int | None = Query(default=None)) -> list[InkOut]:
    return [InkOut.model_validate(i) for i in CatalogRepository(session).all_inks(pen_id)]


@router.post("/pens/{pen_id}/inks", response_model=InkOut, status_code=status.HTTP_201_CREATED,
             summary="Thêm màu mực cho một loại bút (BR-05)")
def create_ink(pen_id: int, body: InkIn, svc: Svc) -> InkOut:
    return InkOut.model_validate(svc.create_ink(pen_id, body.model_dump()))


@router.patch("/inks/{ink_id}", response_model=InkOut, summary="Sửa màu mực")
def update_ink(ink_id: int, body: InkPatch, svc: Svc) -> InkOut:
    return InkOut.model_validate(svc.update_ink(ink_id, body.model_dump(exclude_unset=True)))


@router.post("/inks/{ink_id}/stock", response_model=InkOut, summary="Điều chỉnh tồn kho mực")
def ink_stock(ink_id: int, body: StockIn, svc: Svc) -> InkOut:
    return InkOut.model_validate(svc.adjust_stock("ink", ink_id, body.mode, body.quantity, body.reason))


# ---- compatibility -------------------------------------------------------------------------------
@router.get("/compatibility", response_model=list[CompatOut], summary="Ma trận tương thích giấy – bút (BR-05, BR-06)")
def compat(session: SessionDep, _: ManagerDep) -> list[CompatOut]:
    return [CompatOut.model_validate(c) for c in CatalogRepository(session).compat_rows()]


@router.put("/compatibility/{paper_id}/{pen_id}", response_model=CompatOut,
            summary="Đặt tương thích / không tương thích (thiếu dòng = không tương thích)")
def set_compat(paper_id: int, pen_id: int, body: CompatIn, svc: Svc) -> CompatOut:
    return CompatOut.model_validate(svc.set_compat(paper_id, pen_id, body.is_compatible, body.note))


# ---- templates & handwriting styles --------------------------------------------------------------
@router.get("/templates", response_model=list[TemplateAdminOut], summary="FR-42 Mẫu chữ (kể cả đang tắt)")
def templates(session: SessionDep, _: ManagerDep) -> list[TemplateAdminOut]:
    return [TemplateAdminOut.model_validate(t) for t in CatalogRepository(session).all_templates()]


@router.post("/templates", response_model=TemplateAdminOut, status_code=status.HTTP_201_CREATED,
             summary="Thêm mẫu chữ (font một nét `hershey:<tên>`)")
def create_template(body: TemplateIn, svc: Svc) -> TemplateAdminOut:
    return TemplateAdminOut.model_validate(svc.create_template(body.model_dump()))


@router.patch("/templates/{template_id}", response_model=TemplateAdminOut, summary="Sửa / bật-tắt mẫu chữ")
def update_template(template_id: int, body: TemplatePatch, svc: Svc) -> TemplateAdminOut:
    return TemplateAdminOut.model_validate(svc.update_template(template_id, body.model_dump(exclude_unset=True)))


@router.get("/styles", response_model=list[StyleOut], summary="FR-42 Bộ nét chờ duyệt (lọc theo trạng thái)")
def styles(svc: Svc, status_: StyleStatus | None = Query(default=StyleStatus.PENDING_REVIEW, alias="status")) -> list[StyleOut]:
    return [StyleOut.model_validate(s) for s in svc.styles(status_)]


@router.post("/styles/{style_id}/approve", response_model=StyleOut, summary="Duyệt bộ nét (cần khách đã xác nhận quyền sử dụng)")
def approve_style(style_id: int, svc: Svc) -> StyleOut:
    return StyleOut.model_validate(svc.approve_style(style_id))


@router.post("/styles/{style_id}/reject", response_model=StyleOut, summary="Từ chối bộ nét (kèm lý do)")
def reject_style(style_id: int, body: ReasonIn, svc: Svc) -> StyleOut:
    return StyleOut.model_validate(svc.reject_style(style_id, body.reason))


# ---- robots --------------------------------------------------------------------------------------
@router.get("/robots", response_model=list[RobotOut], summary="FR-39 Danh sách robot")
def robots(session: SessionDep, _: ManagerDep, status_: RobotStatusQuery = None) -> list[RobotOut]:
    return [RobotOut.model_validate(r) for r in RobotRepository(session).list(status_)]


@router.post("/robots", response_model=RobotOut, status_code=status.HTTP_201_CREATED, summary="Thêm robot")
def create_robot(body: RobotIn, svc: Svc) -> RobotOut:
    return RobotOut.model_validate(svc.create_robot(body.model_dump()))


@router.patch("/robots/{robot_id}", response_model=RobotOut,
              summary="Sửa robot / đổi trạng thái (MAINTENANCE, BROKEN trả danh sách job cần xếp lại)")
def update_robot(robot_id: int, body: RobotPatch, svc: Svc) -> RobotOut:
    row, affected = svc.update_robot(robot_id, body.model_dump(exclude_unset=True))
    out = RobotOut.model_validate(row)
    out.affected_job_ids = affected
    return out


# ---- pricing (FR-30) -----------------------------------------------------------------------------
@router.get("/pricing-config", response_model=PricingOut, summary="Bảng giá đang áp dụng")
def pricing_current(svc: Svc) -> PricingOut:
    return PricingOut.model_validate(svc.pricing_current())


@router.get("/pricing-config/versions", response_model=list[PricingOut], summary="Mọi phiên bản bảng giá (mới nhất trước)")
def pricing_versions(svc: Svc) -> list[PricingOut]:
    return [PricingOut.model_validate(p) for p in svc.pricing_versions()]


@router.post("/pricing-config", response_model=PricingOut, status_code=status.HTTP_201_CREATED,
             summary="Lưu bảng giá mới = tạo phiên bản mới và áp dụng ngay (gồm ngưỡng điều chỉnh BR-09, cọc tối thiểu BR-10)",
             description="Chỉ cần gửi các trường muốn đổi; phần còn lại giữ như phiên bản hiện hành. Báo giá đã lập giữ "
                         "nguyên bảng giá của nó (BR-08).")
def save_pricing(body: PricingSaveIn, svc: Svc) -> PricingOut:
    changes = body.model_dump(exclude_unset=True, exclude={"note"})
    if "discount_tiers" in changes and changes["discount_tiers"] is not None:
        changes["discount_tiers"] = [{"min_qty": t["min_qty"], "pct": float(t["pct"]) if t["pct"] % 1 else int(t["pct"])}
                                     for t in changes["discount_tiers"]]
    return PricingOut.model_validate(svc.save_pricing({k: v for k, v in changes.items() if v is not None}, body.note))
