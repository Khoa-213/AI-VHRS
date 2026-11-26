"""Reminders about the account's phone number (owner request 2026-11-26), as in-app notifications (bell, no e-mail).

* ADD_PHONE: at sign-in, an account with no phone number is asked to add one. Once per account, ever: the first sign-in
  without a number (an account created before this feature gets it at its next sign-in).
* VERIFY_PHONE: an account whose number is not verified is asked to verify it (SMS code, `POST /me/phone/otp`), because
  "forgot password by SMS" only works with a verified number and silently sends nothing otherwise. At sign-in at most once
  every 7 days; at once when the number is changed in the profile. Never stacked: not sent while one is still unread.

The notification rows are written through `notifications.notify` (inside the caller's transaction, never failing it). The
sign-in answer also lists the reminders just created (`TokenOut.reminders`), so the web app can open a prompt at once.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.sms import mask
from app.models.account import Account
from app.models.notification import Notification, NotificationChannel
from app.services import notifications

ADD_PHONE, VERIFY_PHONE = "ADD_PHONE", "VERIFY_PHONE"
MSG_CODES = {ADD_PHONE: "PHONE_ADD", VERIFY_PHONE: "PHONE_VER"}       # notifications.msg_code (<= 10 characters)
VERIFY_EVERY = timedelta(days=7)


def _rows(session: Session, account_id: int, msg_code: str):
    return select(Notification.id).where(Notification.account_id == account_id, Notification.msg_code == msg_code,
                                         Notification.channel == NotificationChannel.IN_APP)


def _exists(session: Session, query) -> bool:
    return session.execute(query.limit(1)).first() is not None


def _send(session: Session, acc: Account, kind: str) -> str:
    notifications.notify(session, account_id=acc.id, order_id=None, msg_code=kind,
                         phone=mask(acc.phone) if acc.phone else "")
    return kind


def _enabled() -> bool:
    return get_settings().phone_reminders_enabled


def on_sign_in(session: Session, acc: Account) -> list[str]:
    """The reminders created for this sign-in ([] most of the time)."""
    if not _enabled():
        return []
    if not acc.phone:
        if _exists(session, _rows(session, acc.id, MSG_CODES[ADD_PHONE])):
            return []
        return [_send(session, acc, ADD_PHONE)]
    if acc.phone_verified_at is not None:
        return []
    q = _rows(session, acc.id, MSG_CODES[VERIFY_PHONE])
    recent = datetime.now(timezone.utc) - VERIFY_EVERY
    if _exists(session, q.where(Notification.is_read.is_(False))) or _exists(session, q.where(Notification.created_at > recent)):
        return []
    return [_send(session, acc, VERIFY_PHONE)]


def on_phone_changed(session: Session, acc: Account) -> None:
    """A new (so unverified) number was saved in the profile: ask to verify it, unless a reminder is still unread."""
    if not _enabled() or not acc.phone or acc.phone_verified_at is not None:
        return
    if _exists(session, _rows(session, acc.id, MSG_CODES[VERIFY_PHONE]).where(Notification.is_read.is_(False))):
        return
    _send(session, acc, VERIFY_PHONE)
