"""Notification center (FR-27, FR-57; Phase 4e). Every signed-in role has its own list.

GET  /me/notifications                newest first, `before_id` paging, `unread_only`
GET  /me/notifications/unread-count   the badge
POST /me/notifications/{id}/read      idempotent
POST /me/notifications/read-all
GET  /me/notifications/stream         Server-Sent Events: `ready` (unread count) then one `notification` per new row; a comment
                                      line every HEARTBEAT_S seconds; the server closes after MAX_STREAM_S and the client
                                      reconnects. Bearer token in the Authorization header (no token in the URL), so the browser
                                      side uses fetch streaming (e.g. @microsoft/fetch-event-source), not the bare EventSource.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentAccount, SessionDep, current_principal
from app.api.schemas import ErrorOut
from app.models.notification import NotificationType
from app.services import notification_stream
from app.services.notifications import NotificationService

router = APIRouter(prefix="/me/notifications", tags=["Notifications"])

HEARTBEAT_S = 20.0
MAX_STREAM_S = 30 * 60.0


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: int | None
    type: NotificationType
    msg_code: str | None
    title: str
    body: str
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    unread_count: int
    next_before_id: int | None


class UnreadOut(BaseModel):
    unread_count: int


class ReadAllOut(BaseModel):
    updated: int


@router.get("", response_model=NotificationPage, summary="FR-27 Thông báo của tôi (mới nhất trước)")
def list_notifications(session: SessionDep, account: CurrentAccount, unread_only: bool = False,
                       before_id: Annotated[int | None, Query(ge=1)] = None,
                       limit: Annotated[int, Query(ge=1, le=100)] = 20) -> NotificationPage:
    page = NotificationService(session, account).list(unread_only=unread_only, before_id=before_id, limit=limit)
    return NotificationPage(items=[NotificationOut.model_validate(n) for n in page["items"]],
                            unread_count=page["unread_count"], next_before_id=page["next_before_id"])


@router.get("/unread-count", response_model=UnreadOut, summary="FR-27 Số thông báo chưa đọc")
def unread_count(session: SessionDep, account: CurrentAccount) -> UnreadOut:
    return UnreadOut(unread_count=NotificationService(session, account).unread_count())


@router.post("/read-all", response_model=ReadAllOut, summary="FR-27 Đánh dấu tất cả đã đọc")
def read_all(session: SessionDep, account: CurrentAccount) -> ReadAllOut:
    return ReadAllOut(updated=NotificationService(session, account).mark_all_read())


@router.post("/{notification_id}/read", response_model=NotificationOut, responses={404: {"model": ErrorOut}},
             summary="FR-27 Đánh dấu một thông báo đã đọc")
def read_one(notification_id: int, session: SessionDep, account: CurrentAccount) -> NotificationOut:
    return NotificationOut.model_validate(NotificationService(session, account).mark_read(notification_id))


def _authenticate(request: Request) -> tuple[int, int]:
    """Same checks as every route, in a short session of its own: the stream must not hold a pooled connection for minutes."""
    from app.db.session import _factory
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header[:7].lower() == "bearer " else None
    with _factory()() as session:
        principal = current_principal(request, session, token)
        unread = NotificationService(session, principal.account).unread_count()
        return principal.account.id, unread


def _sse(event: str | None, data: dict | None = None, *, id_: int | None = None) -> str:
    lines = []
    if id_ is not None:
        lines.append(f"id: {id_}")
    if event:
        lines.append(f"event: {event}")
    lines.append("data: " + json.dumps(data or {}, ensure_ascii=False))
    return "\n".join(lines) + "\n\n"


@router.get("/stream", summary="FR-27 Nhận thông báo mới tức thời (Server-Sent Events)",
            responses={200: {"content": {"text/event-stream": {}}}, 401: {"model": ErrorOut}})
async def stream(request: Request) -> StreamingResponse:
    account_id, unread = await run_in_threadpool(_authenticate, request)
    queue = notification_stream.broker.subscribe(account_id)
    loop = asyncio.get_running_loop()
    heartbeat, deadline = HEARTBEAT_S, loop.time() + MAX_STREAM_S

    async def events():
        try:
            yield "retry: 5000\n" + _sse("ready", {"unread_count": unread})
            while loop.time() < deadline:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=min(heartbeat, max(deadline - loop.time(), 0.01)))
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _sse("notification", item, id_=item.get("id"))
        finally:
            notification_stream.broker.unsubscribe(account_id, queue)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

