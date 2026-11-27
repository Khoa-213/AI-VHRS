from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import PrincipalDep, SessionDep, client_ip
from app.api.schemas import (AccountOut, GoogleLoginIn, LoginIn, MessageOut, OAuthTokenOut, PasswordResetConfirmIn,
                             PasswordResetRequestIn, PhoneResetRequestIn, RefreshIn,
                             RegisterIn, TokenOut, account_out)
from app.core.ratelimit import rate_limit
from app.integrations.firebase_auth import FirebaseVerifier, get_firebase_verifier
from app.integrations.google_auth import GoogleVerifier, get_google_verifier
from app.integrations.mailer import Mailer, get_mailer
from app.integrations.sms import get_sms_sender
from app.services.auth import AuthService
from app.services.phone_otp import PhoneOtpService

router = APIRouter(prefix="/auth", tags=["Auth"])


def _service(session: SessionDep, mailer: Mailer = Depends(get_mailer)) -> AuthService:
    return AuthService(session, mailer)


Svc = Annotated[AuthService, Depends(_service)]


@router.post("/register", response_model=AccountOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("register", 10, 3600))],
             summary="UC-05 Đăng ký khách hàng",
             responses={409: {"description": "EMAIL_TAKEN"}, 422: {"description": "WEAK_PASSWORD / validation"}})
def register(body: RegisterIn, svc: Svc) -> AccountOut:
    return account_out(svc.register_customer(
        email=body.email, password=body.password, full_name=body.full_name, phone=body.phone))


@router.post("/login", response_model=TokenOut, summary="UC-01 Đăng nhập (web và Flutter App)",
             dependencies=[Depends(rate_limit("login", 20, 60))],
             responses={401: {"description": "INVALID_CREDENTIALS"}, 403: {"description": "ACCOUNT_DISABLED"},
                        423: {"description": "ACCOUNT_TEMP_LOCKED (sai mật khẩu 5 lần)"}})
def login(body: LoginIn, svc: Svc, request: Request) -> TokenOut:
    acc, access, refresh = svc.login(body.email, body.password, ip=client_ip(request),
                                     user_agent=request.headers.get("user-agent"))
    return TokenOut(access_token=access, refresh_token=refresh, account=account_out(acc), reminders=svc.reminders)


@router.post("/google", response_model=TokenOut, summary="UC-01 Đăng nhập bằng Google (khách hàng; gửi Google ID token)",
             dependencies=[Depends(rate_limit("login", 20, 60))],
             responses={401: {"description": "GOOGLE_TOKEN_INVALID / GOOGLE_EMAIL_NOT_VERIFIED"},
                        403: {"description": "GOOGLE_NOT_ALLOWED (tài khoản nội bộ) / ACCOUNT_DISABLED"},
                        503: {"description": "GOOGLE_NOT_CONFIGURED / GOOGLE_UNAVAILABLE"}})
def login_google(body: GoogleLoginIn, svc: Svc, request: Request,
                 verifier: Annotated[GoogleVerifier, Depends(get_google_verifier)]) -> TokenOut:
    identity = verifier.verify(body.id_token)
    acc, access, refresh = svc.login_google(identity, ip=client_ip(request), user_agent=request.headers.get("user-agent"))
    return TokenOut(access_token=access, refresh_token=refresh, account=account_out(acc), reminders=svc.reminders)


@router.post("/token", response_model=OAuthTokenOut, include_in_schema=True,
             dependencies=[Depends(rate_limit("login", 20, 60))],
             summary="Đăng nhập dạng OAuth2 form (dùng cho nút Authorize của Swagger)",
             description="`username` là email. Trả về cùng access token như `/auth/login`.")
def token(form: Annotated[OAuth2PasswordRequestForm, Depends()], svc: Svc, request: Request) -> OAuthTokenOut:
    _, access, refresh = svc.login(form.username, form.password, ip=client_ip(request),
                                   user_agent=request.headers.get("user-agent"))
    return OAuthTokenOut(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenOut, summary="Làm mới token",
             dependencies=[Depends(rate_limit("refresh", 60, 60))],
             responses={401: {"description": "Refresh token hết hạn, không hợp lệ hoặc phiên đã bị thu hồi"}})
def refresh(body: RefreshIn, svc: Svc) -> TokenOut:
    acc, access, refresh_token = svc.refresh(body.refresh_token)
    return TokenOut(access_token=access, refresh_token=refresh_token, account=account_out(acc))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="UC-02 Đăng xuất (thu hồi phiên)",
             description="Thu hồi phiên hiện tại: access token và refresh token của phiên này không dùng được nữa.")
def logout(principal: PrincipalDep, svc: Svc) -> Response:
    svc.logout(principal.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password-reset/request", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(rate_limit("reset_request", 5, 900))],
             summary="UC-03 Yêu cầu đặt lại mật khẩu qua email",
             description="Luôn trả 202 dù email có tồn tại hay không (chống dò email).")
def password_reset_request(body: PasswordResetRequestIn, svc: Svc) -> MessageOut:
    svc.request_password_reset(body.email)
    return MessageOut(message="Nếu email tồn tại, hướng dẫn đặt lại mật khẩu đã được gửi.")


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(rate_limit("reset_confirm", 10, 900))],
             summary="UC-03 / UC-54 Đặt mật khẩu mới: {email, code} / {phone, code} / {firebase_id_token} + new_password",
             description="Đúng một cách: mã của mail đặt lại mật khẩu (`email` + `code`), mã SMS do BE gửi tới số đã xác minh "
                         "(`phone` + `code`), hoặc `firebase_id_token` của lần đăng nhập Firebase bằng số điện thoại khách vừa "
                         "làm (Google gửi SMS; số phải đã xác minh cho một tài khoản; token dùng một lần, tối đa 10 phút). "
                         "Kiểm và đặt mật khẩu trong một lần gọi; mọi thiết bị bị đăng xuất. Mật khẩu yếu: 422, bằng chứng chưa bị dùng.",
             responses={400: {"description": "OTP_INVALID (details.attempts_left) / OTP_EXPIRED / OTP_TOO_MANY_ATTEMPTS / "
                                             "PHONE_NOT_VERIFIED (Firebase: số chưa xác minh cho tài khoản nào)"},
                        401: {"description": "FIREBASE_TOKEN_INVALID / FIREBASE_TOKEN_EXPIRED"},
                        503: {"description": "FIREBASE_NOT_CONFIGURED / FIREBASE_UNAVAILABLE"}})
def password_reset_confirm(body: PasswordResetConfirmIn, svc: Svc, request: Request,
                           firebase: Annotated[FirebaseVerifier, Depends(get_firebase_verifier)]) -> Response:
    if body.firebase_id_token is not None:
        svc.confirm_password_reset_firebase(body.firebase_id_token, body.new_password, firebase, ip=client_ip(request))
    elif body.phone is not None:
        svc.confirm_password_reset_phone(body.phone, body.code, body.new_password, ip=client_ip(request))
    else:
        svc.confirm_password_reset_code(str(body.email), body.code, body.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- FR-53 / UC-54 (Phase 5e): recover the account with the verified phone number ----------------------------------------
@router.post("/phone-reset/request", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(rate_limit("phone_reset_request", 5, 900))],
             summary="UC-54 Quên mật khẩu: gửi OTP tới số điện thoại đã xác minh",
             description="Luôn trả 202 (chống dò số). Chỉ gửi khi số đã được xác minh cho một tài khoản đang hoạt động; "
                         "chờ 60 giây giữa hai mã, tối đa 5 mã mỗi số trong 24 giờ. Đặt mật khẩu mới bằng "
                         "`POST /auth/password-reset/confirm {phone, code, new_password}`.")
def phone_reset_request(body: PhoneResetRequestIn, session: SessionDep, request: Request) -> MessageOut:
    PhoneOtpService(session, get_sms_sender(), client_ip(request)).request_reset(body.phone)
    return MessageOut(message="Nếu số điện thoại đã được xác minh, mã OTP đã được gửi qua SMS.")

