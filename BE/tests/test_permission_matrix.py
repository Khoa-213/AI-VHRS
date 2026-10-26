"""Who may call what: one table for the whole API, checked against every route the app registers.

Authentication = the Bearer access token (JWT). The server re-reads the account and its session from the database on
every request, so locking an account, logging out or changing a role takes effect immediately; the role is NEVER taken
from the token's own claims. Authorization = `require_roles(...)` on each route (403 `FORBIDDEN` when the role is not
allowed). This test keeps the two honest:

* every route must match a rule below (a new endpoint without a rule fails the test, so nothing is left open by accident);
* anonymous calls to protected routes answer 401;
* every role outside the rule gets 403 `FORBIDDEN`, every role inside it gets anything but 401/403.

Calls use ids that do not exist and empty bodies, so allowed roles end in 404/422 and nothing is changed.
"""
import re

import pytest

from app.main import app
from tests.conftest import auth

CUSTOMER, STAFF, TECH, MANAGER, ADMIN = "CUSTOMER", "STAFF", "TECHNICAL_STAFF", "MANAGER", "ADMIN"
ROLES = [CUSTOMER, STAFF, TECH, MANAGER, ADMIN]
PUBLIC, ANY, SIGNED = "PUBLIC", "ANY_AUTHENTICATED", "SIGNED_WEBHOOK"
VIEW_TICKET = "VIEW_TICKET"        # read-only 3D view: a signed short-lived ticket in the path, never a login
AGENT_KEY = "AGENT_KEY"            # Robot Agent credential (Bearer vhrs_ak_...): a user's JWT must not open it
VNPAY_IPN = "VNPAY_IPN"            # signed by VNPay; answers HTTP 200 with RspCode 97 when the signature is missing/invalid
READ = {"GET"}
WRITE = {"POST", "PUT", "PATCH", "DELETE"}
ALL = READ | WRITE

# (regex on the path without /api/v1, methods, who). First match wins, so specific rules come first.
RULES: list[tuple[str, set[str], object]] = [
    (r"^/health$", ALL, PUBLIC),
    (r"^/(catalog/(papers|pens|templates|suggest-materials|text-styles)|privacy-policy)", READ, PUBLIC),
    (r"^/catalog/templates/\{template_id\}/preview$", {"POST"}, PUBLIC),    # styled preview of a template (rate limited)
    (r"^/locations/", READ, ANY),                                              # address pickers: any signed-in role
    (r"^/pricing/estimate$", ALL, {CUSTOMER}),
    (r"^/auth/(register|login|google|refresh|token|password-reset/(request|confirm))$", ALL, PUBLIC),
    (r"^/webhooks/shipments/\{carrier\}$", ALL, SIGNED),                      # authenticated by the carrier's secret / signature
    (r"^/webhooks/payments/vnpay/ipn$", ALL, VNPAY_IPN),
    (r"^/webhooks/payments/momo/ipn$", ALL, SIGNED),
    (r"^/webhooks/payments/payos$", ALL, SIGNED),
    (r"^/webhooks/payments/\{gateway\}$", ALL, SIGNED),                      # no token: authenticated by the HMAC signature
    (r"^/agent/", ALL, AGENT_KEY),
    (r"^/robot-model/", READ, PUBLIC),                                       # vendor SDK files (public), served from storage
    (r"^/viewer/\{ticket\}/", READ, VIEW_TICKET),
    (r"^/auth/logout$", ALL, ANY),
    (r"^/me/conversations", ALL, {CUSTOMER}),                                # the customer's chat inbox and unread badge
    (r"^/me", ALL, ANY),
    (r"^/catalog/my-styles$", READ, {CUSTOMER}),
    (r"^/orders/\{order_id\}/messages", ALL, {CUSTOMER, STAFF, MANAGER}),    # the Manager joins chats to resolve complaints
    (r"^/orders", ALL, {CUSTOMER}),
    (r"^/payments/", ALL, {CUSTOMER}),                                       # gateways list, refresh, mock-checkout
    (r"^/workshop/", READ, {STAFF, MANAGER}),
    (r"^/workshop/", WRITE, {STAFF}),                                        # accept, reject, sketch, quote, send: Staff only
    (r"^/technician/", ALL, {TECH}),                                         # only the technician, and only their own jobs (BR-19)
    (r"^/manager/", ALL, {MANAGER}),
    (r"^/admin/", ALL, {ADMIN}),
]


def _rule(method: str, path: str):
    for pattern, methods, who in RULES:
        if re.match(pattern, path) and method in methods:
            return who
    return None


def _code(r) -> str | None:
    try:
        data = r.json()
    except ValueError:
        return None
    return (data.get("error") or {}).get("code") if isinstance(data, dict) else None


def _routes() -> list[tuple[str, str]]:
    out = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            out.append((method.upper(), path.removeprefix("/api/v1")))
    return sorted(out)


def _url(path: str) -> str:
    return "/api/v1" + re.sub(r"\{(\w+)\}", lambda m: {"gateway": "VNPAY", "carrier": "GHN"}.get(m.group(1), "999999999"), path)


@pytest.fixture(scope="module")
def tokens(client):
    return {role: auth(client, role) for role in ROLES}


def test_every_route_has_a_permission_rule():
    missing = [f"{m} {p}" for m, p in _routes() if _rule(m, p) is None]
    assert not missing, f"routes without a rule in RULES (add them, never leave a route unclassified): {missing}"


def test_oauth_form_login_is_the_only_unlisted_form_route():
    assert _rule("POST", "/auth/token") is PUBLIC


def test_permission_matrix_is_enforced_on_every_route(client, tokens):
    problems: list[str] = []
    for method, path in _routes():
        who = _rule(method, path)
        url = _url(path)
        body = {} if method in WRITE else None
        anon = client.request(method, url, json=body)
        if who is SIGNED:                               # a bearer token must not open this door, only a valid signature
            for headers in ({}, tokens[MANAGER], tokens[ADMIN]):
                r = client.request(method, url, json=body, headers=headers)
                if r.status_code != 401 or _code(r) != "INVALID_SIGNATURE":
                    problems.append(f"{method} {path}: unsigned call got {r.status_code} {_code(r)}")
            continue
        if who is VIEW_TICKET:
            for headers in ({}, tokens[MANAGER], tokens[TECH]):
                r = client.request(method, url, json=body, headers=headers)
                if r.status_code != 401 or _code(r) != "INVALID_VIEW_TICKET":
                    problems.append(f"{method} {path}: call without a valid view ticket got {r.status_code} {_code(r)}")
            continue
        if who is AGENT_KEY:
            for headers in ({}, tokens[MANAGER], tokens[TECH], {"Authorization": "Bearer vhrs_ak_nope"}):
                r = client.request(method, url, json=body, headers=headers)
                if r.status_code != 401 or _code(r) != "INVALID_AGENT_KEY":
                    problems.append(f"{method} {path}: call without a valid agent key got {r.status_code} {_code(r)}")
            continue
        if who is VNPAY_IPN:
            for headers in ({}, tokens[MANAGER], tokens[ADMIN]):
                r = client.request(method, url, json=body, headers=headers)
                if r.status_code != 200 or (r.json() or {}).get("RspCode") != "97":
                    problems.append(f"{method} {path}: unsigned VNPay IPN got {r.status_code} {r.text[:80]}")
            continue
        if who is PUBLIC:
            if anon.status_code in (401, 403):
                problems.append(f"{method} {path}: public route answered {anon.status_code}")
            continue
        if anon.status_code != 401:
            problems.append(f"{method} {path}: anonymous got {anon.status_code}, expected 401")
        if who == ANY or path == "/auth/logout":
            continue                                    # any signed-in role; calling /me or /logout would change the session
        for role in ROLES:
            r = client.request(method, url, json=body, headers=tokens[role])
            code = _code(r)
            if role in who:
                if r.status_code == 401 or (r.status_code == 403 and code == "FORBIDDEN"):
                    problems.append(f"{method} {path}: {role} should be allowed, got {r.status_code} {code}")
            elif r.status_code != 403 or code != "FORBIDDEN":
                problems.append(f"{method} {path}: {role} should be refused with 403 FORBIDDEN, got {r.status_code} {code}")
    assert not problems, "\n".join(problems)


def test_the_role_comes_from_the_database_not_the_token(client):
    """A Customer token keeps being a Customer token: nothing in the request can raise the role."""
    h = auth(client, CUSTOMER)
    assert client.get("/api/v1/manager/pricing-config", headers={**h, "X-Role": MANAGER}).status_code == 403
    assert client.get("/api/v1/manager/pricing-config", headers={"Authorization": h["Authorization"] + "x"}).status_code == 401
    assert client.get("/api/v1/manager/pricing-config", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    assert client.get("/api/v1/manager/pricing-config", headers={"Authorization": "Basic abc"}).status_code == 401


def test_logout_revokes_the_token_at_once(client):
    h = auth(client, STAFF)
    assert client.get("/api/v1/me", headers=h).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=h).status_code in (200, 204)
    assert client.get("/api/v1/me", headers=h).status_code == 401              # server-side session revoked: token is dead
