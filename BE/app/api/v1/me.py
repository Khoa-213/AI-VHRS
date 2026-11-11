from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import PrincipalDep, SessionDep, client_ip
from app.api.schemas import AccountOut, ChangePasswordIn, OtpSentOut, PhoneOtpVerifyIn, ProfileUpdateIn, account_out
from app.core.ratelimit import rate_limit
from app.integrations.sms import get_sms_sender
from app.repositories.sessions import SessionRepository
from app.services.accounts import ProfileService
from app.services.phone_otp import PhoneOtpService

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


# ---- FR-53 (Phase 5e): verify the profile's phone number by SMS OTP ------------------------------------------------------
_OTP_ERRORS = {400: {"description": "OTP_INVALID (details.attempts_left) / OTP_EXPIRED / OTP_TOO_MANY_ATTEMPTS"},
               409: {"description": "PHONE_ALREADY_VERIFIED / PHONE_TAKEN"}, 422: {"description": "PHONE_MISSING"},
               429: {"description": "OTP_RESEND_TOO_SOON (details.retry_after) / OTP_DAILY_LIMIT"}}


@router.post("/phone/otp", response_model=OtpSentOut, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(rate_limit("phone_otp", 10, 3600))],
             summary="FR-53 Gửi mã OTP xác minh số điện thoại của hồ sơ",
             description="Gửi 6 chữ số tới số trong hồ sơ, hiệu lực 5 phút. Mã mới làm mã cũ hết hiệu lực; chờ 60 giây giữa hai "
                         "lần, tối đa 5 mã mỗi số trong 24 giờ. `mode=MOCK`: chưa gửi SMS thật.",
             responses=_OTP_ERRORS)
def send_phone_otp(principal: PrincipalDep, session: SessionDep, request: Request) -> OtpSentOut:
    return OtpSentOut(**PhoneOtpService(session, get_sms_sender(), client_ip(request)).send_verification(principal.account))


@router.post("/phone/verify", response_model=AccountOut, summary="FR-53 Xác minh số điện thoại bằng mã OTP",
             dependencies=[Depends(rate_limit("phone_verify", 20, 900))],
             description="Đúng mã thì `phone_verified=true`; từ đó số này dùng được để khôi phục tài khoản. Sai 5 lần thì mã bị huỷ.",
             responses=_OTP_ERRORS)
def verify_phone(body: PhoneOtpVerifyIn, principal: PrincipalDep, session: SessionDep, request: Request) -> AccountOut:
    acc = PhoneOtpService(session, get_sms_sender(), client_ip(request)).confirm_verification(principal.account, body.code)
    return account_out(acc)
