"""Workshop side, shared by STAFF and MANAGER: order queue and intake, sketches, quotations.

STAFF act on orders assigned to them (plus the unassigned SUBMITTED pool); MANAGER on every order that has
left DRAFT. CUSTOMER, TECHNICAL_STAFF and ADMIN get 403. Another Staff's order answers 404.
"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.order_schemas import InputOut
from app.api.schemas import Page
from app.api.staff_schemas import (AcceptIn, AdjustIn, FileLinkOut, QuotationCreateIn, QuotationOut, RejectIn,
                                   RequestInfoIn, SketchDetailOut, SketchGenerateIn, SketchManualIn, SketchOut,
                                   SketchPatchIn, WorkshopInputOut, WorkshopOrderDetail, WorkshopOrderRow)
from app.api.v1.orders import optional_storage
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.models.order import Order, OrderInput, OrderStatus
from app.models.sketch import Quotation, Sketch
from app.repositories.workshop import QuotationRepository, SketchRepository
from app.services import quotations as qsvc
from app.services.quotations import QuotationService, option_summaries
from app.services.sketches import SketchService
from app.services.staff_orders import StaffOrderService

router = APIRouter(prefix="/workshop", tags=["Workshop"])
WorkshopDep = Annotated[Account, Depends(require_roles(RoleCode.STAFF.value, RoleCode.MANAGER.value))]
StorageDep = Annotated[ObjectStorage | None, Depends(optional_storage)]
_IMAGES = {"ORIGINAL_IMAGE", "HANDWRITING_SAMPLE"}


def _orders(session: SessionDep, actor: WorkshopDep, request: Request, storage: StorageDep) -> StaffOrderService:
    return StaffOrderService(session, actor, storage, client_ip(request))


def _sketches(session: SessionDep, actor: WorkshopDep, request: Request, storage: StorageDep) -> SketchService:
    return SketchService(session, actor, storage, client_ip(request))


def _quotes(session: SessionDep, actor: WorkshopDep, request: Request, storage: StorageDep) -> QuotationService:
    return QuotationService(session, actor, storage, client_ip(request))


Orders = Annotated[StaffOrderService, Depends(_orders)]
Sketches = Annotated[SketchService, Depends(_sketches)]
Quotes = Annotated[QuotationService, Depends(_quotes)]


def _row(order: Order, customer_name: str) -> WorkshopOrderRow:
    out = WorkshopOrderRow.model_validate(order)
    out.customer_name = customer_name
    return out


def sketch_out(row: Sketch, previews: list[str] | None = None, warnings: list[str] | None = None) -> SketchOut:
    out = SketchOut.model_validate(row)
    out.preview_urls, out.warnings = previews or [], warnings or []
    return out


def quotation_out(q: Quotation) -> QuotationOut:
    out = QuotationOut.model_validate(q)
    out.options = option_summaries(q)
    out.has_pdf = bool(q.file_url)
    return out


# ---- queue & intake -------------------------------------------------------------------------------
@router.get("/orders", response_model=Page[WorkshopOrderRow],
            summary="UC-23 Hàng đợi đơn (Staff: được giao + pool chưa ai nhận; Manager: toàn xưởng)")
def list_orders(svc: Orders, status_filter: Annotated[list[OrderStatus] | None, Query(alias="status")] = None,
                order_type: str | None = None, eta_before: date | None = None, unassigned: bool = False,
                q: Annotated[str | None, Query(max_length=40, description="Mã đơn")] = None,
                page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> Page[WorkshopOrderRow]:
    rows, total = svc.list(statuses=status_filter, order_type=order_type, eta_before=eta_before,
                           unassigned_only=unassigned, q=q, page=page, page_size=page_size)
    return Page(items=[_row(o, n) for o, n in rows], total=total, page=page, page_size=page_size)


@router.get("/orders/{order_id}", response_model=WorkshopOrderDetail,
            summary="Chi tiết đơn: nội dung khách gửi, ảnh (liên kết 10 phút), cảnh báo chất lượng")
def get_order(order_id: int, svc: Orders, session: SessionDep) -> WorkshopOrderDetail:
    order, name, inputs, urls = svc.detail(order_id)
    out = WorkshopOrderDetail.model_validate(order)
    out.customer_name = name
    for row in inputs:
        item = WorkshopInputOut.model_validate(InputOut.model_validate(row).model_dump())
        item.confirmed = row.kind.value not in _IMAGES or row.quality_result is not None
        item.file_url = urls.get(row.id)
        out.inputs.append(item)
    out.warnings = ["IMAGE_QUALITY_LOW"] if any(i.is_quality_warning for i in out.inputs) else []
    final = SketchRepository(session).final(order.id)
    live = QuotationRepository(session).live(order.id)
    out.final_sketch_version, out.open_quotation_id = (final.version if final else None), (live.id if live else None)
    return out


@router.post("/orders/{order_id}/claim", response_model=WorkshopOrderRow,
             summary="FR-12 Staff tự nhận đơn trong pool (nguyên tử: chỉ một người nhận được)")
def claim(order_id: int, svc: Orders) -> WorkshopOrderRow:
    return _row(svc.claim(order_id), "")


@router.post("/orders/{order_id}/accept", response_model=WorkshopOrderRow, summary="UC-24 Tiếp nhận (SUBMITTED → ACCEPTED)")
def accept(order_id: int, body: AcceptIn, svc: Orders) -> WorkshopOrderRow:
    return _row(svc.accept(order_id, body.staff_id), "")


@router.post("/orders/{order_id}/reject", response_model=WorkshopOrderRow,
             summary="UC-24 Từ chối kèm lý do (SUBMITTED → REJECTED)")
def reject(order_id: int, body: RejectIn, svc: Orders) -> WorkshopOrderRow:
    return _row(svc.reject(order_id, body.reason, body.note, body.staff_id), "")


@router.post("/orders/{order_id}/request-info", response_model=WorkshopOrderRow,
             summary="UC-24 Yêu cầu khách bổ sung (SUBMITTED → NEED_INFO)")
def request_info(order_id: int, body: RequestInfoIn, svc: Orders) -> WorkshopOrderRow:
    return _row(svc.request_info(order_id, body.note, body.staff_id), "")


# ---- sketches -------------------------------------------------------------------------------------
@router.post("/orders/{order_id}/sketches/generate", response_model=SketchOut, status_code=status.HTTP_201_CREATED,
             summary="UC-25 Chạy AI tạo phác thảo (OT-1: phục dựng nét từ ảnh; OT-3: sinh nét từ font một nét)",
             responses={422: {"description": "AI_TYPE_UNSUPPORTED (OT-2), UNSUPPORTED_CHARS, NO_STROKES_FOUND, ..."}})
def generate_sketch(order_id: int, body: SketchGenerateIn, svc: Sketches) -> SketchOut:
    row, warnings = svc.generate(order_id, paper_size=body.paper_size, approach_note=body.approach_note, seed=body.seed)
    return sketch_out(row, svc.preview_urls(row), warnings)


@router.post("/orders/{order_id}/sketches", response_model=SketchOut, status_code=status.HTTP_201_CREATED,
             summary="UC-25 Lưu quỹ đạo đã chỉnh sửa / vẽ tay thành phiên bản mới")
def create_manual_sketch(order_id: int, body: SketchManualIn, svc: Sketches) -> SketchOut:
    row = svc.create_manual(order_id, body.trajectory, body.approach_note,
                            body.suggested_complexity.value if body.suggested_complexity else None)
    return sketch_out(row, svc.preview_urls(row))


@router.get("/orders/{order_id}/sketches", response_model=list[SketchOut], summary="Các phiên bản phác thảo")
def list_sketches(order_id: int, svc: Sketches) -> list[SketchOut]:
    return [sketch_out(r) for r in svc.list(order_id)]


@router.get("/orders/{order_id}/sketches/{version}", response_model=SketchDetailOut,
            summary="Một phiên bản: quỹ đạo đầy đủ + liên kết ảnh xem trước từng trang")
def get_sketch(order_id: int, version: int, svc: Sketches) -> SketchDetailOut:
    row, data, previews = svc.detail(order_id, version)
    out = SketchDetailOut.model_validate({**sketch_out(row, previews).model_dump(), "trajectory": data})
    return out


@router.patch("/orders/{order_id}/sketches/{version}", response_model=SketchOut,
              summary="Sửa ghi chú cách làm / độ phức tạp đề xuất")
def patch_sketch(order_id: int, version: int, body: SketchPatchIn, svc: Sketches) -> SketchOut:
    return sketch_out(svc.patch(order_id, version, body.model_dump(exclude_unset=True)))


@router.post("/orders/{order_id}/sketches/{version}/finalize", response_model=SketchOut,
             summary="Chốt phiên bản này là bản gửi khách / dùng sản xuất")
def finalize_sketch(order_id: int, version: int, svc: Sketches) -> SketchOut:
    return sketch_out(svc.finalize(order_id, version))


# ---- quotations -----------------------------------------------------------------------------------
@router.post("/orders/{order_id}/quotations", response_model=QuotationOut, status_code=status.HTTP_201_CREATED,
             summary="UC-26 Lập báo giá từ Pricing Engine (cần phác thảo đã chốt, BR-22)")
def create_quotation(order_id: int, body: QuotationCreateIn, svc: Quotes) -> QuotationOut:
    return quotation_out(svc.create(
        order_id, complexity=body.complexity.value if body.complexity else None, char_count=body.char_count,
        options=[o.model_dump() for o in body.options] if body.options else None, eta=body.eta))


@router.get("/orders/{order_id}/quotations", response_model=list[QuotationOut], summary="Các phiên bản báo giá của đơn")
def list_quotations(order_id: int, svc: Quotes) -> list[QuotationOut]:
    return [quotation_out(q) for q in svc.list_for_order(order_id)]


@router.get("/quotations/{quotation_id}", response_model=QuotationOut, summary="Chi tiết báo giá")
def get_quotation(quotation_id: int, svc: Quotes) -> QuotationOut:
    return quotation_out(svc.get(quotation_id))


@router.put("/quotations/{quotation_id}/adjustment", response_model=QuotationOut,
            summary="FR-31 Điều chỉnh tổng giá: trong ±15% ghi lý do; vượt thì chờ Manager duyệt (BR-09)")
def adjust(quotation_id: int, body: AdjustIn, svc: Quotes) -> QuotationOut:
    return quotation_out(svc.adjust(quotation_id, body.adjusted_total, body.reason))


@router.delete("/quotations/{quotation_id}/adjustment", response_model=QuotationOut, summary="Bỏ điều chỉnh giá")
def clear_adjustment(quotation_id: int, svc: Quotes) -> QuotationOut:
    return quotation_out(svc.clear_adjustment(quotation_id))


@router.post("/quotations/{quotation_id}/send", response_model=QuotationOut,
             summary="Gửi báo giá cho khách: tạo PDF, hiệu lực 7 ngày; đơn → AWAITING_PRIVACY (hoặc QUOTED nếu đã đồng ý chính sách)")
def send(quotation_id: int, svc: Quotes) -> QuotationOut:
    return quotation_out(svc.send(quotation_id))


@router.post("/quotations/{quotation_id}/cancel", response_model=QuotationOut, summary="Hủy báo giá chưa gửi")
def cancel(quotation_id: int, svc: Quotes) -> QuotationOut:
    return quotation_out(svc.cancel(quotation_id))


@router.get("/quotations/{quotation_id}/pdf", response_model=FileLinkOut, summary="FR-32 Liên kết tải PDF báo giá")
def pdf(quotation_id: int, svc: Quotes) -> FileLinkOut:
    return FileLinkOut(url=svc.pdf_url(quotation_id))
