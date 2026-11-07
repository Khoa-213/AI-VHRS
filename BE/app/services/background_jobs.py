"""Background jobs (Phase 5a). Each job is idempotent: running it twice, or after a lazy check already did the work, does nothing
more. `run_all` takes a Postgres advisory lock so two runs (the in-process loop and an Admin's "run now", or two instances)
never overlap, runs every job in its own transactions, and keeps going when one job fails.

Jobs:
* quotation_expiry   BR-08: a SENT quotation past `valid_until` expires, the order is cancelled, MSG08 (was only lazy).
* deposit_deadline   owner's decision 2026-11-06: AWAITING_DEPOSIT more than `deposit_deadline_days` (default 3) after the
                     customer approved the quotation -> cancelled, pending deposit links closed. Skipped while a deposit
                     attempt is younger than DEPOSIT_GRACE (the customer may be paying right now).
* acceptance         FR-28: one reminder after `accept_reminder_days` (3), auto-accept after `auto_accept_days` (7, was lazy).
* email_retry        notification e-mails that failed (sent_at NULL), from EMAIL_RETRY_MIN_AGE to EMAIL_RETRY_MAX_AGE old.
* photo_purge        BR-23 / NFR-12: customer uploads (original images, handwriting samples) of orders COMPLETED or CANCELLED
                     more than PURGE_AFTER_DAYS ago are deleted from storage, unless the sample belongs to a handwriting style
                     the customer agreed to keep. DRY RUN (count only) unless `system_settings.photo_purge_enabled` is true.

`order_ids` limits every job to those orders (tests run against the shared database and must never touch real orders).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.orm import Session

from app.db.session import _factory, get_engine, set_actor
from app.domain import photo_rules as pr
from app.integrations.mailer import get_mailer
from app.integrations.storage import ObjectStorage
from app.models.account import Account, AuditLog
from app.models.notification import Notification, NotificationChannel
from app.models.ops import Payment, PaymentStatus, PaymentType
from app.models.order import HandwritingStyle, Order, OrderInput, OrderInputKind, OrderStatus
from app.models.sketch import Quotation, QuotationStatus
from app.repositories.catalog import CatalogRepository
from app.services import audit, gateway_checkout as checkout, notifications
from app.services import quotations as quotation_service

log = logging.getLogger("app.jobs")

LOCK_KEY = 5_141_001                      # pg advisory lock id of the job runner
DEFAULT_DEPOSIT_DAYS = 3
DEFAULT_REMINDER_DAYS = 3
DEPOSIT_GRACE = timedelta(minutes=60)
EMAIL_RETRY_MIN_AGE = timedelta(minutes=2)
EMAIL_RETRY_MAX_AGE = timedelta(hours=24)
PURGE_AFTER_DAYS = 90
BATCH = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _int_setting(session: Session, key: str, default: int) -> int:
    try:
        return int(CatalogRepository(session).setting(key, default))
    except (TypeError, ValueError):
        return default


def _scoped(q, order_col, order_ids: list[int] | None):
    return q if order_ids is None else q.where(order_col.in_(order_ids or [-1]))


# --------------------------------------------------------------------------------------------------- jobs
def quotation_expiry(session: Session, *, order_ids: list[int] | None = None, **_: Any) -> dict[str, Any]:
    q = select(Quotation.id).where(Quotation.status == QuotationStatus.SENT, Quotation.valid_until < _now())
    done = 0
    for qid in session.scalars(_scoped(q, Quotation.order_id, order_ids).limit(BATCH)).all():
        quote = session.get(Quotation, qid, with_for_update=True)
        session.refresh(quote)
        if quote.status != QuotationStatus.SENT or not quote.valid_until or quote.valid_until >= _now():
            session.rollback()
            continue
        order = session.get(Order, quote.order_id, with_for_update=True)
        session.refresh(order)
        quotation_service._expire(session, quote, order)
        session.commit()
        done += 1
    return {"expired": done}


def deposit_deadline(session: Session, *, order_ids: list[int] | None = None, **_: Any) -> dict[str, Any]:
    days = _int_setting(session, "deposit_deadline_days", DEFAULT_DEPOSIT_DAYS)
    now = _now()
    approved_at = (select(func.max(Quotation.customer_responded_at)).where(
        Quotation.order_id == Order.id, Quotation.status == QuotationStatus.APPROVED).scalar_subquery())
    fresh_attempt = exists().where(Payment.order_id == Order.id, Payment.type == PaymentType.DEPOSIT,
                                   Payment.status == PaymentStatus.PENDING, Payment.created_at > now - DEPOSIT_GRACE)
    q = select(Order.id).where(Order.order_status == OrderStatus.AWAITING_DEPOSIT, approved_at < now - timedelta(days=days),
                               ~fresh_attempt)
    done, skipped = 0, 0
    for oid in session.scalars(_scoped(q, Order.id, order_ids).limit(BATCH)).all():
        order = session.get(Order, oid, with_for_update=True)
        session.refresh(order)
        if order.order_status != OrderStatus.AWAITING_DEPOSIT or session.scalar(
                select(fresh_attempt).where(Order.id == oid)):
            session.rollback()
            skipped += 1
            continue
        for pay in session.scalars(select(Payment).where(Payment.order_id == oid, Payment.type == PaymentType.DEPOSIT,
                                                         Payment.status == PaymentStatus.PENDING)):
            pay.status = PaymentStatus.CANCELLED
            checkout.close(pay)
        reason = f"Quá hạn đặt cọc ({days} ngày sau khi duyệt báo giá)"
        set_actor(session, None, reason)
        order.order_status = OrderStatus.CANCELLED
        order.cancel_reason = reason
        session.flush()
        audit.record(session, actor_id=None, action="ORDER_DEPOSIT_OVERDUE", entity_type="order", entity_id=oid,
                     new={"days": days}, reason=reason)
        notifications.notify(session, account_id=order.customer_id, order_id=oid, msg_code="DEPOSIT_OVERDUE",
                             code=order.code, days=days)
        session.commit()
        done += 1
    return {"cancelled": done, "skipped": skipped, "days": days}


def acceptance(session: Session, *, order_ids: list[int] | None = None, **_: Any) -> dict[str, Any]:
    from app.services.acceptance import AcceptanceService
    auto_days = _int_setting(session, "auto_accept_days", pr.DEFAULT_AUTO_ACCEPT_DAYS)
    remind_days = _int_setting(session, "accept_reminder_days", DEFAULT_REMINDER_DAYS)
    now = _now()
    waiting = select(Order.id).where(Order.order_status == OrderStatus.AWAITING_ACCEPTANCE,
                                     Order.awaiting_acceptance_at.is_not(None))
    accepted = 0
    overdue = _scoped(waiting.where(Order.awaiting_acceptance_at <= now - timedelta(days=auto_days)), Order.id, order_ids)
    for oid in session.scalars(overdue.limit(BATCH)).all():
        order = session.get(Order, oid)
        customer = session.get(Account, order.customer_id)
        if AcceptanceService(session, customer, None).settle_overdue(order):      # locks, re-checks and commits
            accepted += 1
        else:
            session.rollback()
    reminded_marker = exists().where(AuditLog.action == "ACCEPT_REMINDER", AuditLog.entity_type == "order",
                                     AuditLog.entity_id == Order.id, AuditLog.created_at >= Order.awaiting_acceptance_at)
    due = _scoped(waiting.where(Order.awaiting_acceptance_at <= now - timedelta(days=remind_days),
                                Order.awaiting_acceptance_at > now - timedelta(days=auto_days), ~reminded_marker),
                  Order.id, order_ids)
    reminded = 0
    for oid in session.scalars(due.limit(BATCH)).all():
        order = session.get(Order, oid, with_for_update=True)
        session.refresh(order)
        if order.order_status != OrderStatus.AWAITING_ACCEPTANCE or session.scalar(
                select(reminded_marker).where(Order.id == oid)):
            session.rollback()
            continue
        due_at = pr.acceptance_deadline(order.awaiting_acceptance_at, auto_days)
        audit.record(session, actor_id=None, action="ACCEPT_REMINDER", entity_type="order", entity_id=oid,
                     new={"due_at": due_at.isoformat()})
        notifications.notify(session, account_id=order.customer_id, order_id=oid, msg_code="ACCEPT_REMINDER",
                             code=order.code, due_at=due_at.isoformat())
        session.commit()
        reminded += 1
    return {"auto_accepted": accepted, "reminded": reminded}


def email_retry(session: Session, *, order_ids: list[int] | None = None, **_: Any) -> dict[str, Any]:
    now = _now()
    q = (select(Notification.id, Account.email, Notification.title, Notification.body)
         .join(Account, Account.id == Notification.account_id)
         .where(Notification.channel == NotificationChannel.EMAIL, Notification.sent_at.is_(None),
                Notification.created_at < now - EMAIL_RETRY_MIN_AGE, Notification.created_at > now - EMAIL_RETRY_MAX_AGE))
    rows = [tuple(r) for r in session.execute(_scoped(q, Notification.order_id, order_ids).limit(BATCH)).all() if r[1]]
    session.rollback()                                      # nothing held while talking to the mail server
    if rows:
        notifications._send(get_mailer(), rows)
    sent = session.scalar(select(func.count()).select_from(Notification).where(
        Notification.id.in_([r[0] for r in rows] or [-1]), Notification.sent_at.is_not(None))) if rows else 0
    return {"tried": len(rows), "sent": sent or 0}


def photo_purge(session: Session, *, order_ids: list[int] | None = None, storage: ObjectStorage | None = None,
                enabled: bool | None = None, **_: Any) -> dict[str, Any]:
    if enabled is None:                                     # only tests pass it: the shared setting stays untouched
        enabled = CatalogRepository(session).setting("photo_purge_enabled", False) is True
    cutoff = _now() - timedelta(days=PURGE_AFTER_DAYS)
    finished = or_(and_(Order.order_status == OrderStatus.COMPLETED, func.coalesce(Order.completed_at, Order.updated_at) < cutoff),
                   and_(Order.order_status == OrderStatus.CANCELLED, Order.updated_at < cutoff))
    kept = exists().where(HandwritingStyle.id == OrderInput.handwriting_style_id, HandwritingStyle.keep_consent.is_(True))
    q = (select(OrderInput.id).join(Order, Order.id == OrderInput.order_id)
         .where(OrderInput.kind.in_((OrderInputKind.ORIGINAL_IMAGE, OrderInputKind.HANDWRITING_SAMPLE)),
                OrderInput.file_url.is_not(None), OrderInput.deleted_at.is_(None), finished,
                ~and_(OrderInput.kind == OrderInputKind.HANDWRITING_SAMPLE, kept)))
    ids = list(session.scalars(_scoped(q, OrderInput.order_id, order_ids).order_by(OrderInput.id).limit(BATCH)))
    if not enabled or storage is None:
        session.rollback()
        return {"dry_run": True, "would_delete": len(ids), "storage": storage is not None}
    deleted, failed = 0, 0
    for iid in ids:
        row = session.get(OrderInput, iid, with_for_update=True)
        if row is None or row.deleted_at is not None:
            session.rollback()
            continue
        try:
            storage.delete(row.file_url)
        except Exception:                                   # noqa: BLE001 - try again next run
            log.exception("purge: could not delete input %s", iid)
            session.rollback()
            failed += 1
            continue
        row.deleted_at = _now()
        audit.record(session, actor_id=None, action="INPUT_PURGE", entity_type="order", entity_id=row.order_id,
                     old={"input_id": iid, "kind": row.kind.value}, reason="BR-23: xoá ảnh của khách sau 90 ngày")
        session.commit()
        deleted += 1
    return {"dry_run": False, "deleted": deleted, "failed": failed}


JOBS: dict[str, Callable[..., dict[str, Any]]] = {
    "quotation_expiry": quotation_expiry, "deposit_deadline": deposit_deadline, "acceptance": acceptance,
    "email_retry": email_retry, "photo_purge": photo_purge,
}


# --------------------------------------------------------------------------------------------------- runner
def _storage() -> ObjectStorage | None:
    try:
        from app.integrations.storage import get_storage
        return get_storage()
    except Exception:                                       # noqa: BLE001 - not configured: the purge stays a dry run
        return None


def run_all(*, only: list[str] | None = None, order_ids: list[int] | None = None, storage: ObjectStorage | None = None,
            actor_id: int | None = None, session_factory: Callable[[], Session] | None = None) -> dict[str, Any]:
    """Run the jobs once. Returns {"ran": bool, "results": {job: {...} | {"error": ...}}, "started_at", "seconds"}."""
    started, t0 = _now(), time.monotonic()
    names = [n for n in JOBS if only is None or n in only]
    with get_engine().connect() as lock_conn:
        if not lock_conn.execute(text("select pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar():
            return {"ran": False, "reason": "Một lần chạy khác đang diễn ra.", "results": {}, "started_at": started.isoformat(),
                    "seconds": 0.0}
        try:
            results: dict[str, Any] = {}
            store = storage if storage is not None else (_storage() if "photo_purge" in names else None)
            for name in names:
                with (session_factory or _factory())() as session:
                    try:
                        results[name] = JOBS[name](session, order_ids=order_ids, storage=store)
                    except Exception as exc:                  # noqa: BLE001 - the next job still runs
                        session.rollback()
                        log.exception("background job %s failed", name)
                        results[name] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
            out = {"ran": True, "results": results, "started_at": started.isoformat(),
                   "seconds": round(time.monotonic() - t0, 2)}
            if order_ids is not None:                         # a scoped run (tests) leaves no trace in the shared log
                return out
            with (session_factory or _factory())() as session:
                audit.record(session, actor_id=actor_id, action="JOBS_RUN", entity_type="system", entity_id=None,
                             new={**out, "only": only, "scoped": order_ids is not None})
                session.commit()
            return out
        finally:
            lock_conn.execute(text("select pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            lock_conn.commit()


def last_run(session: Session) -> dict[str, Any] | None:
    row = session.scalars(select(AuditLog).where(AuditLog.action == "JOBS_RUN").order_by(AuditLog.id.desc()).limit(1)).first()
    if row is None:
        return None
    return {**(row.new_value or {}), "actor_id": row.actor_id, "recorded_at": row.created_at.isoformat()}
