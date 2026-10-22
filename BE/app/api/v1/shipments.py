"""Waybills (Phase 4c-2c; FR-21, FR-22, UC-29, MSG15).

The Staff create the waybill with the carrier service the customer chose; the carrier reports the journey by callback and the
order follows it (READY_TO_DELIVER -> DELIVERING -> COMPLETED). The customer follows the parcel by its waybill code.
Carriers are simulated (CARRIER_MODE=mock, default) or real (sandbox/live); see integrations/carrier.py.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.ops_schemas import WebhookResult
from app.api.schemas import ErrorOut
from app.api.shipment_schemas import (CancelShipmentIn, CreateShipmentIn, MockEventIn, ShipmentOut,
                                      StaffShipmentOut)
from app.api.v1.orders import optional_storage
from app.core.ratelimit import rate_limit
from app.integrations.storage import ObjectStorage
from app.models.account import Account, RoleCode
from app.models.ops import Carrier, Shipment
from app.services.shipments import ShipmentService, tracking_url

router = APIRouter(tags=["Shipments"])
StaffDep = Annotated[Account, Depends(require_roles(RoleCode.STAFF.value))]
ReaderDep = Annotated[Account, Depends(require_roles(RoleCode.STAFF.value, RoleCode.MANAGER.value))]
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
StorageDep = Annotated[ObjectStorage | None, Depends(optional_storage)]
CONFLICT = {409: {"model": ErrorOut, "description": "SHIPMENT_NOT_EXPECTED / SHIPPING_SERVICE_NOT_CHOSEN / SHIPMENT_ALREADY_EXISTS / "
                                                    "SHIPMENT_NOT_CANCELLABLE"}}


def _mode(row: Shipment) -> str:
    return "MOCK" if (row.waybill_code or "").startswith("MOCK-") else "REAL"


def _customer_out(row: Shipment, eta) -> ShipmentOut:
    from app.integrations.carrier import mode_label
    return ShipmentOut(
        id=row.id, order_id=row.order_id, carrier=row.carrier.value, service_code=row.service_code,
        waybill_code=row.waybill_code, status=row.status, fee=row.fee, eta=eta, picked_up_at=row.picked_up_at,
        delivered_at=row.delivered_at, mode="MOCK" if _mode(row) == "MOCK" else mode_label(),
        tracking_url=tracking_url(row.carrier, row.waybill_code), created_at=row.created_at)


def _staff_out(svc: ShipmentService, row: Shipment, eta) -> StaffShipmentOut:
    base = _customer_out(row, eta).model_dump()
    return StaffShipmentOut(**base, package_type=row.package_type, weight_g=row.weight_g, is_fallback_fee=row.is_fallback_fee,
                            carrier_status_raw=row.carrier_status_raw, to_address=row.to_address,
                            label_link=svc.label_link(row), created_by=row.created_by)


def _eta(svc: ShipmentService, order_id: int):
    order = svc.orders.get(order_id)
    return order.shipping_eta if order else None


@router.get("/orders/{order_id}/shipment", response_model=list[ShipmentOut],
            summary="FR-22 Khách theo dõi vận đơn của đơn (mới nhất trước): mã vận đơn, hãng, trạng thái, trang tra cứu")
def customer_shipments(order_id: int, session: SessionDep, customer: CustomerDep, request: Request) -> list[ShipmentOut]:
    svc = ShipmentService(session, customer, None, client_ip(request))
    eta = _eta(svc, order_id)
    return [_customer_out(r, eta) for r in svc.for_customer(order_id)]


@router.get("/workshop/orders/{order_id}/shipment", response_model=list[StaffShipmentOut],
            summary="UC-29 Vận đơn của đơn (mới nhất trước), kèm link nhãn. Staff và Manager (chỉ đọc)")
def staff_shipments(order_id: int, session: SessionDep, actor: ReaderDep, request: Request,
                    storage: StorageDep) -> list[StaffShipmentOut]:
    svc = ShipmentService(session, actor, storage, client_ip(request))
    eta = _eta(svc, order_id)
    return [_staff_out(svc, r, eta) for r in svc.for_staff(order_id)]


@router.post("/workshop/orders/{order_id}/shipment", response_model=StaffShipmentOut, status_code=status.HTTP_201_CREATED,
             summary="UC-29 Tạo vận đơn đúng hãng + dịch vụ khách đã chọn (đơn READY_TO_DELIVER, giao hàng). Chỉ Staff",
             description="Sinh mã vận đơn và nhãn. Đơn chỉ sang `DELIVERING` khi hãng báo đã lấy hàng (callback). "
                         "Hãng từ chối → `502 CARRIER_REJECTED`; hãng lỗi → `502 CARRIER_UNAVAILABLE`.",
             responses={**CONFLICT, 502: {"model": ErrorOut, "description": "CARRIER_REJECTED / CARRIER_UNAVAILABLE"},
                        503: {"model": ErrorOut, "description": "CARRIER_NOT_CONFIGURED"}})
def create_shipment(order_id: int, body: CreateShipmentIn, session: SessionDep, actor: StaffDep, request: Request,
                    storage: StorageDep) -> StaffShipmentOut:
    svc = ShipmentService(session, actor, storage, client_ip(request))
    row = svc.create(order_id, body.note)
    return _staff_out(svc, row, _eta(svc, order_id))


@router.post("/workshop/shipments/{shipment_id}/cancel", response_model=StaffShipmentOut,
             summary="Huỷ vận đơn hãng chưa lấy hàng (CREATED → CANCELLED) để tạo lại. Chỉ Staff", responses=CONFLICT)
def cancel_shipment(shipment_id: int, body: CancelShipmentIn, session: SessionDep, actor: StaffDep, request: Request,
                    storage: StorageDep) -> StaffShipmentOut:
    svc = ShipmentService(session, actor, storage, client_ip(request))
    row = svc.cancel(shipment_id, body.reason)
    return _staff_out(svc, row, _eta(svc, row.order_id))


@router.post("/workshop/shipments/{shipment_id}/mock-event", response_model=WebhookResult,
             summary="Hãng MOCK báo trạng thái (phát lại đúng callback có chữ ký) để demo. Chỉ Staff, chỉ vận đơn mô phỏng",
             responses={409: {"model": ErrorOut, "description": "NOT_A_MOCK_SHIPMENT"}})
def mock_event(shipment_id: int, body: MockEventIn, session: SessionDep, actor: StaffDep, request: Request) -> WebhookResult:
    return WebhookResult(**ShipmentService(session, actor, None, client_ip(request)).mock_event(
        shipment_id, body.status, body.reason))


@router.post("/webhooks/shipments/{carrier}", response_model=WebhookResult,
             dependencies=[Depends(rate_limit("shipment_webhook", 120, 60))],
             summary="Callback của hãng vận chuyển (GHN/GHTK). Xác thực bằng mã bí mật trong địa chỉ hoặc chữ ký; idempotent",
             description="MOCK: header `X-Signature` = HMAC-SHA256(body). GHN: `?key=<CARRIER_WEBHOOK_SECRET>`. GHTK: `?hash=<CARRIER_WEBHOOK_SECRET>`. "
                         "Callback trùng hoặc cũ hơn trạng thái hiện tại trả `ALREADY_PROCESSED` và không đổi gì. Luôn HTTP 200 khi đã xử lý.",
             responses={401: {"model": ErrorOut, "description": "INVALID_SIGNATURE"},
                        404: {"model": ErrorOut, "description": "SHIPMENT_NOT_FOUND"},
                        422: {"model": ErrorOut, "description": "INVALID_WEBHOOK"}})
async def carrier_webhook(carrier: Carrier, request: Request, session: SessionDep) -> WebhookResult:
    body = await request.body()
    svc = ShipmentService(session, None, None, client_ip(request))
    return WebhookResult(**svc.handle_webhook(carrier, body, dict(request.query_params), dict(request.headers)))
