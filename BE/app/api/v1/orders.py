"""UC-07..14, UC-56/57 (FR-05..11, FR-55, FR-56): Customer creates, drafts and submits orders.

Every route is CUSTOMER-only and scoped to the caller's own orders (BR-02); another customer's
order answers 404 so its existence is not revealed.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.order_schemas import (CancelIn, CanvasInputIn, FileUrlOut, ImagePatchIn, InputOut, OrderCreateIn, OrderDetailOut, OrderOut,
                                   OrderUpdateIn, SubmitIn, TextInputIn, UploadUrlIn, UploadUrlOut)
from app.api.schemas import Page
from app.core.errors import AppError
from app.integrations.storage import ObjectStorage, get_storage
from app.models.account import Account, RoleCode
from app.models.order import OrderInput, OrderInputKind, OrderStatus
from app.repositories.orders import OrderRepository
from app.services.orders import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
_IMAGES = {OrderInputKind.ORIGINAL_IMAGE, OrderInputKind.HANDWRITING_SAMPLE}


def optional_storage() -> ObjectStorage | None:
    """None when storage is not configured: only the endpoints that need it answer 503."""
    try:
        return get_storage()
    except AppError:
        return None


def _service(session: SessionDep, customer: CustomerDep, request: Request,
             storage: Annotated[ObjectStorage | None, Depends(optional_storage)]) -> OrderService:
    return OrderService(session, customer, storage, client_ip(request))


Svc = Annotated[OrderService, Depends(_service)]


def input_out(row: OrderInput) -> InputOut:
    out = InputOut.model_validate(row)
    out.confirmed = row.kind not in _IMAGES or row.quality_result is not None
    return out


def _detail(svc: OrderService, order, warnings: list[str] | None = None) -> OrderDetailOut:
    out = OrderDetailOut.model_validate(order)
    out.inputs = [input_out(r) for r in svc.orders.inputs(order.id)]
    out.warnings = (warnings or []) + (["IMAGE_QUALITY_LOW"] if any(i.is_quality_warning for i in out.inputs) else [])
    return out


@router.post("", response_model=OrderDetailOut, status_code=status.HTTP_201_CREATED,
             summary="UC-07 Tạo đơn (bản nháp) với 1 trong 3 loại đơn")
def create_order(body: OrderCreateIn, svc: Svc) -> OrderDetailOut:
    return _detail(svc, svc.create(body.order_type, body.quantity))


@router.get("", response_model=Page[OrderOut], summary="Đơn của tôi; lọc status=DRAFT để lấy danh sách bản nháp (FR-56)")
def list_orders(customer: CustomerDep, session: SessionDep, status_filter: Annotated[list[OrderStatus] | None,
                Query(alias="status")] = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)
                ) -> Page[OrderOut]:
    rows, total = OrderRepository(session).search_owned(
        customer.id, statuses=status_filter, offset=(page - 1) * page_size, limit=page_size)
    return Page(items=[OrderOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/{order_id}", response_model=OrderDetailOut, summary="Chi tiết đơn của tôi")
def get_order(order_id: int, svc: Svc) -> OrderDetailOut:
    return _detail(svc, svc._get(order_id))


@router.patch("/{order_id}", response_model=OrderDetailOut,
              summary="UC-11 Chọn vật tư / số lượng / ghi chú (lưu nháp, FR-55)",
              description="Chỉ sửa được khi DRAFT hoặc NEED_INFO. Chọn giấy → bút → mực; đổi giấy làm bút không hợp "
                          "sẽ reset bút/mực và trả cảnh báo PEN_RESET.")
def update_order(order_id: int, body: OrderUpdateIn, svc: Svc) -> OrderDetailOut:
    order, warnings = svc.update(order_id, body.model_dump(exclude_unset=True))
    return _detail(svc, order, warnings)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Xóa bản nháp (FR-56)")
def delete_draft(order_id: int, svc: Svc) -> Response:
    svc.delete_draft(order_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{order_id}/inputs/text", response_model=InputOut, summary="UC-09/10 Nhập nội dung chữ + mẫu/bộ nét")
def put_text(order_id: int, body: TextInputIn, svc: Svc) -> InputOut:
    return input_out(svc.set_text(order_id, body.model_dump()))


@router.put("/{order_id}/inputs/canvas", response_model=InputOut, summary="UC-10 Lưu hình vẽ canvas")
def put_canvas(order_id: int, body: CanvasInputIn, svc: Svc) -> InputOut:
    return input_out(svc.set_canvas(order_id, body.canvas_data))


@router.post("/{order_id}/inputs/upload-url", response_model=UploadUrlOut, status_code=status.HTTP_201_CREATED,
             summary="UC-08 Xin liên kết tải ảnh/pdf (jpg/png/pdf ≤ 20 MB, ≤ 10 tệp)",
             description="Client PUT file thẳng lên `upload_url`, sau đó gọi `confirm` để hệ thống kiểm tra "
                         "chất lượng ảnh và ước lượng số ký tự tự động.")
def request_upload(order_id: int, body: UploadUrlIn, svc: Svc) -> UploadUrlOut:
    row, target = svc.request_upload(order_id, OrderInputKind(body.kind), body.mime_type, body.size_bytes)
    return UploadUrlOut(input_id=row.id, upload_url=target.url, method=target.method, expires_in=target.expires_in)


@router.post("/{order_id}/inputs/{input_id}/confirm", response_model=InputOut,
             summary="UC-08 Xác nhận đã tải lên: kiểm tra chất lượng + đếm ký tự bằng CV (FR-33)")
def confirm_upload(order_id: int, input_id: int, svc: Svc) -> InputOut:
    return input_out(svc.confirm_upload(order_id, input_id))


@router.patch("/{order_id}/inputs/{input_id}", response_model=InputOut, summary="UC-08 Xoay / cắt ảnh (phân tích lại)")
def patch_image(order_id: int, input_id: int, body: ImagePatchIn, svc: Svc) -> InputOut:
    return input_out(svc.patch_image(order_id, input_id, body.model_dump(exclude_unset=True)))


@router.delete("/{order_id}/inputs/{input_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Xóa một nội dung")
def delete_input(order_id: int, input_id: int, svc: Svc) -> Response:
    svc.delete_input(order_id, input_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{order_id}/submit", response_model=OrderDetailOut, summary="UC-13 Gửi đơn cho xưởng (DRAFT → SUBMITTED)",
             responses={422: {"description": "ORDER_INCOMPLETE / TERMS_NOT_ACCEPTED"}})
def submit(order_id: int, body: SubmitIn, svc: Svc) -> OrderDetailOut:
    return _detail(svc, svc.submit(order_id, terms_accepted=body.terms_accepted,
                                   confirm_right_to_use=body.confirm_right_to_use))


@router.post("/{order_id}/provide-info", response_model=OrderDetailOut,
             summary="UC-14 Gửi lại sau khi bổ sung (NEED_INFO → SUBMITTED)")
def provide_info(order_id: int, body: SubmitIn, svc: Svc) -> OrderDetailOut:
    return _detail(svc, svc.provide_info(order_id, confirm_right_to_use=body.confirm_right_to_use))


@router.post("/{order_id}/cancel", response_model=OrderDetailOut,
             summary="UC-21 Hủy đơn khi chưa cọc: SUBMITTED, NEED_INFO, QUOTED, AWAITING_DEPOSIT (sau cọc: Phase 4)")
def cancel(order_id: int, body: CancelIn, svc: Svc) -> OrderDetailOut:
    return _detail(svc, svc.cancel(order_id, body.reason))


@router.get("/{order_id}/inputs/{input_id}/file", response_model=FileUrlOut,
            summary="Liên kết xem ảnh đã tải lên (hết hạn sau 10 phút), dùng khi mở lại bản nháp")
def input_file(order_id: int, input_id: int, svc: Svc) -> FileUrlOut:
    url, ttl = svc.file_url(order_id, input_id)
    return FileUrlOut(url=url, expires_in=ttl)
