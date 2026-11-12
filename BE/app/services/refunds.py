"""Cancelling a paid order and paying the money back (Phase 4d-1: FR-19, FR-20, UC-21, UC-28; BR-14, BR-16).

How much comes back is decided by `domain/refund_rules.py`. This module applies it:

* cancellation after the deposit (customer, or the workshop's Staff on its own initiative): the order is CANCELLED, its open
  production jobs are CANCELLED (the robot's time is freed; robot commands still waiting for those jobs expire), and a REFUND
  payment is opened as PENDING with `refund_of_id` = the deposit;
* money that reached us for a payment that no longer counted (`needs_refund`, see services/payments.py): Staff opens a REFUND
  for it;
* every refund is paid out by Staff by hand for now (payOS has no refund API, VNPay's needs Render's IP whitelisted, MoMo's is
  untested; owner's decision 2026-11-04) and then confirmed here with the bank / gateway reference: PENDING -> SUCCESS.

Lock order everywhere: production jobs, then the order, then payment rows (the technician and scheduling paths lock the job
before the order; the payment paths lock the order before the payment). One live refund per original payment and kind is
guaranteed by the database (`ux_payments_active_refund`, migration 0014).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import set_actor
from app.domain import refund_rules as rr
from app.integrations import payment_gateway as gw
from app.models.account import Account
from app.models.ops import JobStatus, Payment, PaymentStatus, PaymentType, ProductionJob, RobotCommand
from app.models.order import Order, OrderStatus, ProductionStatus
from app.models.sketch import QuotationStatus
from app.repositories.catalog import CatalogRepository
from app.repositories.ops import JobRepository, PaymentRepository
from app.repositories.orders import OrderRepository
from app.repositories.workshop import QuotationRepository
from app.services import audit, gateway_checkout as checkout, notifications
from app.services.production_snapshot import SnapshotService
from app.services.workshop_access import WorkshopAccess, not_found

log = logging.getLogger("app")

CANCELLATION, ORPHAN = "CANCELLATION", "ORPHAN"
_JOBS_TO_CANCEL = (JobStatus.SCHEDULED, JobStatus.PREPARING, JobStatus.PAUSED)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CancelPreview:
    order: Order
    decision: rr.CancelDecision
    paid: Decimal
    setup_fee: Decimal
    eta_postponed_days: int
    threshold_days: int
    gateway: str | None                       # gateway of the money to refund (PAYOS needs an account to transfer to)
    account_required: bool


class CancellationService:
    """Cancel an order the customer already paid a deposit for. `actor` is the customer, or the Staff assigned to the order."""

    def __init__(self, session: Session, actor: Account, initiator: rr.Initiator, ip: str | None = None):
        self.session, self.actor, self.initiator, self.ip = session, actor, initiator, ip
        self.orders = OrderRepository(session)
        self.payments = PaymentRepository(session)
        self.jobs = JobRepository(session)

    # ---- access ----
    def _visible(self, order_id: int, *, write: bool) -> Order:
        if self.initiator == rr.Initiator.CUSTOMER:
            order = self.orders.get_owned(order_id, self.actor.id)
            if order is None:
                raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
            return order
        order = WorkshopAccess(self.session, self.actor).order(order_id, write=write)
        if write and order.assigned_staff_id != self.actor.id:
            raise not_found()
        return order

    # ---- facts and decision ----
    def _facts(self, order: Order) -> tuple[rr.CancelFacts, list[Payment]]:
        paid_rows = self.payments.paid_rows(order.id)
        approved = QuotationRepository(self.session).latest(order.id, (QuotationStatus.APPROVED,))
        setup = Decimal(0)
        if approved is not None:
            setup = Decimal(str(((approved.price_snapshot or {}).get("pricing_config") or {}).get("setup_fee") or 0))
        threshold = CatalogRepository(self.session).setting("eta_cancel_threshold_days", 7)
        facts = rr.CancelFacts(
            order_status=order.order_status.value, production_status=order.production_status.value,
            paid=sum((p.amount for p in paid_rows), Decimal(0)), setup_fee=setup,
            eta_postponed_days=order.eta_postponed_days or 0, threshold_days=int(threshold),
            wrote_before=any(j.started_at is not None for j in self.jobs.for_order(order.id)))
        return facts, paid_rows

    def preview(self, order_id: int) -> CancelPreview:
        order = self._visible(order_id, write=False)
        facts, paid_rows = self._facts(order)
        decision = rr.decide(facts, self.initiator)
        gateway = paid_rows[0].gateway.value if paid_rows else None
        return CancelPreview(order=order, decision=decision, paid=facts.paid, setup_fee=facts.setup_fee,
                             eta_postponed_days=facts.eta_postponed_days, threshold_days=facts.threshold_days,
                             gateway=gateway,
                             account_required=bool(decision.refund_amount > 0 and gateway == "PAYOS"
                                                   and self.initiator == rr.Initiator.CUSTOMER))

    # ---- the cancellation itself ----
    def _lock(self, order_id: int) -> tuple[Order, list[ProductionJob]]:
        """Jobs first, then the order (the order the technician and scheduling paths take them in)."""
        open_ids = sorted(j.id for j in self.jobs.for_order(order_id) if j.status in _JOBS_TO_CANCEL
                          or j.status == JobStatus.WRITING)
        jobs = [self.jobs.get(i, lock=True) for i in open_ids]
        order = self.orders.get(order_id, lock=True)
        self.session.refresh(order)
        for j in jobs:
            self.session.refresh(j)
        now_open = sorted(j.id for j in self.jobs.for_order(order_id) if j.status in _JOBS_TO_CANCEL
                          or j.status == JobStatus.WRITING)
        if now_open != open_ids:          # a job was scheduled in between: let the caller try again
            raise AppError(409, "STATE_CONFLICT", "Lịch sản xuất của đơn vừa thay đổi, vui lòng thử lại.")
        return order, jobs

    def cancel(self, order_id: int, reason: str, refund_account: dict[str, str] | None = None) -> tuple[Order, Payment | None]:
        order = self._visible(order_id, write=True)
        order, jobs = self._lock(order.id)
        if order.order_status != OrderStatus.CONFIRMED:
            raise AppError(409, "ORDER_CANCEL_UNSUPPORTED", "Đơn ở trạng thái này không huỷ được.",
                           {"order_status": order.order_status.value})
        facts, paid_rows = self._facts(order)
        decision = rr.decide(facts, self.initiator)
        if not decision.allowed:
            raise AppError(409, decision.error_code or "ORDER_CANCEL_UNSUPPORTED", decision.message,
                           {"production_status": order.production_status.value,
                            "eta_postponed_days": facts.eta_postponed_days, "threshold_days": facts.threshold_days})
        source = next((p for p in paid_rows if p.type == PaymentType.DEPOSIT), paid_rows[0] if paid_rows else None)
        if (decision.refund_amount > 0 and source is not None and source.gateway.value == "PAYOS"
                and self.initiator == rr.Initiator.CUSTOMER and not refund_account):
            raise AppError(422, "REFUND_ACCOUNT_REQUIRED",
                           "Tiền cọc đã chuyển khoản qua payOS: hãy nhập tài khoản ngân hàng để xưởng hoàn tiền.")

        for job in jobs:
            job.status = JobStatus.CANCELLED
        if jobs:
            self.session.execute(update(RobotCommand).where(
                RobotCommand.job_id.in_([j.id for j in jobs]), RobotCommand.status == "PENDING")
                .values(status="EXPIRED", finished_at=_now(), error_code="ORDER_CANCELLED"))
        for pay in self.payments.pending_final(order.id) + self.payments.pending(order.id, PaymentType.DEPOSIT):
            pay.status = PaymentStatus.CANCELLED
            checkout.close(pay)
        self.session.flush()
        who = "Khách" if self.initiator == rr.Initiator.CUSTOMER else "Xưởng"
        set_actor(self.session, self.actor.id, f"{who} huỷ đơn ({decision.rule.value}): {reason}")
        order.order_status, order.production_status = OrderStatus.CANCELLED, ProductionStatus.NOT_STARTED
        order.cancel_reason = reason
        self.session.flush()
        SnapshotService(self.session).revoke_for_order(order.id, f"Đơn bị huỷ: {reason}", actor_id=self.actor.id)   # U1

        refund = None
        if decision.refund_amount > 0 and source is not None:
            payload: dict[str, Any] = {
                "refund_kind": CANCELLATION, "rule": decision.rule.value, "deduction": int(decision.deduction),
                "initiator": self.initiator.value, "requested_by": self.actor.id,
                "mode": (source.gateway_payload or {}).get("mode", gw.get_gateway().mode)}
            if refund_account:
                payload["refund_account"] = refund_account
            refund = _add_refund(self.session, Payment(
                order_id=order.id, type=PaymentType.REFUND, amount=decision.refund_amount, gateway=source.gateway,
                status=PaymentStatus.PENDING, refund_of_id=source.id,
                refund_reason=f"{decision.rule.value}: {reason}"[:1000], gateway_payload=payload))
        self.session.refresh(order)
        audit.record(self.session, actor_id=self.actor.id, action="ORDER_CANCEL", entity_type="order", entity_id=order.id,
                     new={"rule": decision.rule.value, "initiator": self.initiator.value, "paid": str(facts.paid),
                          "refund_amount": str(decision.refund_amount), "deduction": str(decision.deduction),
                          "refund_id": refund.id if refund else None, "cancelled_jobs": [j.id for j in jobs]},
                     reason=reason, ip=self.ip)
        notifications.notify(self.session, account_id=order.customer_id, order_id=order.id, msg_code="ORDER_CANCELLED", code=order.code,
                             refund_amount=str(decision.refund_amount))
        if order.assigned_staff_id and refund is not None:
            notifications.notify(self.session, account_id=order.assigned_staff_id, order_id=order.id, msg_code="REFUND_TO_PROCESS",
                                 code=order.code, amount=str(refund.amount))
        for job in jobs:
            notifications.notify(self.session, account_id=job.technician_id, order_id=order.id, msg_code="JOB_CANCELLED", code=order.code)
        return order, refund


def _add_refund(session: Session, row: Payment) -> Payment:
    try:
        with session.begin_nested():
            return PaymentRepository(session).add(row)
    except IntegrityError as exc:
        if "ux_payments_active_refund" in str(exc.orig):
            raise AppError(409, "REFUND_EXISTS", "Khoản này đã có yêu cầu hoàn tiền.") from exc
        raise


# ---------------------------------------------------------------------------------------------
# Staff side: the refund list, refunding orphan money, confirming a transfer (UC-28)
# ---------------------------------------------------------------------------------------------
@dataclass
class OrphanItem:
    payment: Payment               # the row the refund will reference (first row of its gateway transaction)
    order: Order
    amount: int                    # what actually reached us
    types: list[str]


class RefundService:
    def __init__(self, session: Session, actor: Account, ip: str | None = None):
        self.session, self.actor, self.ip = session, actor, ip
        self.access = WorkshopAccess(session, actor)
        self.payments = PaymentRepository(session)
        self.orders = OrderRepository(session)

    def _scope(self) -> int | None:
        return None if self.access.is_manager else self.actor.id

    def list_refunds(self, status: PaymentStatus | None) -> list[tuple[Payment, Order]]:
        rows = self.payments.refunds(status=status, staff_id=self._scope())
        return [(r, self.orders.get(r.order_id)) for r in rows]

    def orphans(self) -> list[OrphanItem]:
        """Flagged money without a live ORPHAN refund yet, one item per gateway transaction."""
        seen: set[str] = set()
        out = []
        for row in self.payments.flagged_orphans(staff_id=self._scope()):
            group = row.gateway_payload.get("group_txn") or f"row:{row.id}"
            if group in seen:
                continue
            seen.add(group)
            rows = self.payments.by_group(row.order_id, group) if not group.startswith("row:") else [row]
            first = min(rows, key=lambda r: r.id)
            if self.payments.live_refund(first.id, ORPHAN) is not None:
                continue
            received = (first.gateway_payload or {}).get("received_amount")
            amount = int(received) if received else int(sum((r.amount for r in rows), Decimal(0)))
            out.append(OrphanItem(payment=first, order=self.orders.get(first.order_id), amount=amount,
                                  types=[r.type.value for r in rows]))
        return out

    def _staff_order(self, order_id: int) -> Order:
        order = self.access.order(order_id, write=True)
        if order.assigned_staff_id != self.actor.id:
            raise not_found()
        locked = self.orders.get(order.id, lock=True)
        self.session.refresh(locked)
        return locked

    def refund_orphan(self, payment_id: int, *, amount: int | None, reason: str,
                      refund_account: dict[str, str] | None) -> Payment:
        probe = self.payments.get(payment_id)
        if probe is None:
            raise AppError(404, "PAYMENT_NOT_FOUND", "Không tìm thấy giao dịch.")
        order = self._staff_order(probe.order_id)
        row = self.payments.get(payment_id, lock=True)
        self.session.refresh(row)
        payload = row.gateway_payload or {}
        if row.type == PaymentType.REFUND or not payload.get("needs_refund"):
            raise AppError(409, "NOT_REFUNDABLE", "Giao dịch này không được đánh dấu cần hoàn tiền.")
        group = payload.get("group_txn")
        rows = self.payments.by_group(row.order_id, group) if group else [row]
        first = min(rows, key=lambda r: r.id)
        received = int(payload.get("received_amount") or sum((r.amount for r in rows), Decimal(0)))
        amount = received if amount is None else amount
        if amount <= 0 or amount > received:
            raise AppError(422, "INVALID_REFUND_AMOUNT", f"Số tiền hoàn phải từ 1 đến {received:,}đ.",
                           {"received_amount": received})
        refund = _add_refund(self.session, Payment(
            order_id=order.id, type=PaymentType.REFUND, amount=Decimal(amount), gateway=first.gateway,
            status=PaymentStatus.PENDING, refund_of_id=first.id, refund_reason=f"ORPHAN: {reason}"[:1000],
            gateway_payload={"refund_kind": ORPHAN, "received_amount": received, "requested_by": self.actor.id,
                             "initiator": rr.Initiator.WORKSHOP.value,
                             "mode": payload.get("mode", gw.get_gateway().mode),
                             **({"refund_account": refund_account} if refund_account else {})}))
        audit.record(self.session, actor_id=self.actor.id, action="REFUND_REQUEST", entity_type="payment",
                     entity_id=refund.id, new={"order_id": order.id, "refund_of_id": first.id, "kind": ORPHAN,
                                               "amount": amount}, reason=reason, ip=self.ip)
        notifications.notify(self.session, account_id=order.customer_id, order_id=order.id, msg_code="REFUND_REQUESTED", code=order.code,
                             amount=str(amount))
        return refund

    def confirm(self, refund_id: int, *, reference: str, note: str | None,
                refund_account: dict[str, str] | None) -> Payment:
        probe = self.payments.get(refund_id)
        if probe is None or probe.type != PaymentType.REFUND:
            raise AppError(404, "REFUND_NOT_FOUND", "Không tìm thấy yêu cầu hoàn tiền.")
        order = self._staff_order(probe.order_id)
        refund = self.payments.get(refund_id, lock=True)
        self.session.refresh(refund)
        if refund.status != PaymentStatus.PENDING:
            raise AppError(409, "REFUND_NOT_PENDING", f"Yêu cầu hoàn tiền đang ở trạng thái {refund.status.value}.",
                           {"status": refund.status.value})
        now = _now()
        payload = {**(refund.gateway_payload or {}), "reference": reference}
        if note:
            payload["note"] = note
        if refund_account:
            payload["refund_account"] = refund_account
        refund.status, refund.paid_at, refund.confirmed_by, refund.confirmed_at = PaymentStatus.SUCCESS, now, self.actor.id, now
        refund.gateway_payload = payload
        self.session.flush()
        self.session.refresh(refund)
        audit.record(self.session, actor_id=self.actor.id, action="REFUND_CONFIRM", entity_type="payment",
                     entity_id=refund.id, new={"order_id": order.id, "amount": str(refund.amount), "reference": reference},
                     reason=note, ip=self.ip)
        notifications.notify(self.session, account_id=order.customer_id, order_id=order.id, msg_code="REFUND_SENT", code=order.code,
                             amount=str(refund.amount))
        return refund


# ---------------------------------------------------------------------------------------------
# Customer side: where to send the money (payOS transfers, or any refund Staff pays by bank transfer)
# ---------------------------------------------------------------------------------------------
def set_refund_account(session: Session, customer: Account, order_id: int, refund_id: int,
                       account: dict[str, str], ip: str | None = None) -> Payment:
    orders, payments = OrderRepository(session), PaymentRepository(session)
    order = orders.get_owned(order_id, customer.id)
    if order is None:
        raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
    orders.get(order.id, lock=True)
    refund = payments.get(refund_id, lock=True)
    if refund is None or refund.order_id != order.id or refund.type != PaymentType.REFUND:
        raise AppError(404, "REFUND_NOT_FOUND", "Không tìm thấy yêu cầu hoàn tiền.")
    session.refresh(refund)
    if refund.status != PaymentStatus.PENDING:
        raise AppError(409, "REFUND_NOT_PENDING", "Khoản hoàn tiền đã được xử lý, không đổi tài khoản được nữa.")
    refund.gateway_payload = {**(refund.gateway_payload or {}), "refund_account": account}
    session.flush()
    audit.record(session, actor_id=customer.id, action="REFUND_ACCOUNT_SET", entity_type="payment", entity_id=refund.id,
                 new={"order_id": order.id, "account": rr.mask_account(account.get("account_number"))}, ip=ip)
    return refund

