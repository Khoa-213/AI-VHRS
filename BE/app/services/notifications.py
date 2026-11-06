"""Notifications (FR-27, FR-57; Phase 4e): an in-app row for every event, plus an e-mail for the messages the SRS marks
"Email + in-app" (texts and that choice live in domain/notification_messages.py).

`notify(session, ...)` runs inside the caller's transaction and never makes it fail: the rows are written in a SAVEPOINT and an
error is only logged. What leaves the process (e-mail, the live SSE push) waits for the COMMIT, so a rolled-back action sends
nothing: the ids are kept on the session and handled by an `after_commit` hook, which re-reads them in a fresh session (rows
discarded by a later rollback simply are not found). The e-mail row gets `sent_at` once the mailer accepted it; a failed send
leaves it NULL (a retry job belongs to Phase 5).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain import notification_messages as nm
from app.integrations.mailer import ConsoleMailer, get_mailer
from app.models.account import Account
from app.models.notification import Notification, NotificationChannel, NotificationType
from app.services.notification_stream import broker

log = logging.getLogger("app.notify")

_PENDING = "notify_pending"
_HOOKED = "notify_hooked"
MAIL_FOOTER = "\n\n--\nXem chi tiết trong ứng dụng AI-VHRS. Đây là email tự động, vui lòng không trả lời."


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------------------------------------- writing
def notify(session: Session, *, account_id: int | None, order_id: int | None, msg_code: str, **params: Any) -> None:
    if account_id is None:
        return
    try:
        msg = nm.render(msg_code, params)
    except Exception:                                    # noqa: BLE001 - a text bug must never break the business action
        log.exception("notification text failed: code=%s", msg_code)
        return
    log.info("notify account=%s order=%s code=%s", account_id, order_id, msg_code)
    session.flush()                                      # the caller's own pending changes fail where they belong, not here
    try:
        with session.begin_nested():
            if msg.collapse and _has_unread(session, account_id, order_id, msg.type):
                return
            rows = [_row(account_id, order_id, msg, NotificationChannel.IN_APP)]
            if msg.email:
                rows.append(_row(account_id, order_id, msg, NotificationChannel.EMAIL))
            session.add_all(rows)
            session.flush()
        _pending(session).extend(r.id for r in rows)
    except Exception:                                    # noqa: BLE001
        log.exception("notification not stored: account=%s code=%s", account_id, msg_code)


def _row(account_id: int, order_id: int | None, msg: nm.Message, channel: NotificationChannel) -> Notification:
    return Notification(account_id=account_id, order_id=order_id, type=NotificationType(msg.type), msg_code=msg.msg_code,
                        title=msg.title, body=msg.body, channel=channel, is_read=False)


def _has_unread(session: Session, account_id: int, order_id: int | None, type_: str) -> bool:
    q = select(Notification.id).where(Notification.account_id == account_id, Notification.type == NotificationType(type_),
                                      Notification.channel == NotificationChannel.IN_APP, Notification.is_read.is_(False))
    q = q.where(Notification.order_id == order_id) if order_id is not None else q.where(Notification.order_id.is_(None))
    return session.execute(q.limit(1)).first() is not None


def _pending(session: Session) -> list[int]:
    if not session.info.get(_HOOKED):
        event.listen(session, "after_commit", _after_commit)
        event.listen(session, "after_soft_rollback", _after_soft_rollback)
        session.info[_HOOKED] = True
    return session.info.setdefault(_PENDING, [])


def _after_soft_rollback(session: Session, previous_transaction) -> None:
    if previous_transaction.parent is None:              # the whole transaction, not a SAVEPOINT
        session.info.pop(_PENDING, None)


def _after_commit(session: Session) -> None:
    ids = session.info.pop(_PENDING, None)
    if ids:
        dispatch(ids)


# ---------------------------------------------------------------------------------------------------------- delivery
def _new_session() -> Session:
    from app.db.session import _factory
    return _factory()()


def dispatch(ids: list[int]) -> None:
    """After the commit: push the in-app rows to open streams and send the e-mails. Never raises."""
    try:
        with _new_session() as s:
            rows = s.execute(select(Notification, Account.email).join(Account, Account.id == Notification.account_id)
                             .where(Notification.id.in_(ids))).all()
            mails = []
            for n, email in rows:
                if n.channel == NotificationChannel.IN_APP:
                    broker.publish(n.account_id, payload(n))
                elif n.sent_at is None and email:
                    mails.append((n.id, email, n.title, n.body))
    except Exception:                                    # noqa: BLE001
        log.exception("notification dispatch failed for ids=%s", ids)
        return
    if not mails:
        return
    mailer = get_mailer()
    if isinstance(mailer, ConsoleMailer):                # dev / tests: instant, keep it in the request so tests can read it
        _send(mailer, mails)
    else:                                                # real SMTP may take seconds: never hold the response for it
        threading.Thread(target=_send, args=(mailer, mails), name="notify-mail", daemon=True).start()


def _send(mailer, mails: list[tuple[int, str, str, str]]) -> None:
    sent = []
    for nid, to, title, body in mails:
        try:
            mailer.send(to, f"[AI-VHRS] {title}", body + MAIL_FOOTER)
            sent.append(nid)
        except Exception:                                # noqa: BLE001 - sent_at stays NULL
            log.exception("notification e-mail %s not sent", nid)
    if sent:
        try:
            with _new_session() as s:
                s.execute(update(Notification).where(Notification.id.in_(sent)).values(sent_at=_now()))
                s.commit()
        except Exception:                                # noqa: BLE001
            log.exception("could not mark e-mails %s as sent", sent)


def payload(n: Notification) -> dict[str, Any]:
    return {"id": n.id, "order_id": n.order_id, "type": n.type.value, "msg_code": n.msg_code, "title": n.title, "body": n.body,
            "is_read": n.is_read, "read_at": n.read_at.isoformat() if n.read_at else None,
            "created_at": n.created_at.isoformat() if n.created_at else None}


# ---------------------------------------------------------------------------------------------------------- reading
class NotificationService:
    """The signed-in person's in-app notifications (any role). E-mail rows are a delivery log, never listed."""

    def __init__(self, session: Session, account: Account):
        self.session, self.account = session, account

    def _mine(self):
        return select(Notification).where(Notification.account_id == self.account.id,
                                          Notification.channel == NotificationChannel.IN_APP)

    def unread_count(self) -> int:
        return self.session.execute(select(func.count()).select_from(Notification).where(
            Notification.account_id == self.account.id, Notification.channel == NotificationChannel.IN_APP,
            Notification.is_read.is_(False))).scalar_one()

    def list(self, *, unread_only: bool = False, before_id: int | None = None, limit: int = 20) -> dict[str, Any]:
        q = self._mine()
        if unread_only:
            q = q.where(Notification.is_read.is_(False))
        if before_id is not None:
            q = q.where(Notification.id < before_id)
        rows = list(self.session.scalars(q.order_by(Notification.id.desc()).limit(limit + 1)))
        more = len(rows) > limit
        rows = rows[:limit]
        return {"items": rows, "unread_count": self.unread_count(), "next_before_id": rows[-1].id if more else None}

    def mark_read(self, notification_id: int) -> Notification:
        n = self.session.scalars(self._mine().where(Notification.id == notification_id).with_for_update()).first()
        if n is None:
            raise AppError(404, "NOTIFICATION_NOT_FOUND", "Không tìm thấy thông báo.")
        if not n.is_read:
            n.is_read, n.read_at = True, _now()
            self.session.flush()
        return n

    def mark_all_read(self) -> int:
        res = self.session.execute(update(Notification).where(
            Notification.account_id == self.account.id, Notification.channel == NotificationChannel.IN_APP,
            Notification.is_read.is_(False)).values(is_read=True, read_at=_now()))
        return res.rowcount or 0
