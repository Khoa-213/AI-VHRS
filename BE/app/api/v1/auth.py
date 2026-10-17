from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import PrincipalDep, SessionDep, client_ip
from app.api.schemas import (AccountOut, GoogleLoginIn, LoginIn, MessageOut, OAuthTokenOut, PasswordResetConfirmIn,
                             PasswordResetRequestIn, RefreshIn, RegisterIn, TokenOut, account_out)
from app.core.ratelimit import rate_limit
from app.integrations.google_auth import GoogleVerifier, get_google_verifier
from app.integrations.mailer import Mailer, get_mailer
from app.services.auth import AuthService

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
    return TokenOut(access_token=access, refresh_token=refresh, account=account_out(acc))


@router.post("/google", response_model=TokenOut, summary="UC-01 Đăng nhập bằng Google (khách hàng; gửi Google ID token)",
             dependencies=[Depends(rate_limit("login", 20, 60))],
             responses={401: {"description": "GOOGLE_TOKEN_INVALID / GOOGLE_EMAIL_NOT_VERIFIED"},
                        403: {"description": "GOOGLE_NOT_ALLOWED (tài khoản nội bộ) / ACCOUNT_DISABLED"},
                        503: {"description": "GOOGLE_NOT_CONFIGURED / GOOGLE_UNAVAILABLE"}})
def login_google(body: GoogleLoginIn, svc: Svc, request: Request,
                 verifier: Annotated[GoogleVerifier, Depends(get_google_verifier)]) -> TokenOut:
    identity = verifier.verify(body.id_token)
    acc, access, refresh = svc.login_google(identity, ip=client_ip(request), user_agent=request.headers.get("user-agent"))
    return TokenOut(access_token=access, refresh_token=refresh, account=account_out(acc))


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
             summary="UC-03 Đặt mật khẩu mới bằng token (đăng xuất mọi thiết bị)",
             responses={401: {"description": "Token hết hạn hoặc đã dùng"}})
def password_reset_confirm(body: PasswordResetConfirmIn, svc: Svc) -> Response:
    svc.confirm_password_reset(body.token, body.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
