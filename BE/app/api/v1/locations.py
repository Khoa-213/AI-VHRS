"""Provinces and wards for the address forms (FR-02, FR-21): GHN's two-level catalogue, served from this API's cache so the
browser never holds the carrier's token."""
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentAccount
from app.api.schemas import ErrorOut
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.integrations.locations import Unit, get_catalog

router = APIRouter(prefix="/locations", tags=["Locations"], dependencies=[Depends(rate_limit("locations", 120, 60))])
UNAVAILABLE = {503: {"model": ErrorOut, "description": "LOCATIONS_UNAVAILABLE"}}
_CACHE = "private, max-age=3600"


class LocationOut(BaseModel):
    code: str
    name: str


def _out(units: list[Unit]) -> list[LocationOut]:
    return [LocationOut(code=u.code, name=u.name) for u in units]


@router.get("/provinces", response_model=list[LocationOut], responses=UNAVAILABLE,
            summary="FR-02 Danh sách tỉnh/thành (mô hình hai cấp, mã của GHN)",
            description="Dùng `code` làm `province_code` của địa chỉ. Sắp theo tên; trình duyệt được phép giữ 1 giờ.")
def provinces(_: CurrentAccount, response: Response) -> list[LocationOut]:
    response.headers["Cache-Control"] = _CACHE
    return _out(get_catalog().provinces())


@router.get("/provinces/{province_code}/wards", response_model=list[LocationOut],
            responses={**UNAVAILABLE, 404: {"model": ErrorOut, "description": "PROVINCE_NOT_FOUND"}},
            summary="FR-02 Phường/xã của một tỉnh/thành",
            description="Dùng `code` làm `ward_code` của địa chỉ. Không còn cấp quận/huyện.")
def wards(province_code: str, _: CurrentAccount, response: Response) -> list[LocationOut]:
    found = get_catalog().wards(province_code)
    if found is None:
        raise AppError(404, "PROVINCE_NOT_FOUND", "Không tìm thấy tỉnh/thành.")
    response.headers["Cache-Control"] = _CACHE
    return _out(found)
