"""UC-48, UC-51 (FR-51): Admin-only account management and audit log."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.schemas import (AccountOut, AdminAccountCreateIn, AdminAccountUpdateIn, AuditLogOut, Page,
                             account_out)
from app.models.account import Account, AccountStatus, RoleCode
from app.repositories.accounts import AccountRepository, AuditRepository
from app.services.accounts import AccountAdminService

router = APIRouter(prefix="/admin", tags=["Admin"])
AdminDep = Annotated[Account, Depends(require_roles(RoleCode.ADMIN.value))]


@router.get("/accounts", response_model=Page[AccountOut], summary="Danh sách tài khoản")
def list_accounts(_: AdminDep, session: SessionDep, role: str | None = None, status: AccountStatus | None = None,
                  q: str | None = None, page: int = Query(1, ge=1),
                  page_size: int = Query(20, ge=1, le=100)) -> Page[AccountOut]:
    repo = AccountRepository(session)
    role_id = None
    if role:
        r = repo.role_by_code(role)
        role_id = r.id if r else -1
    rows, total = repo.search(role_id=role_id, status=status, q=q, offset=(page - 1) * page_size, limit=page_size)
    return Page(items=[account_out(a) for a in rows], total=total, page=page, page_size=page_size)


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED,
             summary="UC-48 Tạo tài khoản nội bộ (BR-01)")
def create_account(body: AdminAccountCreateIn, admin: AdminDep, session: SessionDep, request: Request) -> AccountOut:
    svc = AccountAdminService(session, admin, client_ip(request))
    return account_out(svc.create_internal(email=body.email, password=body.password, full_name=body.full_name,
                                           phone=body.phone, role_code=body.role))


@router.patch("/accounts/{account_id}", response_model=AccountOut, summary="UC-48 Khoá/mở khoá, đổi vai trò")
def update_account(account_id: int, body: AdminAccountUpdateIn, admin: AdminDep, session: SessionDep,
                   request: Request) -> AccountOut:
    svc = AccountAdminService(session, admin, client_ip(request))
    return account_out(svc.update(account_id, status=body.status, role_code=body.role, reason=body.reason))


@router.get("/audit-logs", response_model=Page[AuditLogOut], summary="UC-51 Nhật ký hoạt động")
def audit_logs(_: AdminDep, session: SessionDep, actor_id: int | None = None, action: str | None = None,
               entity_type: str | None = None, entity_id: int | None = None, page: int = Query(1, ge=1),
               page_size: int = Query(20, ge=1, le=100)) -> Page[AuditLogOut]:
    rows, total = AuditRepository(session).search(
        actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id,
        offset=(page - 1) * page_size, limit=page_size)
    return Page(items=[AuditLogOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)
