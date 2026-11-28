"""Authentication / authorization dependencies (FR-03, NFR-08)."""
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.net import resolve_client_ip
from app.core.errors import AppError
from app.db.session import get_session
from app.models.account import Account, AccountStatus
from app.repositories.sessions import SessionRepository

# tokenUrl powers the "Authorize" form in Swagger UI (username = email).
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)
SessionDep = Annotated[Session, Depends(get_session)]


@dataclass(frozen=True)
class Principal:
    account: Account
    session_id: uuid.UUID
    agent_robot_id: int | None = None       # set when the request was made with a Robot Agent key: the robot that key belongs to


_JOB_IN_PATH = re.compile(r"/technician/jobs/(\d+)")
_RUN_IN_PATH = re.compile(r"/technician/runs/([^/]+)$")
# SR-05 (audit 2026-11-27): an agent key opened almost every /technician route, so a leaked key could end a job, report an
# incident or submit photos in the technician's name. These are the calls the Robot Agent really makes
# (robot_agent/vhrs_agent/bridge.py); the key opens nothing else.
_AGENT_ROUTES = (
    ("GET", re.compile(r"/technician/jobs/\d+$")),
    ("GET", re.compile(r"/technician/jobs/\d+/package$")),
    ("POST", re.compile(r"/technician/jobs/\d+/(calibration|simulation|events|runs)$")),
    ("PATCH", re.compile(r"/technician/runs/[^/]+$")),
    ("POST", re.compile(r"/technician/alerts$")),
    ("PUT", re.compile(r"/technician/robots/\d+/heartbeat$")),
)
AGENT_SESSION = uuid.UUID(int=0)       # marks a request made by a Robot Agent acting for the technician of its live job


def _agent_principal(session: Session, token: str, request: Request) -> Principal:
    """A Robot Agent key opens ONLY the technician routes, as the technician who holds the live job on the agent's robot."""
    from app.services.robot_link import agent_identity, technician_for_agent   # late import: services import deps indirectly
    path = request.url.path
    if "/technician/" not in path or "/robot-commands" in path or "/agent-session" in path:
        raise AppError(401, "INVALID_AGENT_KEY", "Khoá agent chỉ dùng cho API kỹ thuật viên.")
    if not any(request.method == method and rx.search(path) for method, rx in _AGENT_ROUTES):
        raise AppError(403, "AGENT_ROUTE_NOT_ALLOWED", "Khoá agent không dùng được cho thao tác này: việc này do kỹ thuật viên làm "
                       "bằng tài khoản của mình.")
    ident = agent_identity(session, token)
    m = _JOB_IN_PATH.search(path)
    acc = _technician_of_run(session, ident, _RUN_IN_PATH.search(path))
    if acc is None:
        acc = technician_for_agent(session, ident.robot_id, int(m.group(1)) if m else None, ident.account_id)
    # TP-06: the agent acts AS this technician, so it must stop working the moment the account does (locked, disabled).
    if (acc is None or acc.status != AccountStatus.ACTIVE
            or (acc.locked_until and acc.locked_until > datetime.now(timezone.utc))):
        raise AppError(401, "AGENT_ACCOUNT_INACTIVE", "Tài khoản kỹ thuật viên của job này đã bị khoá hoặc vô hiệu hoá.")
    return Principal(account=acc, session_id=AGENT_SESSION, agent_robot_id=ident.robot_id)


def _technician_of_run(session: Session, ident, match) -> Account | None:
    """Reporting how a run ended (`PATCH /technician/runs/{run_id}`): the agent of the robot the run ran on may always do
    that, whatever became of the job since (finished by a Manager's override, failed, cancelled). Otherwise a result that
    arrives late was refused at the door as "no active job" and the agent kept it for ever. A session key still acts only
    for its own technician. None = not that route, or not this agent's run: the usual rule decides."""
    if match is None:
        return None
    from app.models.ops import ProductionJob, RobotRun
    row = session.execute(select(ProductionJob.technician_id).join(RobotRun, RobotRun.job_id == ProductionJob.id).where(
        RobotRun.run_id == match.group(1), RobotRun.robot_id == ident.robot_id)).first()
    if row is None or (ident.account_id is not None and row[0] != ident.account_id):
        return None
    return session.get(Account, row[0])


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
    # Re-read from DB each request so logout, lock and role changes take effect immediately (account + session: one query).
    acc = SessionRepository(session).active_account(sid, int(payload["sub"]))
    if (acc is None or acc.status != AccountStatus.ACTIVE
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


async def raw_body(request: Request) -> bytes:
    """The request body, read on the event loop (AR-02).

    A webhook needs the raw bytes (signature) or the parsed JSON, and reading them is the only thing that must be awaited.
    The handler itself is a plain `def`, so FastAPI runs it in the thread pool: the synchronous database work (row locks
    included) no longer stops the one event loop, and with it every other request, while a callback is being processed."""
    return await request.body()


RawBody = Annotated[bytes, Depends(raw_body)]


def client_ip(request: Request) -> str | None:
    """Peer address for audit_logs.ip_address (INET); None when it is not a literal IP."""
    return resolve_client_ip(request)
