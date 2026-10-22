"""Schemas for waybills (Phase 4c-2c)."""
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.api.ops_schemas import Reason
from app.models.ops import ShipmentStatus


class CreateShipmentIn(BaseModel):
    note: str | None = Field(default=None, max_length=300, description="Ghi chú cho shipper (không bắt buộc).")


class CancelShipmentIn(BaseModel):
    reason: Reason


class MockEventIn(BaseModel):
    status: ShipmentStatus
    reason: str | None = Field(default=None, max_length=300)


class ShipmentOut(BaseModel):
    """What the customer may see about their parcel."""
    id: int
    order_id: int
    carrier: str
    service_code: str | None
    waybill_code: str | None
    status: ShipmentStatus
    fee: Decimal = Field(description="Phí vận chuyển khách đã thanh toán.")
    eta: datetime | None = Field(default=None, description="Ngày giao dự kiến khi khách chọn dịch vụ.")
    picked_up_at: datetime | None
    delivered_at: datetime | None
    mode: str = Field(description="MOCK = vận đơn mô phỏng; SANDBOX/LIVE = vận đơn của hãng.")
    tracking_url: str | None = Field(default=None, description="Trang tra cứu của hãng (không có với vận đơn mô phỏng).")
    created_at: datetime


class StaffShipmentOut(ShipmentOut):
    package_type: str | None
    weight_g: int | None
    is_fallback_fee: bool
    carrier_status_raw: str | None
    to_address: dict[str, Any]
    label_link: str | None = Field(default=None, description="Link PDF nhãn (hết hạn sau 10 phút), nếu có.")
    created_by: int | None
