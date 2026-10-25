"""Load failures identify the failing hop and never expose signed URL tokens or bypass the hash check."""
import argparse

import httpx
import pytest

from app.services.stroke_ai import trajectory as tj
from app.services.stroke_ai.trajectory import Page, Stroke
from scripts.robot_console import cmd_load
from vhrs_agent.bridge import BackendBridge, BridgeError, PACKAGE_READ_TIMEOUT_S, TRAJECTORY_READ_TIMEOUT_S

RAW = tj.dumps(tj.to_dict([Page("A4", [Stroke([(20, 20), (40, 20)])])], {"name": "test"}))
SIGNED_URL = "https://storage.example/trajectory?token=private-test-token"


def package(req):
    return httpx.Response(200, json={"trajectory_url": SIGNED_URL, "package_hash": tj.content_hash(RAW)})


def bridge(downloader=None, handler=package):
    return BackendBridge("https://be.example", "test-token", transport=httpx.MockTransport(handler), downloader=downloader)


def test_package_timeout_is_long_enough_for_backend_storage_and_reports_stage_without_retry():
    seen = []

    def slow(req):
        seen.append(req)
        assert req.extensions["timeout"]["read"] == PACKAGE_READ_TIMEOUT_S == 90
        assert req.extensions["timeout"]["connect"] == 5
        raise httpx.ReadTimeout("slow storage behind backend", request=req)

    with pytest.raises(BridgeError) as err:
        bridge(handler=slow).fetch_job(289)
    assert err.value.status == 504 and err.value.code == "BACKEND_TIMEOUT"
    assert "/jobs/289/package" in str(err.value)
    assert len(seen) == 1


@pytest.mark.parametrize("error_type,code", [
    (httpx.ReadTimeout, "TRAJECTORY_DOWNLOAD_TIMEOUT"),
    (httpx.ConnectError, "TRAJECTORY_DOWNLOAD_FAILED"),
])
def test_download_network_failures_are_named_and_signed_url_is_redacted(monkeypatch, error_type, code):
    calls = []

    def fail(url, **kwargs):
        calls.append(url)
        assert kwargs["timeout"].read == TRAJECTORY_READ_TIMEOUT_S == 60
        raise error_type(f"network error at {url}", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fail)
    with pytest.raises(BridgeError) as err:
        bridge().fetch_job(289)
    assert err.value.code == code
    assert "private-test-token" not in str(err.value)
    assert err.value.__suppress_context__
    assert calls == [SIGNED_URL]


def test_expired_download_is_not_misreported_as_hash_mismatch(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(403, request=httpx.Request("GET", url)))
    with pytest.raises(BridgeError) as err:
        bridge().fetch_job(289)
    assert err.value.code == "TRAJECTORY_DOWNLOAD_FAILED"
    assert "403" in str(err.value) and "private-test-token" not in str(err.value)


def test_successful_download_still_requires_the_package_hash(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(200, content=RAW, request=httpx.Request("GET", url)))
    result = bridge().fetch_job(289)
    assert result["hash"] == tj.content_hash(RAW)
    assert len(result["pages"]) == 1
    with pytest.raises(BridgeError) as err:
        bridge(downloader=lambda url: b"wrong file").fetch_job(289)
    assert err.value.code == "JOB_HASH_MISMATCH"


def test_console_load_waits_for_the_longer_package_and_download_budget(capsys):
    class Client:
        def command(self, kind, **kwargs):
            assert kind == "LOAD" and kwargs["wait_s"] == 240
            return {"kind": "LOAD", "status": "FAILED"}

    cmd_load(Client(), argparse.Namespace())


def test_load_api_surfaces_backend_timeout_without_generic_agent_error(tmp_path):
    from test_server_api import FakeBackend, auth, make

    class SlowBackend(FakeBackend):
        def __call__(self, req):
            if req.url.path.endswith("/package"):
                raise httpx.ReadTimeout("slow package", request=req)
            return super().__call__(req)

    _, client, _ = make(tmp_path, backend=SlowBackend())
    response = client.post("/api/jobs/12/load", headers=auth())
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "BACKEND_TIMEOUT"
