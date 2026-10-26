"""GET /locations/...: the provinces and wards (GHN's two-level catalogue) behind the address forms. The default source is the
MOCK catalogue (real GHN staging ids), so nothing here touches the network; a failing source stands in for GHN being down."""
import pytest

from app.core.errors import AppError
from app.integrations import locations as loc
from tests.conftest import auth
from tests.test_api_orders import API

L = f"{API}/locations"


@pytest.fixture(autouse=True)
def _default_catalogue():
    loc.use_source(None)
    yield
    loc.use_source(None)


def test_provinces_and_wards_for_a_logged_in_user(client):
    h = auth(client, "CUSTOMER")
    r = client.get(f"{L}/provinces", headers=h)
    assert r.status_code == 200 and r.headers["cache-control"] == "private, max-age=3600"
    provinces = {p["name"]: p["code"] for p in r.json()}
    assert provinces["Hồ Chí Minh"] == "1000001" and set(r.json()[0]) == {"code", "name"}
    wards = client.get(f"{L}/provinces/{provinces['Hồ Chí Minh']}/wards", headers=h)
    assert wards.status_code == 200 and {"code": "1003506", "name": "Phường Sài Gòn"} in wards.json()
    assert client.get(f"{L}/provinces/9999/wards", headers=h).status_code == 404
    assert client.get(f"{L}/provinces/9999/wards", headers=h).json()["error"]["code"] == "PROVINCE_NOT_FOUND"
    for role in ("STAFF", "MANAGER"):                                            # every signed-in role may read the catalogue
        assert client.get(f"{L}/provinces", headers=auth(client, role)).status_code == 200, role


def test_the_catalogue_needs_a_session(client):
    assert client.get(f"{L}/provinces").status_code == 401
    assert client.get(f"{L}/provinces/1000001/wards").status_code == 401


def test_a_carrier_outage_is_a_503_not_a_crash(client):
    class Down:
        def provinces(self):
            raise AppError(503, "LOCATIONS_UNAVAILABLE", "down")

        def wards(self, province_code):
            raise AppError(503, "LOCATIONS_UNAVAILABLE", "down")

    loc.use_source(Down())
    h = auth(client, "CUSTOMER")
    for url in (f"{L}/provinces", f"{L}/provinces/1000001/wards"):
        r = client.get(url, headers=h)
        assert r.status_code == 503 and r.json()["error"]["code"] == "LOCATIONS_UNAVAILABLE", url


def test_the_listing_is_rate_limited(client):
    from app.core.ratelimit import limiter
    h = auth(client, "CUSTOMER")
    assert client.get(f"{L}/provinces", headers=h).status_code == 200
    for _ in range(119):                                   # the test client has no literal IP, so its key is "unknown"
        assert limiter.hit("locations", "unknown", 120, 60) == 0
    r = client.get(f"{L}/provinces", headers=h)             # a real caller spends calls at network speed; we spend them directly
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
