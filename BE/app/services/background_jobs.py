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
                     more than `image_retention_days` (90) ago are deleted from storage, unless the sample belongs to a handwriting style
                     the customer agreed to keep. OT-2 O2: also the photos of sample-sheet pages of styles not kept
                     (`keep_consent` false), untouched that long and not waiting for review (the traced strokes stay).
                     DRY RUN (count only) unless `system_settings.photo_purge_enabled` is true.
* ai_chat_purge      0031: the text of the AI conversations of the same orders, after the same time, with the same switch
                     (the customer agrees to it in the AI chat data policy). Rows, flags and counts stay.

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
from app.models.order import (HandwritingStyle, HandwritingStylePage, Order, OrderInput, OrderInputKind, OrderStatus,
                              StyleStatus)
from app.models.sketch import Quotation, QuotationStatus
from app.models.studio import AiSession, StudioDraft
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


def _style_pages_due(session: Session, cutoff: datetime, style_ids: list[int] | None) -> list[int]:
    """OT-2 O2: photos of sample-sheet pages of styles the customer did not ask to keep, untouched for `image_retention_days`
    and not waiting for review. The traced strokes (read_result) and an approved glyph set stay; only the photo goes."""
    q = (select(HandwritingStylePage.id).join(HandwritingStyle, HandwritingStyle.id == HandwritingStylePage.style_id)
         .where(HandwritingStyle.keep_consent.is_(False), HandwritingStyle.updated_at < cutoff,
                HandwritingStyle.status != StyleStatus.PENDING_REVIEW,
                HandwritingStylePage.read_result["photo_deleted_at"].astext.is_(None)))
    if style_ids is not None:
        q = q.where(HandwritingStylePage.style_id.in_(style_ids or [-1]))
    return list(session.scalars(q.order_by(HandwritingStylePage.id).limit(BATCH)))


def _purge_style_pages(session: Session, ids: list[int], storage: ObjectStorage) -> tuple[int, int]:
    deleted = failed = 0
    for pid in ids:
        row = session.get(HandwritingStylePage, pid, with_for_update=True)
        if row is None or row.read_result.get("photo_deleted_at"):
            session.rollback()
            continue
        try:
            storage.delete(row.file_url)
        except Exception:                                   # noqa: BLE001 - try again next run
            log.exception("purge: could not delete style page %s", pid)
            session.rollback()
            failed += 1
            continue
        row.read_result = {**row.read_result, "photo_deleted_at": _now().isoformat()}
        audit.record(session, actor_id=None, action="STYLE_PHOTO_PURGE", entity_type="handwriting_style",
                     entity_id=row.style_id, old={"page_no": row.page_no}, reason="NFR-12: xoá ảnh phiếu mẫu sau 90 ngày")
        session.commit()
        deleted += 1
    return deleted, failed


def photo_purge(session: Session, *, order_ids: list[int] | None = None, storage: ObjectStorage | None = None,
                enabled: bool | None = None, style_ids: list[int] | None = None, **_: Any) -> dict[str, Any]:
    if enabled is None:                                     # only tests pass it: the shared setting stays untouched
        enabled = CatalogRepository(session).setting("photo_purge_enabled", False) is True
    days = PURGE_AFTER_DAYS if PURGE_AFTER_DAYS == 0 else _int_setting(session, "image_retention_days", PURGE_AFTER_DAYS)
    cutoff = _now() - timedelta(days=days)
    finished = or_(and_(Order.order_status == OrderStatus.COMPLETED, func.coalesce(Order.completed_at, Order.updated_at) < cutoff),
                   and_(Order.order_status == OrderStatus.CANCELLED, Order.updated_at < cutoff))
    kept = exists().where(HandwritingStyle.id == OrderInput.handwriting_style_id, HandwritingStyle.keep_consent.is_(True))
    q = (select(OrderInput.id).join(Order, Order.id == OrderInput.order_id)
         .where(OrderInput.kind.in_((OrderInputKind.ORIGINAL_IMAGE, OrderInputKind.HANDWRITING_SAMPLE)),
                OrderInput.file_url.is_not(None), OrderInput.deleted_at.is_(None), finished,
                ~and_(OrderInput.kind == OrderInputKind.HANDWRITING_SAMPLE, kept)))
    ids = list(session.scalars(_scoped(q, OrderInput.order_id, order_ids).order_by(OrderInput.id).limit(BATCH)))
    # a run scoped to orders (tests) never touches style photos unless it also names the styles
    style_pages = None if (order_ids is not None and style_ids is None) else _style_pages_due(session, cutoff, style_ids)
    if not enabled or storage is None:
        session.rollback()
        out = {"dry_run": True, "would_delete": len(ids), "storage": storage is not None}
        return out if style_pages is None else {**out, "style_pages_would_delete": len(style_pages)}
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
    out = {"dry_run": False, "deleted": deleted, "failed": failed}
    if style_pages is None:
        return out
    s_deleted, s_failed = _purge_style_pages(session, style_pages, storage)
    return {**out, "style_pages_deleted": s_deleted, "style_pages_failed": s_failed}


def ai_chat_purge(session: Session, *, order_ids: list[int] | None = None, enabled: bool | None = None,
                  **_: Any) -> dict[str, Any]:
    """0031: the text of the AI conversations of orders COMPLETED or CANCELLED more than `image_retention_days` (90) ago is
    wiped (rows, flags and counts stay: chat_sessions.wipe), the conversations of the order itself and of the studio draft
    that led to it. Same rule and same switch as the customer's photos (BR-23): a dry run unless `photo_purge_enabled`."""
    from app.services.ai import chat_sessions
    if enabled is None:                                     # only tests pass it: the shared setting stays untouched
        enabled = CatalogRepository(session).setting("photo_purge_enabled", False) is True
    days = PURGE_AFTER_DAYS if PURGE_AFTER_DAYS == 0 else _int_setting(session, "image_retention_days", PURGE_AFTER_DAYS)
    cutoff = _now() - timedelta(days=days)
    finished = or_(and_(Order.order_status == OrderStatus.COMPLETED, func.coalesce(Order.completed_at, Order.updated_at) < cutoff),
                   and_(Order.order_status == OrderStatus.CANCELLED, Order.updated_at < cutoff))
    of_orders = (select(AiSession.id, Order.id.label("oid")).join(Order, Order.id == AiSession.order_id)
                 .where(AiSession.deleted_at.is_(None), finished))
    of_drafts = (select(AiSession.id, Order.id.label("oid")).join(StudioDraft, StudioDraft.id == AiSession.draft_id)
                 .join(Order, Order.id == StudioDraft.order_id).where(AiSession.deleted_at.is_(None), finished))
    due = [tuple(r) for r in session.execute(_scoped(of_orders, Order.id, order_ids).order_by(AiSession.id).limit(BATCH))]
    due += [tuple(r) for r in session.execute(_scoped(of_drafts, Order.id, order_ids).order_by(AiSession.id).limit(BATCH))]
    if not enabled:
        session.rollback()
        return {"dry_run": True, "would_delete": len(due)}
    deleted = 0
    for sid, oid in due:
        sess = session.get(AiSession, sid, with_for_update=True)
        if sess is None or sess.deleted_at is not None:
            session.rollback()
            continue
        chat_sessions.wipe(session, sess, reason="RETENTION", actor_id=None, ip=None, order_id=oid)
        session.commit()
        deleted += 1
    return {"dry_run": False, "deleted": deleted}


def stuck_orders(session: Session, *, order_ids: list[int] | None = None, **_: Any) -> dict[str, Any]:
    """D08 (audit 2026-11-27): remind the customer of an unpaid balance; tell the Managers about an order that has waited too
    long for the balance or for collection (services/order_exits.py)."""
    from app.services import order_exits as ox
    return ox.follow_up(session, order_ids=order_ids, settings={
        "remind": _int_setting(session, "final_payment_remind_days", ox.DEFAULT_REMIND_DAYS),
        "overdue": _int_setting(session, "final_payment_overdue_days", ox.DEFAULT_OVERDUE_DAYS),
        "pickup": _int_setting(session, "pickup_overdue_days", ox.DEFAULT_OVERDUE_DAYS)})


def robot_watch(session: Session, *, order_ids: list[int] | None = None, **_: Any) -> dict[str, Any]:
    """TP-08 (audit 2026-11-27): a workstation that goes silent while its robot has a run open was only noticed when somebody
    opened a robot screen (the check ran inside those requests). Here it runs on the clock: the orange alerts AGENT_OFFLINE
    and RUN_OUTCOME_UNKNOWN are raised, and e-mailed where the catalogue says so, also when nobody is looking."""
    if order_ids is not None:                               # a scoped run (tests of other jobs) does not sweep every robot
        return {"skipped": True}
    from app.services.robot_ops import RobotOpsService, dispatch_mail
    svc = RobotOpsService(session, None)
    raised = svc.sweep_stale()
    session.commit()
    if svc.pending_mail:
        dispatch_mail(list(svc.pending_mail))
    return {"alerts_raised": raised}


JOBS: dict[str, Callable[..., dict[str, Any]]] = {
    "quotation_expiry": quotation_expiry, "deposit_deadline": deposit_deadline, "acceptance": acceptance,
    "stuck_orders": stuck_orders, "robot_watch": robot_watch,
    "email_retry": email_retry, "photo_purge": photo_purge, "ai_chat_purge": ai_chat_purge,
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
