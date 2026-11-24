"""Conversations with the order assistant (owner request 2026-11-24, migration 0031): several per order ("new chat"), listed
like the sidebar of a chat app, renamed, deleted by the customer while the order is a draft, wiped by the retention job.

* A conversation is an `ai_sessions` row. A new one starts with a message sent with `new_session: true`: the assistant does
  not remember the earlier conversations of the order, but it always sees the order as it is now.
* Deleting (customer, or the retention job) never removes the rows: the text of the messages and the tool calls' arguments
  and results are wiped, the title goes, `deleted_at` / `deleted_reason` are set. The rows stay because the daily caps count
  them, the safety flags (e.g. FORGERY_RISK) stay for the workshop, and the proposals stay part of the order's history
  (the pending ones are rejected).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, null, select, text, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.studio import AiMessage, AiProposal, AiSession, AiToolCall
from app.services import audit

MAX_SESSIONS_PER_ORDER = 20
TITLE_MAX = 120
AUTO_TITLE = 60                         # characters of the first message shown as the title of an unnamed conversation
PREVIEW = 140


def _clip(value: str | None, n: int) -> str:
    s = re.sub(r"\s+", " ", value or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def active(session: Session, order_id: int) -> list[AiSession]:
    """The conversations of an order the customer still sees, most recently used first."""
    return list(session.scalars(select(AiSession).where(AiSession.order_id == order_id, AiSession.deleted_at.is_(None))
                                .order_by(func.coalesce(AiSession.last_message_at, AiSession.created_at).desc(),
                                          AiSession.id.desc())))


def latest(session: Session, order_id: int) -> AiSession | None:
    rows = active(session, order_id)
    return rows[0] if rows else None


def get(session: Session, order_id: int, session_id: int) -> AiSession:
    sess = session.get(AiSession, session_id)
    if sess is None or sess.order_id != order_id or sess.deleted_at is not None:
        raise AppError(404, "SESSION_NOT_FOUND", "Không tìm thấy cuộc chat này của đơn.")
    return sess


def pick(session: Session, order_id: int, session_id: int | None, new_session: bool) -> AiSession | None:
    """The conversation a message goes to. None: a new one is started (asked for, or the order has none yet)."""
    if new_session and session_id is not None:
        raise AppError(422, "INVALID_SESSION_CHOICE", "Chọn một cuộc chat có sẵn (session_id) hoặc bắt đầu cuộc chat mới, không cả hai.")
    if session_id is not None:
        return get(session, order_id, session_id)
    if new_session:
        if len(active(session, order_id)) >= MAX_SESSIONS_PER_ORDER:
            raise AppError(409, "TOO_MANY_SESSIONS",
                           f"Đơn này đã có {MAX_SESSIONS_PER_ORDER} cuộc chat. Hãy tiếp tục hoặc xoá bớt một cuộc chat cũ.",
                           {"max": MAX_SESSIONS_PER_ORDER})
        return None
    return latest(session, order_id)


def rename(session: Session, sess: AiSession, title: str, *, actor_id: int, ip: str | None) -> AiSession:
    value = _clip(title, TITLE_MAX + 1)
    if not value or len(value) > TITLE_MAX:
        raise AppError(422, "INVALID_TITLE", f"Tên cuộc chat cần 1 đến {TITLE_MAX} ký tự.")
    old = sess.title
    sess.title = value
    session.flush()
    audit.record(session, actor_id=actor_id, action="AI_SESSION_RENAME", entity_type="order", entity_id=sess.order_id,
                 old={"session_id": sess.id, "title": old}, new={"title": value}, ip=ip)
    return sess


def wipe(session: Session, sess: AiSession, *, reason: str, actor_id: int | None, ip: str | None,
         order_id: int | None = None) -> int:
    """Delete a conversation's text (CUSTOMER or RETENTION). Returns how many messages were wiped. `order_id`: the order a
    studio conversation led to (the audit row is filed under the order either way)."""
    now = datetime.now(timezone.utc)
    ids = list(session.scalars(select(AiMessage.id).where(AiMessage.session_id == sess.id)))
    session.execute(update(AiMessage).where(AiMessage.session_id == sess.id).values(content=""),
                    execution_options={"synchronize_session": False})
    if ids:
        session.execute(update(AiToolCall).where(AiToolCall.message_id.in_(ids)).values(args={}, result=null()),   # result: SQL NULL, not JSON null
                        execution_options={"synchronize_session": False})
    rejected = list(session.scalars(update(AiProposal).where(AiProposal.session_id == sess.id, AiProposal.status == "PENDING")
                                    .values(status="REJECTED", decided_at=now).returning(AiProposal.id),
                                    execution_options={"synchronize_session": False}))
    flags = list(sess.flags or [])
    sess.title, sess.deleted_at, sess.deleted_reason = None, now, reason
    session.flush()
    audit.record(session, actor_id=actor_id, action="AI_SESSION_DELETE" if reason == "CUSTOMER" else "AI_SESSION_PURGE",
                 entity_type="order", entity_id=sess.order_id or order_id,
                 old={"session_id": sess.id, "draft_id": sess.draft_id, "messages": len(ids), "flags": flags,
                      "rejected_proposals": rejected},
                 reason="Khách xoá cuộc chat" if reason == "CUSTOMER" else "Xoá nội dung chat sau thời hạn lưu", ip=ip)
    session.expire_all()
    return len(ids)


# ---------------------------------------------------------------------------------------------------------- lists
_LIST = """
SELECT s.id, s.order_id, o.code AS order_code, o.order_type, o.order_status, s.title, s.created_at, s.last_message_at,
       COALESCE(s.last_message_at, s.created_at) AS activity,
       (SELECT count(*) FROM ai_messages m WHERE m.session_id = s.id) AS message_count,
       (SELECT m.content FROM ai_messages m WHERE m.session_id = s.id AND m.role = 'USER' ORDER BY m.id LIMIT 1) AS first_text,
       (SELECT m.content FROM ai_messages m WHERE m.session_id = s.id ORDER BY m.id DESC LIMIT 1) AS last_text
FROM ai_sessions s JOIN orders o ON o.id = s.order_id
WHERE s.customer_id = :customer AND s.deleted_at IS NULL {where}
ORDER BY activity DESC, s.id DESC
LIMIT :limit
"""


def _row(r: Any) -> dict[str, Any]:
    from app.models.order import OrderStatus
    from app.services.orders import EDITABLE
    status = r.order_status.value if hasattr(r.order_status, "value") else str(r.order_status)
    return {"id": r.id, "order_id": r.order_id, "order_code": r.order_code,
            "order_type": r.order_type.value if hasattr(r.order_type, "value") else str(r.order_type),
            "order_status": status, "title": r.title or _clip(r.first_text, AUTO_TITLE) or None,
            "title_is_custom": r.title is not None, "preview": _clip(r.last_text, PREVIEW) or None,
            "message_count": int(r.message_count), "created_at": r.created_at, "last_message_at": r.last_message_at,
            "can_chat": OrderStatus(status) in EDITABLE, "can_delete": status == OrderStatus.DRAFT.value}


def _cursor(activity: datetime, sid: int) -> str:
    return f"{int(activity.timestamp() * 1_000_000)}-{sid}"


def _parse_cursor(cursor: str) -> tuple[datetime, int]:
    m = re.fullmatch(r"(\d{1,20})-(\d{1,19})", cursor or "")
    if not m:
        raise AppError(422, "INVALID_CURSOR", "Tham số cursor không hợp lệ.")
    return datetime.fromtimestamp(int(m.group(1)) / 1_000_000, tz=timezone.utc), int(m.group(2))


def of_customer(session: Session, customer_id: int, *, limit: int = 20, cursor: str | None = None) -> dict[str, Any]:
    """Every conversation of the customer across orders, most recently used first (sidebar). Deleted ones are left out."""
    params: dict[str, Any] = {"customer": customer_id, "limit": limit + 1}
    where = "AND s.order_id IS NOT NULL"
    if cursor:
        at, sid = _parse_cursor(cursor)
        where += " AND (COALESCE(s.last_message_at, s.created_at), s.id) < (:at, :sid)"
        params.update(at=at, sid=sid)
    rows = list(session.execute(text(_LIST.format(where=where)), params))
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [_row(r) for r in rows],
            "next_cursor": _cursor(rows[-1].activity, rows[-1].id) if more and rows else None}


def of_order(session: Session, customer_id: int, order_id: int) -> list[dict[str, Any]]:
    rows = session.execute(text(_LIST.format(where="AND s.order_id = :order")),
                           {"customer": customer_id, "order": order_id, "limit": MAX_SESSIONS_PER_ORDER * 5})
    return [_row(r) for r in rows]
