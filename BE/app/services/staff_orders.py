"""Workshop order queue and intake: UC-23, UC-24, UC-47 (FR-12, FR-13).

State changes are issued as plain UPDATEs; the DB trigger fn_order_state_guard accepts or rejects
them (P0409 -> 409), so the transition table lives in one place only.
"""
from __future__ import annotations  # methods named `list` would otherwise shadow the builtin in later annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.integrations.storage import ObjectStorage
from app.models.account import Account, AccountStatus, RoleCode
from app.models.order import Order, OrderInput, OrderStatus
from app.repositories.accounts import AccountRepository
from app.repositories.orders import OrderRepository
from app.services import audit, notifications, quotations
from app.services.workshop_access import WorkshopAccess

REJECT_REASONS = {"TOO_OLD", "DAMAGED", "MISSING_CONTENT", "PROHIBITED_CONTENT", "OTHER"}
ASSIGNABLE = {OrderStatus.SUBMITTED, OrderStatus.NEED_INFO, OrderStatus.ACCEPTED, OrderStatus.AWAITING_PRIVACY,
              OrderStatus.QUOTED, OrderStatus.AWAITING_DEPOSIT, OrderStatus.CONFIRMED, OrderStatus.AWAITING_ACCEPTANCE,
              OrderStatus.AWAITING_FINAL_PAYMENT, OrderStatus.READY_TO_DELIVER, OrderStatus.DELIVERING}


class StaffOrderService:
    def __init__(self, session: Session, actor: Account, storage: ObjectStorage | None = None, ip: str | None = None):
        self.session, self.actor, self.storage, self.ip = session, actor, storage, ip
        self.access = WorkshopAccess(session, actor)
        self.orders = OrderRepository(session)

    # ---- queue (UC-23, FR-12) ----
    def list(self, *, statuses: list[OrderStatus] | None, order_type: str | None, eta_before: date | None,
             unassigned_only: bool, q: str | None, page: int, page_size: int) -> tuple[list[tuple[Order, str]], int]:
        return self.orders.search_workshop(
            staff_id=None if self.access.is_manager else self.actor.id, statuses=statuses, order_type=order_type,
            eta_before=eta_before, unassigned_only=unassigned_only, q=q, offset=(page - 1) * page_size,
            limit=page_size)

    def detail(self, order_id: int) -> tuple[Order, str, list[OrderInput], dict[int, str]]:
        order = self.access.order(order_id)
        quotations.expire_if_overdue(self.session, order)
        customer = AccountRepository(self.session).get(order.customer_id)
        inputs = self.orders.inputs(order.id)
        urls: dict[int, str] = {}
        if self.storage is not None:
            for row in inputs:
                if row.file_url:
                    urls[row.id] = self.storage.create_download_url(row.file_url, 600)
        return order, customer.full_name if customer else "", inputs, urls

    # ---- assignment (FR-12, UC-47) ----
    def claim(self, order_id: int) -> Order:
        if self.access.is_manager:
            raise AppError(403, "FORBIDDEN", "Manager phân công Staff thay vì tự nhận đơn.")
        order = self.access.order(order_id)
        if order.assigned_staff_id == self.actor.id:
            return order
        return self.access.order(order_id, write=True, allow_claim=True)

    def assign(self, order_id: int, staff_id: int) -> Order:
        order = self.access.order(order_id, write=True, lock=True)
        if order.order_status not in ASSIGNABLE:
            raise AppError(409, "ORDER_CLOSED", "Đơn đã kết thúc, không thể phân công.")
        staff = AccountRepository(self.session).get(staff_id)
        if staff is None or staff.role.code != RoleCode.STAFF.value or staff.status != AccountStatus.ACTIVE:
            raise AppError(422, "INVALID_STAFF", "Chỉ phân công được cho tài khoản Staff đang hoạt động.")
        old = order.assigned_staff_id
        order.assigned_staff_id, order.assigned_by = staff.id, self.actor.id
        self.session.flush()
        audit.record(self.session, actor_id=self.actor.id, action="ORDER_ASSIGN", entity_type="order",
                     entity_id=order.id, old={"assigned_staff_id": old}, new={"assigned_staff_id": staff.id},
                     ip=self.ip)
        return order

    def staff_directory(self) -> list[dict[str, Any]]:
        role = AccountRepository(self.session).role_by_code(RoleCode.STAFF.value)
        rows, _ = AccountRepository(self.session).search(role_id=role.id, status=AccountStatus.ACTIVE, q=None,
                                                         offset=0, limit=200)
        counts = self.orders.open_counts_by_staff()
        return [{"id": a.id, "full_name": a.full_name, "email": a.email, "open_orders": counts.get(a.id, 0)}
                for a in rows]

    # ---- intake (UC-24) ----
    def _intake_order(self, order_id: int, staff_id: int | None = None) -> Order:
        order = self.access.order(order_id, write=True, allow_claim=not self.access.is_manager, lock=True)
        if order.assigned_staff_id is None:                 # Manager acting on a pool order
            if staff_id is None:
                raise AppError(422, "STAFF_REQUIRED", "Đơn chưa có Staff phụ trách; hãy chọn staff_id.")
            self.assign(order.id, staff_id)
        return order

    def _move(self, order: Order, target: OrderStatus, reason: str) -> None:
        """Issue the UPDATE and let fn_order_state_guard judge it. The one case the trigger cannot see is a
        no-op (same status written again), so that is refused here."""
        if order.order_status == target:
            raise AppError(409, "STATE_CONFLICT", f"Đơn đã ở trạng thái {target.value}.")
        set_actor(self.session, self.actor.id, reason)
        order.order_status = target
        self.session.flush()

    def accept(self, order_id: int, staff_id: int | None = None) -> Order:
        order = self._intake_order(order_id, staff_id)
        self._move(order, OrderStatus.ACCEPTED, "Tiếp nhận đơn")
        return order

    def reject(self, order_id: int, reason: str, note: str | None, staff_id: int | None = None) -> Order:
        if reason not in REJECT_REASONS:
            raise AppError(422, "INVALID_REASON", "Lý do từ chối không hợp lệ.")
        if reason == "OTHER" and not (note or "").strip():
            raise AppError(422, "NOTE_REQUIRED", "Vui lòng ghi rõ lý do khác.")
        order = self._intake_order(order_id, staff_id)
        order.reject_reason, order.reject_note = reason, (note or None)
        self._move(order, OrderStatus.REJECTED, (note or reason).strip())
        notifications.notify(account_id=order.customer_id, order_id=order.id, msg_code="MSG07", code=order.code,
                             reason=note or reason)
        return order

    def request_info(self, order_id: int, note: str, staff_id: int | None = None) -> Order:
        if not note.strip():
            raise AppError(422, "NOTE_REQUIRED", "Vui lòng nêu thông tin cần khách bổ sung.")
        order = self._intake_order(order_id, staff_id)
        order.info_request_note = note.strip()
        self._move(order, OrderStatus.NEED_INFO, "Yêu cầu bổ sung thông tin")
        return order
