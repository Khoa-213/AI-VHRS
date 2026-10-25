"""Authentication / authorization dependencies (FR-03, NFR-08)."""
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core import security
from app.core.net import resolve_client_ip
from app.core.errors import AppError
from app.db.session import get_session
from app.models.account import Account, AccountStatus
from app.repositories.accounts import AccountRepository
from app.repositories.sessions import SessionRepository

# tokenUrl powers the "Authorize" form in Swagger UI (username = email).
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)
SessionDep = Annotated[Session, Depends(get_session)]


@dataclass(frozen=True)
class Principal:
    account: Account
    session_id: uuid.UUID


_JOB_IN_PATH = re.compile(r"/technician/jobs/(\d+)")
AGENT_SESSION = uuid.UUID(int=0)       # marks a request made by a Robot Agent acting for the technician of its live job


def _agent_principal(session: Session, token: str, request: Request) -> Principal:
    """A Robot Agent key opens ONLY the technician routes, as the technician who holds the live job on the agent's robot."""
    from app.services.robot_link import agent_identity, technician_for_agent   # late import: services import deps indirectly
    path = request.url.path
    if "/technician/" not in path or "/robot-commands" in path or "/agent-session" in path:
        raise AppError(401, "INVALID_AGENT_KEY", "Khoá agent chỉ dùng cho API kỹ thuật viên.")
    ident = agent_identity(session, token)
    m = _JOB_IN_PATH.search(path)
    acc = technician_for_agent(session, ident.robot_id, int(m.group(1)) if m else None, ident.account_id)
    return Principal(account=acc, session_id=AGENT_SESSION)


def current_principal(request: Request, session: SessionDep, token: Annotated[str | None, Depends(_oauth2)]) -> Principal:
    if token is None:
        raise AppError(401, "NOT_AUTHENTICATED", "Vui lòng đăng nhập.")
    if token.startswith("vhrs_ak_"):
        return _agent_principal(session, token, request)
    payload = security.decode_token(token, security.ACCESS)
    try:
        sid = uuid.UUID(str(payload.get("sid")))
    except ValueError as exc:
        raise AppError(401, "NOT_AUTHENTICATED", "Phiên đăng nhập không còn hiệu lực.") from exc
    acc = AccountRepository(session).get(int(payload["sub"]))
    # Re-read from DB each request so logout, lock and role changes take effect immediately.
    if (acc is None or acc.status != AccountStatus.ACTIVE
            or SessionRepository(session).get_active(sid, acc.id) is None
            or (acc.locked_until and acc.locked_until > datetime.now(timezone.utc))):
        raise AppError(401, "NOT_AUTHENTICATED", "Phiên đăng nhập không còn hiệu lực.")
    return Principal(account=acc, session_id=sid)


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def current_account(principal: PrincipalDep) -> Account:
    return principal.account


CurrentAccount = Annotated[Account, Depends(current_account)]


def require_roles(*codes: str) -> Callable[[Account], Account]:
    def checker(acc: CurrentAccount) -> Account:
        if acc.role.code not in codes:
            raise AppError(403, "FORBIDDEN", "Bạn không có quyền thực hiện thao tác này.")
        return acc
    return checker


def client_ip(request: Request) -> str | None:
    """Peer address for audit_logs.ip_address (INET); None when it is not a literal IP."""
    return resolve_client_ip(request)
