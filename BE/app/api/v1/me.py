from fastapi import APIRouter, Response, status

from app.api.deps import PrincipalDep, SessionDep
from app.api.schemas import AccountOut, ChangePasswordIn, ProfileUpdateIn, account_out
from app.repositories.sessions import SessionRepository
from app.services.accounts import ProfileService

router = APIRouter(prefix="/me", tags=["Profile"])


@router.get("", response_model=AccountOut, summary="UC-04 Xem hồ sơ")
def get_me(principal: PrincipalDep) -> AccountOut:
    return account_out(principal.account)


@router.patch("", response_model=AccountOut, summary="UC-04 Sửa hồ sơ và địa chỉ (FR-02)",
              description="Chỉ các trường gửi lên mới được cập nhật. Đổi số điện thoại sẽ bỏ trạng thái đã xác minh.")
def update_me(body: ProfileUpdateIn, principal: PrincipalDep, session: SessionDep) -> AccountOut:
    addresses = None if body.addresses is None else [a.model_dump() for a in body.addresses]
    acc = ProfileService(session).update(principal.account, full_name=body.full_name, phone=body.phone,
                                         addresses=addresses, phone_given="phone" in body.model_fields_set)
    session.flush()
    return account_out(acc)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT,
             summary="Đổi mật khẩu (đăng xuất các thiết bị khác)",
             responses={400: {"description": "WRONG_PASSWORD"}, 422: {"description": "WEAK_PASSWORD"}})
def change_password(body: ChangePasswordIn, principal: PrincipalDep, session: SessionDep) -> Response:
    ProfileService(session).change_password(principal.account, body.current_password, body.new_password)
    SessionRepository(session).revoke_all(principal.account.id, except_id=principal.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
