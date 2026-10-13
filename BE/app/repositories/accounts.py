"""Data access only: no business rules here."""
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.account import Account, AccountStatus, AuditLog, Role


class AccountRepository:
    def __init__(self, session: Session):
        self.s = session

    def get(self, account_id: int) -> Account | None:
        return self.s.get(Account, account_id)

    def get_by_email(self, email: str) -> Account | None:
        return self.s.scalar(select(Account).where(func.lower(Account.email) == email.lower()))

    def role_by_code(self, code: str) -> Role | None:
        return self.s.scalar(select(Role).where(Role.code == code))

    def role_by_id(self, role_id: int) -> Role | None:
        return self.s.get(Role, role_id)

    def add(self, account: Account) -> Account:
        self.s.add(account)
        self.s.flush()
        self.s.refresh(account)
        return account

    def search(self, *, role_id: int | None, status: AccountStatus | None, q: str | None,
               offset: int, limit: int) -> tuple[list[Account], int]:
        stmt = select(Account)
        if role_id is not None:
            stmt = stmt.where(Account.role_id == role_id)
        if status is not None:
            stmt = stmt.where(Account.status == status)
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(or_(func.lower(Account.email).like(like), func.lower(Account.full_name).like(like)))
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.s.scalars(stmt.order_by(Account.id).offset(offset).limit(limit)).unique().all()
        return list(rows), total


class AuditRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, entry: AuditLog) -> AuditLog:
        self.s.add(entry)
        self.s.flush()
        return entry

    def search(self, *, actor_id: int | None, action: str | None, entity_type: str | None,
               entity_id: int | None, offset: int, limit: int) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog)
        for col, val in ((AuditLog.actor_id, actor_id), (AuditLog.action, action),
                         (AuditLog.entity_type, entity_type), (AuditLog.entity_id, entity_id)):
            if val is not None:
                stmt = stmt.where(col == val)
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.s.scalars(stmt.order_by(AuditLog.id.desc()).offset(offset).limit(limit)).all()
        return list(rows), total
