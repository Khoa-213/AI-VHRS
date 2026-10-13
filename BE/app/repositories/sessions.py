"""Login-session storage (see migrations/0003)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.account import AuthSession


class SessionRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, row: AuthSession) -> AuthSession:
        self.s.add(row)
        self.s.flush()
        return row

    def get_active(self, session_id: uuid.UUID, account_id: int) -> AuthSession | None:
        row = self.s.get(AuthSession, session_id)
        if row is None or row.account_id != account_id or row.revoked_at is not None:
            return None
        if row.expires_at <= datetime.now(timezone.utc):
            return None
        return row

    def revoke(self, session_id: uuid.UUID) -> None:
        self.s.execute(update(AuthSession)
                       .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
                       .values(revoked_at=datetime.now(timezone.utc)))

    def revoke_all(self, account_id: int, *, except_id: uuid.UUID | None = None) -> None:
        stmt = update(AuthSession).where(AuthSession.account_id == account_id, AuthSession.revoked_at.is_(None))
        if except_id is not None:
            stmt = stmt.where(AuthSession.id != except_id)
        self.s.execute(stmt.values(revoked_at=datetime.now(timezone.utc)))
