"""Administrative units for addresses (FR-02, FR-21): provinces and the wards that belong to them.

Vietnam has had two levels since 01/07/2025 (province -> ward, no district), and GHN's catalogue for that model is what the
shipping fee and the waybill are asked with, so the same catalogue feeds the address pickers of the web app. The browser never
holds GHN's token: it asks this API (`/locations/...`), which asks GHN once a day and keeps the answer in memory.

* `CARRIER_MODE=mock` (default): a small fixed catalogue taken from GHN's staging data, so demos and tests need no network.
* `sandbox` / `live`: GHN's `v3/master-data` endpoints with the shop's token.

A unit's `code` is GHN's own id written as text; its `name` is the canonical name GHN wants back when an order is created.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import AppError

CACHE_TTL_SECONDS = 24 * 3600
_STALE_OK_SECONDS = 7 * 24 * 3600          # when GHN is down an older answer is still better than no address form at all


@dataclass(frozen=True)
class Unit:
    code: str
    name: str


class LocationSource(Protocol):
    def provinces(self) -> list[Unit]: ...
    def wards(self, province_code: str) -> list[Unit] | None: ...      # None = no such province


# ---------------------------------------------------------------------------------------------------- MOCK
_MOCK: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("1000000", "Hà Nội"): [("1003479", "Xã Đoài Phương"), ("1003478", "Phường Tùng Thiện"), ("1003477", "Phường Sơn Tây"),
                            ("1003476", "Phường Đống Đa")],
    ("1000001", "Hồ Chí Minh"): [("1003506", "Phường Sài Gòn"), ("1003647", "Xã Long Sơn"), ("1003646", "Phường Vũng Tàu"),
                                 ("1003645", "Phường Tam Thắng"), ("1003644", "Phường Rạch Dừa")],
    ("1000003", "Đà Nẵng"): [("1003895", "Xã Điện Bàn Tây"), ("1003894", "Xã Gò Nổi"), ("1003893", "Phường Điện Bàn Đông"),
                             ("1003892", "Phường Điện Bàn Bắc")],
    ("1000022", "Cà Mau"): [("1006674", "Xã Phong Thạnh"), ("1006673", "Phường Láng Tròn"), ("1006672", "Phường Giá Rai"),
                            ("1006671", "Phường Vĩnh Trạch")],
}


class MockLocations:
    def provinces(self) -> list[Unit]:
        return [Unit(code, name) for code, name in _MOCK]

    def wards(self, province_code: str) -> list[Unit] | None:
        for (code, _), wards in _MOCK.items():
            if code == province_code:
                return [Unit(c, n) for c, n in wards]
        return None


# ---------------------------------------------------------------------------------------------------- GHN
class GhnLocations:
    def __init__(self, *, token: str, shop_id: str | int, base_url: str, transport: httpx.BaseTransport | None = None):
        self._headers = {"Token": token, "ShopId": str(shop_id)}
        self._base, self._transport = base_url.rstrip("/") + "/v3/master-data", transport

    def _get(self, path: str, params: Mapping[str, Any]) -> list[dict[str, Any]] | None:
        try:
            with httpx.Client(transport=self._transport, timeout=15.0) as http:
                r = http.get(self._base + path, headers=self._headers, params=dict(params))
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(503, "LOCATIONS_UNAVAILABLE", "Chưa tải được danh sách địa chỉ, vui lòng thử lại.") from exc
        if r.status_code >= 400 or not isinstance(data, dict) or data.get("code") != 200:
            raise AppError(503, "LOCATIONS_UNAVAILABLE", "Chưa tải được danh sách địa chỉ, vui lòng thử lại.")
        rows = data.get("data")
        return rows if isinstance(rows, list) else None                  # GHN answers 200 + null for an unknown province

    @staticmethod
    def _units(rows: list[dict[str, Any]]) -> list[Unit]:
        return sorted((Unit(str(r["_id"]), str(r["name"])) for r in rows if r.get("status") == 1 and r.get("_id") and r.get("name")),
                      key=lambda u: u.name)

    def provinces(self) -> list[Unit]:
        return self._units(self._get("/province/all", {"offset": 0, "limit": 200}) or [])

    def wards(self, province_code: str) -> list[Unit] | None:
        try:
            province_id = int(province_code)
        except ValueError:
            return None
        rows = self._get("/ward/all-by-province-id", {"province_id": province_id, "offset": 0, "limit": 200})
        return None if rows is None else self._units(rows)


# ---------------------------------------------------------------------------------------------------- the cached catalogue
class LocationCatalog:
    def __init__(self, source: LocationSource, *, clock=time.monotonic):
        self._source, self._clock = source, clock
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, Any]] = {}

    def _cached(self, key: str, load) -> Any:
        with self._lock:
            hit = self._cache.get(key)
            now = self._clock()
            if hit and now - hit[0] < CACHE_TTL_SECONDS:
                return hit[1]
            try:
                value = load()
            except AppError:
                if hit and now - hit[0] < _STALE_OK_SECONDS:
                    return hit[1]
                raise
            if value is not None:                                         # an unknown province is not worth remembering
                self._cache[key] = (now, value)
            return value

    def provinces(self) -> list[Unit]:
        return self._cached("provinces", self._source.provinces)

    def wards(self, province_code: str) -> list[Unit] | None:
        return self._cached(f"wards:{province_code}", lambda: self._source.wards(province_code))

    def resolve(self, province_code: str, ward_code: str) -> tuple[Unit, Unit]:
        """The province and the ward behind a pair of codes; the ward must belong to the province."""
        province = next((p for p in self.provinces() if p.code == str(province_code)), None)
        wards = self.wards(province.code) if province else None
        ward = next((w for w in wards or [] if w.code == str(ward_code)), None)
        if province is None or ward is None:
            raise AppError(422, "INVALID_ADDRESS", "Tỉnh/thành hoặc phường/xã không hợp lệ.",
                           {"province_code": str(province_code), "ward_code": str(ward_code)})
        return province, ward


# ---------------------------------------------------------------------------------------------------- registry
_override: LocationCatalog | None = None
_catalogs: dict[str, LocationCatalog] = {}


def use_source(source: LocationSource | None) -> None:
    """Tests only: a stand-in source (None clears)."""
    global _override
    _override = LocationCatalog(source) if source is not None else None


def get_catalog() -> LocationCatalog:
    if _override is not None:
        return _override
    s = get_settings()
    if s.carrier_mode == "mock":
        return _catalogs.setdefault("mock", LocationCatalog(MockLocations()))
    if not (s.ghn_token and s.ghn_shop_id):
        raise AppError(503, "LOCATIONS_UNAVAILABLE", "Chưa cấu hình GHN trên máy chủ nên chưa có danh sách địa chỉ.")
    key = f"ghn:{s.ghn_base_url}:{s.ghn_shop_id}"
    if key not in _catalogs:
        _catalogs[key] = LocationCatalog(GhnLocations(token=s.ghn_token, shop_id=s.ghn_shop_id, base_url=s.ghn_base_url))
    return _catalogs[key]


def normalize_address(address: Mapping[str, Any]) -> dict[str, Any]:
    """An address as stored: the names come from the catalogue (never from the client) and the old district fields are dropped."""
    out = {k: v for k, v in address.items() if k not in ("district_code", "district_name")}
    province, ward = get_catalog().resolve(str(address.get("province_code") or ""), str(address.get("ward_code") or ""))
    out.update(province_code=province.code, province_name=province.name, ward_code=ward.code, ward_name=ward.name)
    return out
