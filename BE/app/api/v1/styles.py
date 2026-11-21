"""OT-2 Phase O2 (owner approved 2026-11-20): the customer's handwriting styles built from the fixed sample sheet.

Flow: POST /styles -> GET /styles/sheet.pdf (print, write by hand) -> for each page: POST .../upload-url, PUT the photo to
`upload_url`, POST .../confirm (the page is read on the server) -> GET /styles/{id} (coverage, boxes with problems) ->
POST /styles/{id}/submit (Manager review, `/manager/styles`). An approved style is listed by `/catalog/my-styles`.
"""
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.v1.orders import optional_storage
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.models.order import StyleStatus
from app.services import handwriting_styles as svc_mod
from app.services.handwriting_styles import StyleService
from app.services.stroke_ai import sample_sheet

router = APIRouter(prefix="/styles", tags=["Handwriting styles (OT-2)"])
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]


def _svc(session: SessionDep, customer: CustomerDep, request: Request,
         storage: Annotated[ObjectStorage | None, Depends(optional_storage)]) -> StyleService:
    return StyleService(session, customer, storage, client_ip(request))


Svc = Annotated[StyleService, Depends(_svc)]


class StyleCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    right_to_use_confirmed: bool
    keep_consent: bool = False


class PageSummary(BaseModel):
    page_no: int
    uploaded_at: datetime
    cells: dict[str, int]


class StyleDetailOut(BaseModel):
    id: int
    name: str
    status: StyleStatus
    sheet_version: str | None
    right_to_use_confirmed: bool
    keep_consent: bool
    coverage_pct: float
    missing: list[str]
    issues: list[dict[str, Any]]
    review_note: str | None
    submitted_at: datetime | None
    approved_at: datetime | None
    created_at: datetime
    pages_total: int
    pages: list[PageSummary]


class PageUploadIn(BaseModel):
    mime_type: Literal["image/jpeg", "image/png"]
    size_bytes: int = Field(gt=0)


class PageUploadOut(BaseModel):
    upload_id: str
    upload_url: str
    method: str
    expires_in: int


class PageConfirmIn(BaseModel):
    upload_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    mime_type: Literal["image/jpeg", "image/png"]


class PageOut(BaseModel):
    page_no: int
    cells: list[dict[str, Any]]          # {cell, char, status}; strokes are not sent back to the customer here


def _detail(svc: StyleService, row) -> StyleDetailOut:
    return StyleDetailOut(**svc_mod.describe(svc.s, row))


@router.get("/sheet.pdf", summary="Phiếu mẫu chữ (PDF A4, in ra để viết tay)", response_class=Response)
def sheet_pdf(_: CustomerDep) -> Response:
    return Response(sample_sheet.sheet_pdf(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="phieu-mau-chu-{sample_sheet.SHEET_VERSION}.pdf"'})


@router.post("", response_model=StyleDetailOut, status_code=status.HTTP_201_CREATED, summary="Tạo bộ nét (DRAFT)")
def create_style(body: StyleCreateIn, svc: Svc) -> StyleDetailOut:
    return _detail(svc, svc.create(body.name, body.right_to_use_confirmed, body.keep_consent))


@router.get("", response_model=list[StyleDetailOut], summary="Bộ nét của tôi (mọi trạng thái trừ đã xoá)")
def my_styles(svc: Svc) -> list[StyleDetailOut]:
    return [_detail(svc, r) for r in svc.mine()]


@router.get("/{style_id}", response_model=StyleDetailOut, summary="Chi tiết bộ nét: độ phủ, chữ còn thiếu, ô có vấn đề")
def get_style(style_id: int, svc: Svc) -> StyleDetailOut:
    return _detail(svc, svc.get(style_id))


@router.post("/{style_id}/pages/{page_no}/upload-url", response_model=PageUploadOut, status_code=status.HTTP_201_CREATED,
             summary="Xin URL tải ảnh một trang phiếu", description="PUT ảnh thẳng lên `upload_url`, rồi gọi `confirm`.")
def page_upload_url(style_id: int, page_no: int, body: PageUploadIn, svc: Svc) -> PageUploadOut:
    upload_id, target = svc.request_upload(style_id, page_no, body.mime_type, body.size_bytes)
    return PageUploadOut(upload_id=upload_id, upload_url=target.url, method=target.method, expires_in=target.expires_in)


@router.post("/{style_id}/pages/{page_no}/confirm", response_model=PageOut,
             summary="Xác nhận ảnh trang phiếu: hệ thống đọc từng ô (không gửi ảnh ra ngoài)")
def page_confirm(style_id: int, page_no: int, body: PageConfirmIn, svc: Svc) -> PageOut:
    page = svc.confirm_upload(style_id, page_no, body.upload_id, body.mime_type)
    return PageOut(page_no=page.page_no, cells=[{"cell": c["cell"], "char": c["char"], "status": c["status"]}
                                                for c in page.read_result["cells"]])


@router.post("/{style_id}/submit", response_model=StyleDetailOut, summary="Gửi bộ nét cho xưởng duyệt")
def submit_style(style_id: int, svc: Svc) -> StyleDetailOut:
    return _detail(svc, svc.submit(style_id))


@router.delete("/{style_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Xoá bộ nét và ảnh phiếu")
def delete_style(style_id: int, svc: Svc) -> Response:
    svc.delete(style_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
