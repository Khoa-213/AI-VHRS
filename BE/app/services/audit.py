"""Audit trail writer (BR-24, NFR-11)."""
from typing import Any

from sqlalchemy.orm import Session

from app.models.account import AuditLog
from app.repositories.accounts import AuditRepository


def record(session: Session, *, actor_id: int | None, action: str, entity_type: str | None = None,
           entity_id: int | None = None, old: dict[str, Any] | None = None,
           new: dict[str, Any] | None = None, reason: str | None = None,
           ip: str | None = None, policy_version: str | None = None) -> AuditLog:
    return AuditRepository(session).add(AuditLog(
        actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id,
        old_value=old, new_value=new, reason=reason, ip_address=ip, policy_version=policy_version))
