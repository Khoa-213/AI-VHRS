"""Rate limiting, security headers and CORS."""
from app.core.config import get_settings
from app.core.ratelimit import SlidingWindowLimiter

API = "/api/v1"


# ---- limiter unit tests (fake clock, no DB) -----------------------------------------------------
def test_limiter_blocks_after_limit_and_recovers_after_window():
    now = [1000.0]
    lim = SlidingWindowLimiter(clock=lambda: now[0])
    assert [lim.hit("r", "ip", 3, 60) for _ in range(3)] == [0, 0, 0]
    wait = lim.hit("r", "ip", 3, 60)
    assert 1 <= wait <= 61
    now[0] += 61
    assert lim.hit("r", "ip", 3, 60) == 0


def test_limiter_is_per_key_and_per_rule():
    lim = SlidingWindowLimiter(clock=lambda: 1.0)
    assert lim.hit("login", "a", 1, 60) == 0
    assert lim.hit("login", "a", 1, 60) > 0
    assert lim.hit("login", "b", 1, 60) == 0
    assert lim.hit("register", "a", 1, 60) == 0


# ---- HTTP behaviour -----------------------------------------------------------------------------
def test_rate_limit_returns_429_with_retry_after(client):
    body = {"email": "nobody@example.com"}
    for _ in range(5):
        assert client.post(f"{API}/auth/password-reset/request", json=body).status_code == 202
    r = client.post(f"{API}/auth/password-reset/request", json=body)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["retry-after"]) >= 1


def test_forwarded_for_is_ignored_unless_proxy_is_trusted(client):
    body = {"email": "nobody@example.com"}
    for i in range(5):
        client.post(f"{API}/auth/password-reset/request", json=body, headers={"X-Forwarded-For": f"1.1.1.{i}"})
    r = client.post(f"{API}/auth/password-reset/request", json=body, headers={"X-Forwarded-For": "9.9.9.9"})
    assert r.status_code == 429  # spoofed header gives no fresh bucket


def test_forwarded_for_buckets_clients_when_proxy_is_trusted(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
    body = {"email": "nobody@example.com"}
    hdr = lambda ip: {"X-Forwarded-For": ip}  # noqa: E731
    for _ in range(5):
        assert client.post(f"{API}/auth/password-reset/request", json=body, headers=hdr("10.0.0.1")).status_code == 202
    assert client.post(f"{API}/auth/password-reset/request", json=body, headers=hdr("10.0.0.1")).status_code == 429
    assert client.post(f"{API}/auth/password-reset/request", json=body, headers=hdr("10.0.0.2")).status_code == 202


def test_rate_limit_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
    for _ in range(8):
        assert client.post(f"{API}/auth/password-reset/request", json={"email": "x@example.com"}).status_code == 202


def test_security_headers_on_api_responses(client):
    h = client.get(f"{API}/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in h["content-security-policy"]
    assert h["cache-control"] == "no-store"
    assert "strict-transport-security" not in h  # plain HTTP in tests


def test_swagger_ui_is_not_blocked_by_csp(client):
    r = client.get("/docs")
    assert r.status_code == 200
    assert "content-security-policy" not in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"


def test_hsts_only_over_https(client):
    r = client.get(f"{API}/health", headers={"Host": "api.example.com"})
    assert "strict-transport-security" not in r.headers
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app, base_url="https://api.example.com") as https:
        assert "max-age=31536000" in https.get(f"{API}/health").headers["strict-transport-security"]


def test_cors_allows_configured_origin_only(client):
    ok = client.options(f"{API}/auth/login", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type"})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    bad = client.options(f"{API}/auth/login", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert bad.status_code == 400 and "access-control-allow-origin" not in bad.headers
