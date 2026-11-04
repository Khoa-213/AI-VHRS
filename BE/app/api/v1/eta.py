"""ETA and its postponements (Phase 4d-2: BR-15, BR-16, FR-26, UC-30).

Customer: GET /orders/{id}/eta. Workshop: GET /workshop/orders/{id}/eta (Staff of the order, Manager read-only; includes the BR-15
estimate as `suggested_eta`), POST /workshop/orders/{id}/eta (Staff of the order, any date from today, reason required).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.ops_schemas import EtaChange, EtaOut, EtaSetIn
from app.api.schemas import ErrorOut
from app.core.errors import AppError
from app.models.account import Account, RoleCode
from app.repositories.orders import OrderRepository
from app.services.eta import EtaService
from app.services.workshop_access import WorkshopAccess

router = APIRouter(tags=["ETA"])
CustomerDep = Annotated[Account, Depends(require_roles(RoleCode.CUSTOMER.value))]
WorkshopDep = Annotated[Account, Depends(require_roles(RoleCode.STAFF.value, RoleCode.MANAGER.value))]
StaffDep = Annotated[Account, Depends(require_roles(RoleCode.STAFF.value))]
_ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}}


def _out(view: dict, *, workshop: bool, suggested=None) -> EtaOut:
    history = [EtaChange.model_validate({**h, "actor_id": h["actor_id"] if workshop else None}) for h in view["history"]]
    return EtaOut(**{**view, "history": history}, suggested_eta=suggested)


@router.get("/orders/{order_id}/eta", response_model=EtaOut, responses=_ERR,
            summary="FR-26 · BR-15/16 Ngày giao dự kiến của đơn, lịch sử dời và quyền huỷ hoàn 100%")
def customer_eta(order_id: int, session: SessionDep, customer: CustomerDep) -> EtaOut:
    order = OrderRepository(session).get_owned(order_id, customer.id)
    if order is None:
        raise AppError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.")
    return _out(EtaService(session, customer).view(order), workshop=False)


@router.get("/workshop/orders/{order_id}/eta", response_model=EtaOut, responses=_ERR,
            summary="UC-30 ETA của đơn, lịch sử dời và ETA ước tính theo BR-15 nếu xác nhận lúc này")
def workshop_eta(order_id: int, session: SessionDep, actor: WorkshopDep) -> EtaOut:
    order = WorkshopAccess(session, actor).order(order_id)
    svc = EtaService(session, actor)
    return _out(svc.view(order), workshop=True, suggested=svc.estimate(order))


@router.post("/workshop/orders/{order_id}/eta", response_model=EtaOut, responses=_ERR,
             summary="UC-30 · MSG11 Staff đổi ngày giao dự kiến (bắt buộc lý do; dời muộn hơn được cộng vào BR-16)")
def set_eta(order_id: int, body: EtaSetIn, session: SessionDep, staff: StaffDep, request: Request) -> EtaOut:
    svc = EtaService(session, staff, client_ip(request))
    order = svc.set_manual(order_id, body.eta, body.reason)
    return _out(svc.view(order), workshop=True)
