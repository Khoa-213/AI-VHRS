"""Upgrade U8: public verification of a product by the code written on the sheet / printed on the certificate card."""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import SessionDep
from app.api.schemas import ErrorOut
from app.core.ratelimit import rate_limit
from app.services.certificates import CertificateService

router = APIRouter(prefix="/verify", tags=["Verify"])


class VerifyOut(BaseModel):
    code: str
    status: str = Field(description="VALID (đã sản xuất) | NOT_PRODUCED (chưa viết xong) | REVOKED (đơn đã huỷ)")
    status_text: str
    statement: str = Field(description="Câu khẳng định đây là bản tái tạo bằng AI, không phải bản gốc")
    watermark_text: str = Field(description="Dòng robot viết ở lề tờ giấy, để đối chiếu")
    order_type: str
    order_type_label: str
    paper_size: str | None
    pages: int | None
    quantity: int
    issued_at: datetime
    production_locked_at: datetime | None
    written_at: datetime | None


@router.get("/{code}", response_model=VerifyOut, dependencies=[Depends(rate_limit("verify", 30, 60))],
            responses={404: {"model": ErrorOut, "description": "CERTIFICATE_NOT_FOUND"}},
            summary="U8 Xác thực sản phẩm bằng mã trên tờ giấy / thẻ chứng nhận (không cần đăng nhập)",
            description="Nhận mã có hoặc không có gạch nối, chữ hoa hay thường. Không trả thông tin khách hàng hay nội dung "
                        "đã viết; chỉ loại sản phẩm, khổ giấy, số trang, số bản và các mốc ngày.")
def verify(code: str, session: SessionDep) -> VerifyOut:
    return VerifyOut(**CertificateService(session).public_view(code))
