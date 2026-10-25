"""Robot Agent link routes: commands and live view for the app (Technical Staff, Manager) and `sync` for the agent."""
from typing import Annotated

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.api.deps import SessionDep, client_ip, require_roles
from app.api.link_schemas import (AgentCommand, AgentInfoOut, AgentKeyOut, AgentResultIn, AgentSyncIn, AgentSyncOut, CommandIn,
                                  CommandOut, LiveOut, SceneOut, SessionKeyIn, SessionKeyOut)
from app.api.schemas import ErrorOut
from app.api.v1.orders import optional_storage
from app.integrations.storage import ObjectStorage
from app.core.errors import AppError
from app.models.account import Account, RoleCode
from app.services import robot_view
from app.services.robot_link import RobotLinkService, _now, agent_for_key

technician_router = APIRouter(prefix="/technician", tags=["Robot link"])
manager_router = APIRouter(prefix="/manager", tags=["Robot link"])
agent_router = APIRouter(prefix="/agent", tags=["Robot link"])
viewer_router = APIRouter(tags=["Robot 3D view"])
TechDep = Annotated[Account, Depends(require_roles(RoleCode.TECHNICAL_STAFF.value))]
ManagerDep = Annotated[Account, Depends(require_roles(RoleCode.MANAGER.value))]
StorageDep = Annotated[ObjectStorage | None, Depends(optional_storage)]
ERR = {409: {"model": ErrorOut, "description": "AGENT_OFFLINE / JOB_NOT_ACTIVE / IDEMPOTENCY_KEY_REUSED"}}


def _tech(session: SessionDep, tech: TechDep, request: Request) -> RobotLinkService:
    return RobotLinkService(session, tech, client_ip(request))


def _mgr(session: SessionDep, manager: ManagerDep, request: Request) -> RobotLinkService:
    return RobotLinkService(session, manager, client_ip(request))


Tech = Annotated[RobotLinkService, Depends(_tech)]
Mgr = Annotated[RobotLinkService, Depends(_mgr)]


# ---------------------------------------------------------------------------------------------- Technical Staff
@technician_router.post("/robot-commands", response_model=CommandOut, status_code=status.HTTP_201_CREATED, responses=ERR,
                        summary="Gửi lệnh robot tới Robot Agent: LOAD, PREFLIGHT, DRY_RUN, RUN, PAUSE, RESUME, STOP, PAPER_CHANGED, IDENTIFY")
def create_command(body: CommandIn, svc: Tech) -> CommandOut:
    return CommandOut.model_validate(svc.create_command(robot_id=body.robot_id, job_id=body.job_id, kind=body.kind,
                                                        params=body.params, idempotency_key=body.idempotency_key))


@technician_router.get("/robot-commands/{command_id}", response_model=CommandOut,
                       summary="Trạng thái và kết quả của một lệnh (PENDING → DELIVERED → DONE/FAILED; quá hạn → EXPIRED)")
def get_command(command_id: str, svc: Tech) -> CommandOut:
    return CommandOut.model_validate(svc.command(command_id))


@technician_router.get("/jobs/{job_id}/robot-commands", response_model=list[CommandOut], summary="Các lệnh robot gần đây của job (mới → cũ)")
def job_commands(job_id: int, svc: Tech, limit: int = Query(50, ge=1, le=200)) -> list[CommandOut]:
    return [CommandOut.model_validate(c) for c in svc.job_commands(job_id, limit)]


@technician_router.get("/robots/{robot_id}/live", response_model=LiveOut,
                       summary="Trạng thái sống của robot: kết nối agent, khung hình mới sau `after` (khớp, TCP, lực, mức cảnh báo). Gọi 4–5 lần/giây")
def live(robot_id: int, svc: Tech, after: int = Query(0, ge=0)) -> LiveOut:
    return LiveOut(**svc.live(robot_id, after))


@technician_router.get("/robots/{robot_id}/scene", response_model=SceneOut, summary="Tờ giấy, khung toạ độ và nét của job agent vừa nạp (để vẽ 3D)")
def scene(robot_id: int, svc: Tech) -> SceneOut:
    return SceneOut(**svc.scene(robot_id))


@technician_router.post("/robots/{robot_id}/agent-session", response_model=SessionKeyOut, status_code=status.HTTP_201_CREATED,
                        summary="App kỹ thuật viên xin khoá agent theo phiên đăng nhập (vài giờ, gia hạn êm, mỗi robot một app điều khiển)",
                        responses={409: {"model": ErrorOut, "description": "ROBOT_IN_USE: robot đang do người/máy khác điều khiển"}})
def agent_session(robot_id: int, body: SessionKeyIn, svc: Tech) -> SessionKeyOut:
    key, row, renew = svc.issue_session_key(robot_id, body.instance_id)
    return SessionKeyOut(robot_id=robot_id, key=key, key_prefix=row.key_prefix, expires_at=row.expires_at, renew_after_s=renew)


@technician_router.delete("/robots/{robot_id}/agent-session", status_code=status.HTTP_204_NO_CONTENT,
                          summary="App đóng: trả khoá phiên (409 RUN_OPEN khi robot còn lần chạy chưa kết thúc)")
def release_session(robot_id: int, svc: Tech, instance_id: Annotated[str, Query(min_length=8, max_length=64)]) -> None:
    svc.release_session_key(robot_id, instance_id)


# ---------------------------------------------------------------------------------------------- Manager
@manager_router.post("/robots/{robot_id}/robot-commands", response_model=CommandOut, status_code=status.HTTP_201_CREATED, responses=ERR,
                     summary="Quản lý: chỉ PAUSE, RESUME, STOP (không bắt đầu chạy)")
def manager_command(robot_id: int, body: CommandIn, svc: Mgr) -> CommandOut:
    return CommandOut.model_validate(svc.create_command(robot_id=robot_id, job_id=body.job_id, kind=body.kind, params=body.params,
                                                        idempotency_key=body.idempotency_key))


@manager_router.get("/robots/{robot_id}/live", response_model=LiveOut, summary="Quản lý: trạng thái sống của robot")
def manager_live(robot_id: int, svc: Mgr, after: int = Query(0, ge=0)) -> LiveOut:
    return LiveOut(**svc.live(robot_id, after))


@manager_router.get("/robots/{robot_id}/scene", response_model=SceneOut, summary="Quản lý: cảnh 3D của job đã nạp")
def manager_scene(robot_id: int, svc: Mgr) -> SceneOut:
    return SceneOut(**svc.scene(robot_id))


@manager_router.get("/robots/{robot_id}/agent", response_model=AgentInfoOut, summary="Robot Agent của robot: đã có khoá chưa, đang online không")
def agent_info(robot_id: int, svc: Mgr) -> AgentInfoOut:
    return AgentInfoOut(**svc.agent_info(robot_id))


@manager_router.post("/robots/{robot_id}/agent-key", response_model=AgentKeyOut, status_code=status.HTTP_201_CREATED,
                     summary="Cấp (hoặc đổi) khoá cho Robot Agent của robot. Khoá cũ bị thu hồi; khoá mới chỉ hiện MỘT LẦN")
def issue_key(robot_id: int, svc: Mgr) -> AgentKeyOut:
    key, row = svc.issue_key(robot_id)
    return AgentKeyOut(robot_id=robot_id, key=key, key_prefix=row.key_prefix)


@manager_router.delete("/robots/{robot_id}/agent-key", status_code=status.HTTP_204_NO_CONTENT, summary="Thu hồi khoá Robot Agent")
def revoke_key(robot_id: int, svc: Mgr) -> None:
    svc.revoke_key(robot_id)


# ---------------------------------------------------------------------------------------------- Robot Agent
def _agent_ids(session: SessionDep, authorization: Annotated[str | None, Header()] = None) -> tuple[int, int]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(401, "INVALID_AGENT_KEY", "Thiếu khoá agent.")
    return agent_for_key(session, authorization[7:].strip())


AgentIds = Annotated[tuple[int, int], Depends(_agent_ids)]


@agent_router.post("/sync", response_model=AgentSyncOut,
                   summary="Agent gọi ra hệ thống ~1 lần/giây (4 lần/giây khi đang chạy): gửi trạng thái và khung hình sống, nhận lệnh mới")
def sync(body: AgentSyncIn, ids: AgentIds, session: SessionDep, request: Request) -> AgentSyncOut:
    robot_id, agent_id = ids
    svc = RobotLinkService(session, None, client_ip(request))
    cmds = svc.sync(robot_id, agent_id, status=body.status, frames=body.frames, versions=body.model_dump(include={
        "controller_version", "firmware_version", "sdk_version", "agent_version"}))
    return AgentSyncOut(robot_id=robot_id, server_time=_now(), commands=[
        AgentCommand(id=c.id, kind=c.kind, job_id=c.job_id, params=c.params, expires_at=c.expires_at) for c in cmds])


@agent_router.post("/commands/{command_id}/result", response_model=CommandOut, summary="Agent báo kết quả của một lệnh đã nhận (idempotent)")
def command_result(command_id: str, body: AgentResultIn, ids: AgentIds, session: SessionDep, request: Request) -> CommandOut:
    svc = RobotLinkService(session, None, client_ip(request))
    return CommandOut.model_validate(svc.finish_command(ids[0], command_id, ok=body.ok, result=body.result,
                                                        error_code=body.error_code, message=body.message))


# ---------------------------------------------------------------------------------------------- 3D view (ticket, read-only)
class ViewTicketOut(BaseModel):
    ticket: str
    expires_in: int
    viewer_path: str = Field(description="Đường dẫn trang xem 3D do BE phục vụ; ghép với base URL của BE: `<BE>` + viewer_path.")
    live_path: str
    scene_path: str


def _ticket(svc: RobotLinkService, robot_id: int) -> ViewTicketOut:
    svc.ops._robot(robot_id)                                   # 404 for a technician who holds no job on this robot
    ticket, ttl = robot_view.issue_ticket(svc.actor.id, robot_id)
    return ViewTicketOut(ticket=ticket, expires_in=ttl, viewer_path=f"/viewer/robot.html?ticket={ticket}",
                         live_path=f"/api/v1/viewer/{ticket}/live", scene_path=f"/api/v1/viewer/{ticket}/scene")


@technician_router.post("/robots/{robot_id}/view-ticket", response_model=ViewTicketOut, status_code=status.HTTP_201_CREATED,
                        summary="Vé xem 3D (chỉ đọc, 60 phút) cho trang `/viewer/robot.html` nhúng trong WebView/iframe")
def tech_ticket(robot_id: int, svc: Tech) -> ViewTicketOut:
    return _ticket(svc, robot_id)


@manager_router.post("/robots/{robot_id}/view-ticket", response_model=ViewTicketOut, status_code=status.HTTP_201_CREATED,
                     summary="Quản lý: vé xem 3D của một robot")
def manager_ticket(robot_id: int, svc: Mgr) -> ViewTicketOut:
    return _ticket(svc, robot_id)


def _viewer_svc(session: SessionDep) -> RobotLinkService:
    return RobotLinkService(session, None)


@viewer_router.get("/viewer/{ticket}/live", response_model=LiveOut, summary="Trang 3D: khung hình sống của robot (vé thay cho đăng nhập)")
def viewer_live(ticket: str, session: SessionDep, after: int = Query(0, ge=0)) -> LiveOut:
    return LiveOut(**_viewer_svc(session).live(robot_view.robot_of_ticket(ticket), after))


@viewer_router.get("/viewer/{ticket}/scene", response_model=SceneOut, summary="Trang 3D: tờ giấy, khung toạ độ và nét của job đã nạp")
def viewer_scene(ticket: str, session: SessionDep) -> SceneOut:
    return SceneOut(**_viewer_svc(session).scene(robot_view.robot_of_ticket(ticket)))


_MODEL_HEADERS = {"Cache-Control": "public, max-age=86400"}


@viewer_router.get("/robot-model/fairino3_v6.urdf", summary="Mô hình URDF của FAIRINO FR3 V6 (file SDK công khai của hãng)")
def model_urdf(storage: StorageDep) -> Response:
    return Response(robot_view.model_bytes(storage, "fairino3_v6.urdf", mesh=False), media_type="application/xml", headers=_MODEL_HEADERS)


@viewer_router.get("/robot-model/meshes/fairino3_v6/{name}", summary="Mesh STL của FR3 V6")
def model_mesh(name: str, storage: StorageDep) -> Response:
    return Response(robot_view.model_bytes(storage, name, mesh=True), media_type="model/stl", headers=_MODEL_HEADERS)
