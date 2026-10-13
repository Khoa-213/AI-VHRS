"""API request/response schemas (kept separate from ORM models)."""
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.account import AccountStatus

T = TypeVar("T")
_PHONE = r"^(0|\+84)\d{9}$"


class ErrorBody(BaseModel):
    code: str = Field(examples=["INVALID_CREDENTIALS"])
    message: str
    details: Any | None = None


class ErrorOut(BaseModel):
    """Every non-2xx response uses this envelope."""
    error: ErrorBody


class MessageOut(BaseModel):
    message: str


class OAuthTokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Address(BaseModel):
    label: str | None = Field(default=None, max_length=50)
    receiver: str = Field(min_length=1, max_length=150)
    phone: str = Field(pattern=_PHONE)
    street: str = Field(min_length=1, max_length=255)
    province_code: str  # codes follow the carrier's (GHN/GHTK) location tables (FR-02)
    district_code: str
    ward_code: str
    is_default: bool = False


class RegisterIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "email": "khach@example.com", "password": "Matkhau123", "full_name": "Nguyễn Văn A", "phone": "0901234567"}]})
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(default=None, pattern=_PHONE)


class LoginIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "email": "customer@example.com", "password": "ChangeMe@123"}]})
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RefreshIn(BaseModel):
    refresh_token: str


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetConfirmIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    phone: str | None
    phone_verified: bool
    role: str
    status: AccountStatus
    addresses: list[dict[str, Any]]
    created_at: datetime
    last_login_at: datetime | None


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    account: AccountOut


class ProfileUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    phone: str | None = Field(default=None, pattern=_PHONE)
    addresses: list[Address] | None = Field(default=None, max_length=10)

    @field_validator("addresses")
    @classmethod
    def _one_default(cls, v: list[Address] | None) -> list[Address] | None:
        if v and sum(a.is_default for a in v) > 1:
            raise ValueError("Chỉ được có một địa chỉ mặc định")
        return v


class AdminAccountCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(default=None, pattern=_PHONE)
    role: str


class AdminAccountUpdateIn(BaseModel):
    status: AccountStatus | None = None
    role: str | None = None
    reason: str | None = Field(default=None, max_length=500)


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_id: int | None
    action: str
    entity_type: str | None
    entity_id: int | None
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    reason: str | None
    created_at: datetime


def account_out(acc: Any) -> AccountOut:
    return AccountOut(
        id=acc.id, email=acc.email, full_name=acc.full_name, phone=acc.phone,
        phone_verified=acc.phone_verified_at is not None, role=acc.role.code, status=acc.status,
        addresses=acc.addresses or [], created_at=acc.created_at, last_login_at=acc.last_login_at)
