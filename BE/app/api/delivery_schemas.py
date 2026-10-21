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


class DeliveryQuoteOut(BaseModel):
    paper_size: str
    package_type: Literal["FLAT_BOX_A5", "FLAT_BOX_A4", "TUBE"]
    balance: Decimal = Field(description="G − D: phần còn lại của đơn.")
    is_fallback_fee: bool = Field(description="True: phí lấy từ bảng phí dự phòng (chưa nối API hãng vận chuyển).")
    options: dict[Literal["DELIVERY", "PICKUP"], DeliveryOptionOut]
    chosen: DeliveryMethod | None = None


class DeliveryIn(BaseModel):
    method: DeliveryMethod
    address: Address | None = Field(default=None, description="Bắt buộc khi DELIVERY (địa chỉ giao hàng, mã tỉnh/huyện/xã theo hãng).")
    pickup_slot_start: datetime | None = Field(default=None, description="Bắt buộc khi PICKUP; có múi giờ, trong giờ làm việc.")
    pickup_slot_end: datetime | None = None
    contact_phone: str | None = Field(default=None, pattern=_PHONE,
                                      description="Bắt buộc khi PICKUP: Staff đối chiếu số này khi bàn giao.")
    receiver: str | None = Field(default=None, max_length=150)

    @model_validator(mode="after")
    def _by_method(self) -> "DeliveryIn":
        if self.method == DeliveryMethod.DELIVERY and self.address is None:
            raise ValueError("DELIVERY cần address")
        if self.method == DeliveryMethod.PICKUP and not (self.pickup_slot_start and self.pickup_slot_end and self.contact_phone):
            raise ValueError("PICKUP cần pickup_slot_start, pickup_slot_end và contact_phone")
        return self


class FinalPaymentIn(BaseModel):
    gateway: PaymentGateway


class FinalPaymentOut(BaseModel):
    payment_required: bool = Field(description="False khi cọc đã đủ và nhận tại xưởng: đơn sang READY_TO_DELIVER ngay.")
    total_due: Decimal
    order_status: str
    payments: list[PaymentOut] = Field(description="FINAL và/hoặc SHIPPING cùng một giao dịch cổng; checkout bằng một trong hai id.")


class PickupConfirmIn(BaseModel):
    phone: str = Field(min_length=9, max_length=20, description="Số điện thoại người nhận xuất trình tại xưởng.")
