"""Schemas for the end of an order: delivery choice, final payment, hand-over (Phase 4c-1)."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.api.ops_schemas import PaymentOut
from app.api.schemas import Address
from app.models.ops import PaymentGateway
from app.models.order import DeliveryMethod

_PHONE = r"^(0|\+84)\d{9}$"


class DeliveryOptionOut(BaseModel):
    fee: Decimal = Field(description="Phí vận chuyển (VND).")
    total_due: Decimal = Field(description="Số tiền phải trả một lần: (G − D) + phí ship.")


class ServiceOptionOut(BaseModel):
    carrier: Literal["GHN"]
    service_code: str
    service_name: str
    fee: Decimal
    total_due: Decimal = Field(description="(G − D) + phí dịch vụ này.")
    eta: datetime | None = Field(default=None, description="Ngày giao dự kiến do hãng báo (có thể trống).")
    is_fallback_fee: bool = Field(description="True: phí từ bảng phí dự phòng vì API hãng không dùng được.")
    mode: str = Field(description="MOCK | SANDBOX | LIVE | FALLBACK")


class DeliveryQuoteOut(BaseModel):
    paper_size: str
    package_type: Literal["FLAT_BOX_A5", "FLAT_BOX_A4", "TUBE"]
    balance: Decimal = Field(description="G − D: phần còn lại của đơn.")
    is_fallback_fee: bool = Field(description="True: phí lấy từ bảng phí dự phòng (chưa nối API hãng vận chuyển).")
    options: dict[Literal["DELIVERY", "PICKUP"], DeliveryOptionOut]
    chosen: DeliveryMethod | None = None
    services: list[ServiceOptionOut] = Field(default_factory=list, description="Các dịch vụ vận chuyển khách có thể chọn khi DELIVERY.")
    chosen_service: ServiceOptionOut | None = Field(default=None, description="Dịch vụ khách đã chọn (nếu đã chọn).")


class DeliveryIn(BaseModel):
    method: DeliveryMethod
    address: Address | None = Field(default=None, description="Bắt buộc khi DELIVERY (địa chỉ giao hàng: mã tỉnh và phường/xã lấy từ `GET /locations/...`).")
    pickup_slot_start: datetime | None = Field(default=None, description="Bắt buộc khi PICKUP; có múi giờ, trong giờ làm việc.")
    pickup_slot_end: datetime | None = None
    contact_phone: str | None = Field(default=None, pattern=_PHONE,
                                      description="Bắt buộc khi PICKUP: Staff đối chiếu số này khi bàn giao.")
    receiver: str | None = Field(default=None, max_length=150)
    carrier: Literal["GHN"] | None = Field(default=None, description="DELIVERY: hãng khách chọn (cùng với service_code). Bỏ trống = dịch vụ rẻ nhất.")
    service_code: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def _by_method(self) -> "DeliveryIn":
        if self.method == DeliveryMethod.DELIVERY and self.address is None:
            raise ValueError("DELIVERY cần address")
        if self.method == DeliveryMethod.PICKUP and not (self.pickup_slot_start and self.pickup_slot_end and self.contact_phone):
            raise ValueError("PICKUP cần pickup_slot_start, pickup_slot_end và contact_phone")
        if (self.carrier is None) != (self.service_code is None):
            raise ValueError("carrier và service_code phải đi cùng nhau")
        return self


class QuoteIn(BaseModel):
    address: Address


class FinalPaymentIn(BaseModel):
    gateway: PaymentGateway
    expected_total: Decimal | None = Field(default=None, ge=0, description="Số tiền khách đã thấy; phí đổi so với lúc đó thì trả 409 FEE_CHANGED.")


class FinalPaymentOut(BaseModel):
    payment_required: bool = Field(description="False khi cọc đã đủ và nhận tại xưởng: đơn sang READY_TO_DELIVER ngay.")
    total_due: Decimal
    order_status: str
    payments: list[PaymentOut] = Field(description="FINAL và/hoặc SHIPPING cùng một giao dịch cổng; checkout bằng một trong hai id.")


class PickupConfirmIn(BaseModel):
    phone: str = Field(min_length=9, max_length=20, description="Số điện thoại người nhận xuất trình tại xưởng.")
