"""Waybills (Phase 4c-2c): the Staff create the waybill with the carrier service the customer chose, the carrier reports the
parcel's journey by callback, and the order follows it (FR-21, FR-22, UC-29, MSG15).

READY_TO_DELIVER -> DELIVERING when the carrier has the parcel; DELIVERING -> COMPLETED when it is delivered. A failed or
returned delivery leaves the order in DELIVERING (decided by the project owner): the Staff cancel the dead waybill if needed
and create a new one, or switch the customer to pickup. Callbacks arrive repeated and out of order, so every move is judged
against the waybill's current status and an old or repeated one changes nothing (NFR-06).

Order changes are plain UPDATEs judged by the DB trigger `fn_order_state_guard`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.domain import carrier_rules as cr
from app.integrations import carrier as cx
from app.integrations.carrier import SIGNATURE_HEADER
from app.integrations.payment_gateway import InvalidSignature, MalformedCallback
from app.integrations.storage import ObjectStorage
from app.models.account import Account
from app.models.ops import Carrier, PaymentType, Shipment, ShipmentStatus
from app.models.order import DeliveryMethod, Order, OrderStatus
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import JobRepository, PaymentRepository, ShipmentRepository
from app.repositories.orders import OrderRepository
from app.services import audit, notifications
from app.services import parcel as parcel_svc
from app.services.workshop_access import WorkshopAccess

log = logging.getLogger("app")
LABEL_TTL = 600
ALIVE = (ShipmentStatus.CREATED, ShipmentStatus.PICKED_UP, ShipmentStatus.DELIVERING)   # blocks a second waybill


def _now() -> datetime:
    return datetime.now(timezone.utc)


def tracking_url(carrier: Carrier, code: str | None) -> str | None:
    """Public tracking page of the carrier (none for a simulated waybill). Addresses as the author knows them: to confirm."""
    if not code or code.startswith("MOCK-"):
        return None
    return {"GHN": f"https://donhang.ghn.vn/?order_code={code}", "GHTK": f"https://i.ghtk.vn/{code}"}[carrier.value]


class ShipmentService:
    def __init__(self, session: Session, actor: Account | None = None, storage: ObjectStorage | None = None,
                 ip: str | None = None):
        self.session, self.actor, self.storage, self.ip = session, actor, storage, ip
        self.orders = OrderRepository(session)
        self.shipments = ShipmentRepository(session)
        self.payments = PaymentRepository(session)
        self.catalog = CatalogRepository(session)
        self.jobs = JobRepository(session)

    # ------------------------------------------------------------------ reads
    def for_customer(self, order_id: int) -> list[Shipment]:
        assert self.actor is not None
        order = self.orders.get_owned(order_id, self.actor.id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
        return list(reversed(self.shipments.for_order(order.id)))

    def for_staff(self, order_id: int) -> list[Shipment]:
        assert self.actor is not None
        order = WorkshopAccess(self.session, self.actor).order(order_id)
        return list(reversed(self.shipments.for_order(order.id)))

    def label_link(self, shipment: Shipment) -> str | None:
        if not (shipment.label_url and self.storage):
            return None
        try:
            return self.storage.create_download_url(shipment.label_url, LABEL_TTL)
        except AppError:
            return None

    # ------------------------------------------------------------------ UC-29: create the waybill
    def create(self, order_id: int, note: str | None) -> Shipment:
        assert self.actor is not None
        order = WorkshopAccess(self.session, self.actor).order(order_id, write=True, lock=True)
        self.session.refresh(order)
        # READY_TO_DELIVER: the first waybill. DELIVERING: the previous waybill failed or was returned, ship again.
        if (order.order_status not in (OrderStatus.READY_TO_DELIVER, OrderStatus.DELIVERING)
                or order.delivery_method != DeliveryMethod.DELIVERY):
            raise AppError(409, "SHIPMENT_NOT_EXPECTED",
                           "Chỉ tạo vận đơn cho đơn giao hàng đã thanh toán đủ (READY_TO_DELIVER) hoặc đang giao mà vận đơn trước thất bại.",
                           {"order_status": order.order_status.value,
                            "delivery_method": order.delivery_method.value if order.delivery_method else None})
        if order.shipping_carrier is None or order.shipping_service_code is None:
            raise AppError(409, "SHIPPING_SERVICE_NOT_CHOSEN", "Khách chưa chọn hãng và dịch vụ vận chuyển cho đơn này.")
        latest = next(iter(reversed(self.shipments.for_order(order.id))), None)
        if latest is not None and latest.status in ALIVE:
            raise AppError(409, "SHIPMENT_ALREADY_EXISTS", "Đơn đang có vận đơn còn hiệu lực.",
                           {"shipment_id": latest.id, "status": latest.status.value})

        fee_table = self.catalog.setting("fallback_shipping_fees", None)
        adapter = cx.get_adapter(order.shipping_carrier, fee_table=fee_table)
        parcel = parcel_svc.build_parcel(self.catalog, self.jobs, order)
        to = dict(order.delivery_address or {})
        service_code = order.shipping_service_code
        if service_code == "STANDARD" and adapter.mode != "MOCK":
            # chosen while the carrier's API was off (fallback fee): pick its cheapest real service now
            service_code = cr.pick_service(adapter.quote(parcel=parcel, to=to, order_code=order.code), None, None).service_code
        waybill = adapter.create(parcel=parcel, to=to, order_code=order.code, service_code=service_code, note=note)

        paid = self.payments.success(order.id, PaymentType.SHIPPING)
        fee = Decimal(paid.amount) if paid else Decimal(0)            # what the customer paid, not what the carrier charges us
        label_path = self._store_label(adapter, order, waybill, parcel, to, service_code)
        row = self.shipments.add(Shipment(
            order_id=order.id, carrier=Carrier(order.shipping_carrier), service_code=service_code, waybill_code=waybill.code,
            fee=fee, is_fallback_fee=not cx.api_enabled(order.shipping_carrier, self.catalog.setting("integrations_enabled", {})),
            package_type=parcel.package_type, weight_g=parcel.weight_g, to_address=to, status=ShipmentStatus.CREATED,
            label_url=label_path, created_by=self.actor.id))
        if waybill.eta and order.shipping_eta is None:
            order.shipping_eta = waybill.eta
        audit.record(self.session, actor_id=self.actor.id, action="SHIPMENT_CREATE", entity_type="shipment", entity_id=row.id,
                     new={"order_id": order.id, "carrier": row.carrier.value, "service": service_code,
                          "waybill": waybill.code, "customer_paid_fee": str(fee), "carrier_fee": waybill.fee,
                          "mode": adapter.mode}, ip=self.ip)
        notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="SHIPMENT_CREATED", code=order.code,
                             waybill=waybill.code)
        return row

    def _store_label(self, adapter: cx.CarrierAdapter, order: Order, waybill: cr.Waybill, parcel: cr.Parcel,
                     to: Mapping[str, Any], service_code: str) -> str | None:
        """The label is a convenience: failing to get or keep it never loses the waybill that already exists at the carrier."""
        if self.storage is None:
            return None
        try:
            pdf = adapter.label(waybill_code=waybill.code, context={
                "service_name": service_code, "order_code": order.code, "receiver": to.get("receiver", ""),
                "phone": to.get("phone", ""), "address_line": ", ".join(str(to.get(k)) for k in (
                    "street", "ward_name", "district_name", "province_name") if to.get(k)) or str(to.get("street", "")),
                "weight_g": parcel.weight_g})
            if not pdf:
                return None
            path = f"orders/{order.id}/shipments/{waybill.code}/label.pdf"
            self.storage.write(path, pdf, "application/pdf")
            return path
        except AppError:
            log.warning("label for waybill %s could not be stored", waybill.code)
            return None

    # ------------------------------------------------------------------ cancel a waybill that nobody has picked up yet
    def cancel(self, shipment_id: int, reason: str) -> Shipment:
        assert self.actor is not None
        row = self.shipments.get(shipment_id, lock=True)
        if row is None:
            raise AppError(404, "SHIPMENT_NOT_FOUND", "Không tìm thấy vận đơn.")
        order = WorkshopAccess(self.session, self.actor).order(row.order_id, write=True, lock=True)
        self.session.refresh(row)
        if row.status != ShipmentStatus.CREATED:
            raise AppError(409, "SHIPMENT_NOT_CANCELLABLE", "Chỉ huỷ được vận đơn hãng chưa lấy hàng (CREATED).",
                           {"status": row.status.value})
        if row.waybill_code:
            cx.get_adapter(row.carrier.value, fee_table=self.catalog.setting("fallback_shipping_fees", None)).cancel(row.waybill_code)
        row.status = ShipmentStatus.CANCELLED
        self.session.flush()
        audit.record(self.session, actor_id=self.actor.id, action="SHIPMENT_CANCEL", entity_type="shipment", entity_id=row.id,
                     new={"order_id": order.id, "waybill": row.waybill_code}, reason=reason, ip=self.ip)
        return row

    # ------------------------------------------------------------------ the carrier's callbacks
    def handle_webhook(self, carrier: Carrier, body: bytes, query: Mapping[str, str], headers: Mapping[str, str]) -> dict[str, Any]:
        adapter = cx.get_adapter(carrier.value, fee_table=None, strict=False)
        if adapter is None:
            raise AppError(401, "INVALID_SIGNATURE", "Không xác thực được callback của hãng vận chuyển.")
        try:
            event = adapter.parse_webhook(body=body, query=query, headers=headers)
        except InvalidSignature as exc:
            raise AppError(401, "INVALID_SIGNATURE", "Không xác thực được callback của hãng vận chuyển.") from exc
        except MalformedCallback as exc:
            raise AppError(422, "INVALID_WEBHOOK", "Nội dung callback không hợp lệ.") from exc
        if event.status is None:                                        # weight/fee changes, shipper-reported updates, ...
            return {"result": "IGNORED", "status": event.raw_status}
        row = self.shipments.by_waybill(carrier, event.waybill_code, lock=True)
        if row is None:
            raise AppError(404, "SHIPMENT_NOT_FOUND", "Không tìm thấy vận đơn.")
        order = self.orders.get(row.order_id, lock=True)
        return self._apply(row, order, event)

    def _apply(self, row: Shipment, order: Order, event: cr.TrackingEvent) -> dict[str, Any]:
        new = event.status
        assert new is not None
        if new == row.status or not cr.can_move(row.status, new):
            return {"result": "ALREADY_PROCESSED", "status": row.status.value, "order_status": order.order_status.value}
        old = row.status
        row.status, row.carrier_status_raw = new, event.raw_status[:60]
        stamp = event.occurred_at or _now()
        if new in (ShipmentStatus.PICKED_UP, ShipmentStatus.DELIVERING) and row.picked_up_at is None:
            row.picked_up_at = stamp
        if new == ShipmentStatus.DELIVERED:
            row.delivered_at = stamp
        self.session.flush()

        # Only the order's latest waybill drives the order; an older one that reports late just updates its own record.
        latest = self.shipments.for_order(order.id)[-1]
        effect = cr.order_effect(new) if latest.id == row.id else None
        if effect == "DELIVERING" and order.order_status == OrderStatus.READY_TO_DELIVER:
            self._order_to(order, OrderStatus.DELIVERING, "Hãng vận chuyển đã nhận hàng")
            notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="MSG15", code=order.code,
                                 waybill=row.waybill_code)
        if effect == "COMPLETED":
            if order.order_status == OrderStatus.READY_TO_DELIVER:      # the first report we hear is already "delivered"
                self._order_to(order, OrderStatus.DELIVERING, "Hãng vận chuyển đã nhận hàng")
            if order.order_status == OrderStatus.DELIVERING:
                self._order_to(order, OrderStatus.COMPLETED, "Giao hàng thành công")
                notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="ORDER_COMPLETED", code=order.code)
        audit.record(self.session, actor_id=None, action="SHIPMENT_STATUS", entity_type="shipment", entity_id=row.id,
                     old={"status": old.value}, new={"status": new.value, "raw": event.raw_status, "order_id": order.id,
                                                     "reason": event.reason})
        if new in (ShipmentStatus.FAILED, ShipmentStatus.RETURNED) and order.assigned_staff_id:
            notifications.notify(account_id=order.assigned_staff_id, order_id=order.id, msg_code="SHIPMENT_PROBLEM",
                                 code=order.code, status=new.value, reason=event.reason)
        return {"result": "PROCESSED", "status": new.value, "order_status": order.order_status.value}

    def _order_to(self, order: Order, status: OrderStatus, reason: str) -> None:
        set_actor(self.session, None, reason)
        order.order_status = status
        self.session.flush()

    # ------------------------------------------------------------------ demo: the simulated carrier "reports"
    def mock_event(self, shipment_id: int, status: ShipmentStatus, reason: str | None) -> dict[str, Any]:
        assert self.actor is not None
        row = self.shipments.get(shipment_id)
        if row is None:
            raise AppError(404, "SHIPMENT_NOT_FOUND", "Không tìm thấy vận đơn.")
        WorkshopAccess(self.session, self.actor).order(row.order_id, write=True)
        adapter = cx.get_adapter(row.carrier.value, fee_table=None, strict=False)
        if not isinstance(adapter, cx.MockCarrier) or not (row.waybill_code or "").startswith("MOCK-"):
            raise AppError(409, "NOT_A_MOCK_SHIPMENT", "Vận đơn này không phải vận đơn mô phỏng.")
        body = adapter.webhook_body(row.waybill_code, status, reason)
        return self.handle_webhook(row.carrier, body, {}, {SIGNATURE_HEADER: adapter.sign(body)})
