import uuid

from tests.conftest import PASSWORD, auth, login, make_account

API = "/api/v1"


def _email() -> str:
    return f"pytest_{uuid.uuid4().hex[:10]}@example.com"


def _bearer(tok: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok['access_token']}"}


def test_health(client):
    assert client.get(f"{API}/health").json() == {"status": "ok"}


def test_register_login_me_roundtrip(client):
    email = _email()
    r = client.post(f"{API}/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Khách A"})
    assert r.status_code == 201 and r.json()["role"] == "CUSTOMER"
    me = client.get(f"{API}/me", headers=_bearer(login(client, email)))
    assert me.status_code == 200 and me.json()["email"] == email


def test_register_duplicate_email_case_insensitive_409(client):
    email = _email()
    body = {"email": email, "password": PASSWORD, "full_name": "A"}
    assert client.post(f"{API}/auth/register", json=body).status_code == 201
    r = client.post(f"{API}/auth/register", json={**body, "email": email.upper()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_TAKEN"


def test_register_validation_and_weak_password(client):
    r = client.post(f"{API}/auth/register", json={"email": "not-an-email", "password": PASSWORD, "full_name": "A"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    r = client.post(f"{API}/auth/register", json={"email": _email(), "password": "abcdefghij", "full_name": "A"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "WEAK_PASSWORD"


def test_lock_after_five_wrong_passwords(client):
    email = make_account("CUSTOMER")
    for _ in range(5):
        r = client.post(f"{API}/auth/login", json={"email": email, "password": "Wrong1234"})
        assert r.status_code == 401
    r = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 423 and r.json()["error"]["code"] == "ACCOUNT_TEMP_LOCKED"


def test_unauthenticated_and_bad_token(client):
    assert client.get(f"{API}/me").status_code == 401
    assert client.get(f"{API}/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_rbac_matrix_for_admin_endpoints(client):
    for role in ("CUSTOMER", "STAFF", "TECHNICAL_STAFF", "MANAGER"):
        h = auth(client, role)
        assert client.get(f"{API}/admin/accounts", headers=h).status_code == 403, role
        assert client.get(f"{API}/admin/audit-logs", headers=h).status_code == 403, role
    assert client.get(f"{API}/admin/accounts?page_size=5", headers=auth(client, "ADMIN")).status_code == 200


def test_profile_addresses_and_phone_reset(client):
    h = auth(client, "CUSTOMER")
    addr = {"receiver": "A", "phone": "0900000001", "street": "1 Lê Lợi", "province_code": "79",
            "district_code": "760", "ward_code": "26734", "is_default": True}
    r = client.patch(f"{API}/me", headers=h, json={"phone": "0900000002", "addresses": [addr]})
    assert r.status_code == 200 and r.json()["phone"] == "0900000002" and r.json()["phone_verified"] is False
    assert len(r.json()["addresses"]) == 1
    r = client.patch(f"{API}/me", headers=h, json={"addresses": [addr, addr]})
    assert r.status_code == 422  # two defaults


def test_change_password(client):
    email = make_account("CUSTOMER")
    h = _bearer(login(client, email))
    assert client.post(f"{API}/me/change-password", headers=h,
                       json={"current_password": "bad", "new_password": "NewPassw0rd"}).status_code == 400
    assert client.post(f"{API}/me/change-password", headers=h,
                       json={"current_password": PASSWORD, "new_password": "NewPassw0rd"}).status_code == 204
    login(client, email, "NewPassw0rd")


def test_password_reset_flow_token_is_single_use(client, mailbox):
    email = make_account("CUSTOMER")
    assert client.post(f"{API}/auth/password-reset/request", json={"email": email}).status_code == 202
    assert client.post(f"{API}/auth/password-reset/request", json={"email": _email()}).status_code == 202
    assert len(mailbox) == 1  # unknown email sends nothing, yet answers identically
    token = mailbox[0][2].rsplit(": ", 1)[1]
    ok = client.post(f"{API}/auth/password-reset/confirm", json={"token": token, "new_password": "Brandn3wPass"})
    assert ok.status_code == 204
    login(client, email, "Brandn3wPass")
    again = client.post(f"{API}/auth/password-reset/confirm", json={"token": token, "new_password": "Another1234"})
    assert again.status_code == 401


def test_admin_creates_internal_account_and_audits(client):
    h = auth(client, "ADMIN")
    email = _email()
    r = client.post(f"{API}/admin/accounts", headers=h,
                    json={"email": email, "password": PASSWORD, "full_name": "NV", "role": "STAFF"})
    assert r.status_code == 201 and r.json()["role"] == "STAFF"
    acc_id = r.json()["id"]
    bad = client.post(f"{API}/admin/accounts", headers=h,
                      json={"email": _email(), "password": PASSWORD, "full_name": "X", "role": "ADMIN"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "ROLE_NOT_ALLOWED"  # BR-01
    locked = client.patch(f"{API}/admin/accounts/{acc_id}", headers=h, json={"status": "LOCKED", "reason": "test"})
    assert locked.json()["status"] == "LOCKED"
    assert client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).status_code == 403
    assert client.patch(f"{API}/admin/accounts/{acc_id}", headers=h, json={"status": "ACTIVE"}).status_code == 200
    login(client, email)
    logs = client.get(f"{API}/admin/audit-logs?entity_type=account&entity_id={acc_id}", headers=h).json()
    assert {x["action"] for x in logs["items"]} >= {"ACCOUNT_CREATE", "ACCOUNT_LOCK", "ACCOUNT_UNLOCK"}


def test_admin_update_unknown_account_404_and_self_change_403(client):
    tok = login(client, make_account("ADMIN"))
    h = _bearer(tok)
    assert client.patch(f"{API}/admin/accounts/999999999", headers=h, json={"status": "LOCKED"}).status_code == 404
    assert client.patch(f"{API}/admin/accounts/{tok['account']['id']}", headers=h,
                        json={"status": "LOCKED"}).status_code == 403


# ---- session revocation (logout / password change / reset) --------------------------------------
def test_logout_revokes_access_and_refresh_token(client):
    email = make_account("CUSTOMER")
    tok = login(client, email)
    h = _bearer(tok)
    assert client.get(f"{API}/me", headers=h).status_code == 200
    assert client.post(f"{API}/auth/logout", headers=h).status_code == 204
    assert client.get(f"{API}/me", headers=h).status_code == 401
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_INVALID"


def test_logout_only_affects_that_session(client):
    email = make_account("CUSTOMER")
    a, b = login(client, email), login(client, email)
    assert client.post(f"{API}/auth/logout", headers=_bearer(a)).status_code == 204
    assert client.get(f"{API}/me", headers=_bearer(a)).status_code == 401
    assert client.get(f"{API}/me", headers=_bearer(b)).status_code == 200


def test_refresh_keeps_session_and_new_access_works(client):
    tok = login(client, make_account("CUSTOMER"))
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 200
    assert client.get(f"{API}/me", headers=_bearer(r.json())).status_code == 200


def test_access_token_cannot_be_used_as_refresh_token(client):
    tok = login(client, make_account("CUSTOMER"))
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": tok["access_token"]})
    assert r.status_code == 401


def test_change_password_signs_out_other_devices_but_not_current(client):
    email = make_account("CUSTOMER")
    here, other = login(client, email), login(client, email)
    r = client.post(f"{API}/me/change-password", headers=_bearer(here),
                    json={"current_password": PASSWORD, "new_password": "NewPassw0rd"})
    assert r.status_code == 204
    assert client.get(f"{API}/me", headers=_bearer(here)).status_code == 200
    assert client.get(f"{API}/me", headers=_bearer(other)).status_code == 401


def test_password_reset_signs_out_every_device(client, mailbox):
    email = make_account("CUSTOMER")
    tok = login(client, email)
    client.post(f"{API}/auth/password-reset/request", json={"email": email})
    token = mailbox[0][2].rsplit(": ", 1)[1]
    assert client.post(f"{API}/auth/password-reset/confirm",
                       json={"token": token, "new_password": "Brandn3wPass"}).status_code == 204
    assert client.get(f"{API}/me", headers=_bearer(tok)).status_code == 401
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401


def test_locked_account_session_stops_working(client):
    admin = auth(client, "ADMIN")
    email = _email()
    created = client.post(f"{API}/admin/accounts", headers=admin,
                          json={"email": email, "password": PASSWORD, "full_name": "NV", "role": "STAFF"})
    tok = login(client, email)
    client.patch(f"{API}/admin/accounts/{created.json()['id']}", headers=admin, json={"status": "LOCKED"})
    assert client.get(f"{API}/me", headers=_bearer(tok)).status_code == 401


# ---- Swagger / OpenAPI --------------------------------------------------------------------------
def test_swagger_ui_and_openapi_are_served(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "AI-VHRS API"
    assert "OAuth2PasswordBearer" in spec["components"]["securitySchemes"]
    assert "/api/v1/auth/login" in spec["paths"] and "/api/v1/auth/logout" in spec["paths"]


def test_oauth2_form_token_endpoint_for_swagger_authorize(client):
    email = make_account("CUSTOMER")
    r = client.post(f"{API}/auth/token", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"
    assert client.get(f"{API}/me", headers=_bearer(r.json())).status_code == 200
