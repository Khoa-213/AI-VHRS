"""Robot operations: runs, alerts, heartbeat, status (Technical Staff), health, process compliance and the alert catalogue (Manager).

The Robot Agent calls the technician routes with the technician's own token. Alerts are only NAMED by the agent: the level, the
sentence and the action come from the catalogue. A red alert (level 4) means "press the physical E-Stop now"; it is e-mailed in the
background to the technician and the Managers.
"""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.robot_schemas import (AlertOut, AlertRaiseIn, AlertResolveIn, CatalogOut, CatalogPatch, ComplianceOut, HealthOut,
                                   HeartbeatIn, RobotStatusOut, RunCloseIn, RunOpenIn, RunOut)
from app.api.schemas import ErrorOut, Page
from app.models.account import Account, RoleCode
from app.models.ops import RobotAlert
from app.services.robot_ops import OFFLINE_AFTER_S, RobotOpsService, dispatch_mail

technician_router = APIRouter(prefix="/technician", tags=["Robot operations"])
manager_router = APIRouter(prefix="/manager", tags=["Robot operations"])
TechDep = Annotated[Account, Depends(require_roles(RoleCode.TECHNICAL_STAFF.value))]
ManagerDep = Annotated[Account, Depends(require_roles(RoleCode.MANAGER.value))]
CONFLICT = {409: {"model": ErrorOut, "description": "JOB_STATE_CONFLICT / ROBOT_BUSY / RUN_ALREADY_CLOSED"}}


def _tech(session: SessionDep, tech: TechDep, request: Request) -> RobotOpsService:
    return RobotOpsService(session, tech, client_ip(request))


def _mgr(session: SessionDep, manager: ManagerDep, request: Request) -> RobotOpsService:
    return RobotOpsService(session, manager, client_ip(request))


TechSvc = Annotated[RobotOpsService, Depends(_tech)]
MgrSvc = Annotated[RobotOpsService, Depends(_mgr)]


def _alert_out(svc: RobotOpsService, rows: list[RobotAlert]) -> list[AlertOut]:
    from app.models.ops import Robot
    codes = {r.id: r.code for r in svc.session.query(Robot).filter(Robot.id.in_({a.robot_id for a in rows}))} if rows else {}
    out = []
    for a in rows:
        o = AlertOut.model_validate(a)
        o.robot_code = codes.get(a.robot_id, "")
        out.append(o)
    return out


def _flush_mail(svc: RobotOpsService, bg: BackgroundTasks) -> None:
    if svc.pending_mail:
        bg.add_task(dispatch_mail, list(svc.pending_mail))
        svc.pending_mail.clear()


# ---------------------------------------------------------------------------------------------- Technical Staff
@technician_router.post("/jobs/{job_id}/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED, responses=CONFLICT,
                        summary="Robot Agent mở một lần chạy (cả chạy thử pen-up). Chạy robot THẬT cần `authorized:true`")
def open_run(job_id: int, body: RunOpenIn, svc: TechSvc) -> RunOut:
    return RunOut.model_validate(svc.open_run(job_id, **body.model_dump()))


@technician_router.patch("/runs/{run_id}", response_model=RunOut, responses=CONFLICT,
                         summary="Robot Agent đóng lần chạy với kết quả (DONE/STOPPED/FAULT/UNKNOWN/DRY_RUN_DONE/REFUSED); gọi lại cùng kết quả là idempotent")
def close_run(run_id: str, body: RunCloseIn, svc: TechSvc) -> RunOut:
    return RunOut.model_validate(svc.close_run(run_id, **body.model_dump()))


@technician_router.post("/alerts", response_model=AlertOut, status_code=status.HTTP_201_CREATED,
                        summary="Báo một cảnh báo theo MÃ trong danh mục (mức, câu chữ, việc cần làm lấy từ danh mục). Mức 4 gửi email")
def raise_alert(body: AlertRaiseIn, svc: TechSvc, bg: BackgroundTasks) -> AlertOut:
    alert, _ = svc.raise_alert(robot_id=body.robot_id, code=body.code, job_id=body.job_id, run_key=body.run_id, details=body.details)
    _flush_mail(svc, bg)
    return _alert_out(svc, [alert])[0]


@technician_router.get("/alerts", response_model=Page[AlertOut], summary="Cảnh báo của các robot tôi đang phụ trách (mặc định: chưa xử lý)")
def tech_alerts(svc: TechSvc, bg: BackgroundTasks, open_only: Annotated[bool, Query(alias="open")] = True,
                robot_id: int | None = None, min_level: Annotated[int, Query(ge=1, le=4)] = 1, job_id: int | None = None,
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> Page[AlertOut]:
    svc.sweep_stale()
    _flush_mail(svc, bg)
    rows, total = svc.alerts(open_only=open_only, robot_id=robot_id, min_level=min_level, job_id=job_id,
                             offset=(page - 1) * page_size, limit=page_size)
    return Page(items=_alert_out(svc, rows), total=total, page=page, page_size=page_size)


@technician_router.post("/alerts/{alert_id}/ack", response_model=AlertOut, summary="Đã thấy cảnh báo (không đóng cảnh báo)")
def tech_ack(alert_id: int, svc: TechSvc) -> AlertOut:
    return _alert_out(svc, [svc.acknowledge(alert_id)])[0]


@technician_router.post("/alerts/{alert_id}/resolve", response_model=AlertOut,
                        summary="Đóng cảnh báo mức 1..3 kèm ghi chú. Mức 4 (đỏ) chỉ Manager đóng được")
def tech_resolve(alert_id: int, body: AlertResolveIn, svc: TechSvc) -> AlertOut:
    return _alert_out(svc, [svc.resolve(alert_id, body.note)])[0]


@technician_router.put("/robots/{robot_id}/heartbeat", summary="Robot Agent báo còn sống (mỗi 1–5 giây): chế độ, phiên bản controller/SDK/agent")
def heartbeat(robot_id: int, body: HeartbeatIn, svc: TechSvc) -> dict:
    robot = svc.heartbeat(robot_id, **body.model_dump())
    return {"ok": True, "robot_id": robot.id, "offline_after_seconds": OFFLINE_AFTER_S}


@technician_router.get("/robot-status", response_model=list[RobotStatusOut],
                       summary="Tình trạng robot của tôi bằng tiếng thường: trạng thái, mức 1–4, cảnh báo đang mở, hiệu chuẩn cũ bao lâu")
def tech_status(svc: TechSvc, bg: BackgroundTasks) -> list[RobotStatusOut]:
    rows = svc.my_robots_status()
    _flush_mail(svc, bg)
    return _status_out(svc, rows)


def _status_out(svc: RobotOpsService, rows: list[dict]) -> list[RobotStatusOut]:
    out = []
    for r in rows:
        alerts = _alert_out(svc, r["open_alerts"])
        out.append(RobotStatusOut(**{**r, "open_run": RunOut.model_validate(r["open_run"]) if r["open_run"] else None,
                                     "open_alerts": alerts}))
    return out


# ---------------------------------------------------------------------------------------------- Manager
@manager_router.get("/robot-status", response_model=list[RobotStatusOut], summary="Tình trạng mọi robot (bảng robot của Manager)")
def mgr_status(svc: MgrSvc, bg: BackgroundTasks) -> list[RobotStatusOut]:
    rows = svc.all_robots_status()
    _flush_mail(svc, bg)
    return _status_out(svc, rows)


@manager_router.get("/robots/{robot_id}/health", response_model=HealthOut, summary="Sức khoẻ robot trong N ngày: lần chạy, dừng an toàn, cảnh báo, % lực trong dải")
def health(robot_id: int, svc: MgrSvc, bg: BackgroundTasks, days: Annotated[int, Query(ge=1, le=365)] = 30) -> HealthOut:
    data = svc.health(robot_id, days)
    _flush_mail(svc, bg)
    st = _status_out(svc, [data["robot"]])[0]
    return HealthOut(**{**data, "robot": st})


@manager_router.get("/runs", response_model=Page[RunOut], summary="Các lần chạy của Robot Agent (lọc theo robot/job)")
def runs(svc: MgrSvc, robot_id: int | None = None, job_id: int | None = None, page: int = Query(1, ge=1),
         page_size: int = Query(50, ge=1, le=200)) -> Page[RunOut]:
    rows, total = svc.runs(robot_id=robot_id, job_id=job_id, offset=(page - 1) * page_size, limit=page_size)
    return Page(items=[RunOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


@manager_router.get("/jobs/{job_id}/compliance", response_model=ComplianceOut,
                    summary="Job có đi đúng quy trình không: từng bước đạt/không đạt và các ngoại lệ")
def compliance(job_id: int, svc: MgrSvc) -> ComplianceOut:
    return ComplianceOut(**svc.compliance(job_id))


@manager_router.get("/alerts", response_model=Page[AlertOut], summary="Cảnh báo robot (mặc định: chưa xử lý, nặng nhất trước)")
def mgr_alerts(svc: MgrSvc, bg: BackgroundTasks, open_only: Annotated[bool, Query(alias="open")] = True,
               robot_id: int | None = None, min_level: Annotated[int, Query(ge=1, le=4)] = 1, job_id: int | None = None,
               page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> Page[AlertOut]:
    svc.sweep_stale()
    _flush_mail(svc, bg)
    rows, total = svc.alerts(open_only=open_only, robot_id=robot_id, min_level=min_level, job_id=job_id,
                             offset=(page - 1) * page_size, limit=page_size)
    return Page(items=_alert_out(svc, rows), total=total, page=page, page_size=page_size)


@manager_router.post("/alerts/{alert_id}/ack", response_model=AlertOut, summary="Manager đã thấy cảnh báo")
def mgr_ack(alert_id: int, svc: MgrSvc) -> AlertOut:
    return _alert_out(svc, [svc.acknowledge(alert_id)])[0]


@manager_router.post("/alerts/{alert_id}/resolve", response_model=AlertOut,
                     summary="Manager đóng cảnh báo (kể cả mức đỏ) sau khi kiểm tra robot an toàn")
def mgr_resolve(alert_id: int, body: AlertResolveIn, svc: MgrSvc) -> AlertOut:
    return _alert_out(svc, [svc.resolve(alert_id, body.note)])[0]


@manager_router.get("/alert-catalog", response_model=list[CatalogOut], summary="Danh mục cảnh báo: mức, câu chữ, việc cần làm, người nhận")
def catalog(svc: MgrSvc) -> list[CatalogOut]:
    return [CatalogOut.model_validate(c) for c in svc.catalog()]


@manager_router.patch("/alert-catalog/{code}", response_model=CatalogOut,
                      summary="Sửa câu chữ, người nhận, email, ngưỡng, bật/tắt (mức không đổi; cảnh báo đỏ không được tắt)")
def patch_catalog(code: str, body: CatalogPatch, svc: MgrSvc) -> CatalogOut:
    return CatalogOut.model_validate(svc.patch_catalog(code, body.model_dump(exclude_unset=True)))
