"""Local password reuse is scoped to backend/account and does not change robot gates."""
import json
import os

import httpx
import pytest

from vhrs_agent import credentials


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_windows_password_round_trip_is_encrypted_and_account_scoped(tmp_path):
    path = tmp_path / "credential.dpapi"
    secret = "test-password-not-a-real-credential"
    credentials.save_password("http://127.0.0.1:8000/", "Staff@Example.com", secret, path=path)
    assert secret.encode() not in path.read_bytes()
    assert credentials.load_password("http://127.0.0.1:8000", "staff@example.com", path=path) == secret
    assert credentials.load_password("http://different.example", "staff@example.com", path=path) is None
    assert credentials.load_password("http://127.0.0.1:8000", "other@example.com", path=path) is None
    assert not path.with_name(path.name + ".tmp").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_damaged_credential_is_not_used_as_plaintext(tmp_path):
    path = tmp_path / "credential.dpapi"
    path.write_bytes(b"not a DPAPI blob")
    with pytest.raises(credentials.CredentialError):
        credentials.load_password("https://be.example", "staff@example.com", path=path)


def test_cached_credential_avoids_prompt_and_stale_environment_password(monkeypatch):
    monkeypatch.setattr(credentials, "load_password", lambda backend, email: "cached-test-password")
    monkeypatch.setenv("VHRS_TECH_PASSWORD", "stale-test-password")
    monkeypatch.setattr(credentials.getpass, "getpass", lambda prompt: pytest.fail("unexpected password prompt"))
    assert credentials.get_password("https://be.example", "staff@example.com") == "cached-test-password"
    assert credentials.get_password("https://be.example", "staff@example.com", "explicit-test") == "explicit-test"


def test_console_uses_cached_password_for_selected_account_without_prompt(monkeypatch):
    from scripts.robot_console import Client

    def cached(backend, email):
        assert (backend, email) == ("https://be.example", "staff@example.com")
        return "cached-test-password"

    def backend(req):
        assert json.loads(req.content) == {"email": "staff@example.com", "password": "cached-test-password"}
        return httpx.Response(200, json={"account": {"role": "TECHNICAL_STAFF"}, "access_token": "test-token"})

    monkeypatch.setattr(credentials, "load_password", cached)
    monkeypatch.setattr(credentials.getpass, "getpass", lambda prompt: pytest.fail("unexpected password prompt"))
    client = Client({"backend_url": "https://be.example", "email": "staff@example.com", "job_id": 289},
                    transport=httpx.MockTransport(backend))
    client.login()
    assert client.token == "test-token"


def test_agent_launcher_uses_cached_password_and_restores_process_environment(monkeypatch):
    from scripts import start_agent
    from vhrs_agent.server import ServerConfig

    cfg = ServerConfig(backend_url="https://be.example", robot_id=46)
    monkeypatch.setattr(start_agent.ServerConfig, "from_file", lambda path: cfg)
    monkeypatch.setattr(start_agent, "load_settings", lambda path: {"backend_url": cfg.backend_url, "email": "staff@example.com"})
    monkeypatch.setattr(credentials, "load_password", lambda backend, email: "cached-test-password")
    monkeypatch.setattr(credentials.getpass, "getpass", lambda prompt: pytest.fail("unexpected password prompt"))
    monkeypatch.setenv("VHRS_TECH_EMAIL", "old@example.com")
    monkeypatch.setenv("VHRS_AGENT_KEY", "old-test-key")
    names = ("VHRS_TECH_EMAIL", "VHRS_TECH_PASSWORD", "VHRS_AGENT_KEY")
    before = {name: os.environ.get(name) for name in names}

    def fake_serve(agent):
        assert os.environ["VHRS_TECH_EMAIL"] == "staff@example.com"
        assert os.environ["VHRS_TECH_PASSWORD"] == "cached-test-password"
        assert "VHRS_AGENT_KEY" not in os.environ and agent.agent_key is None
        assert agent.modes == ("mock", "sim")
        raise KeyboardInterrupt

    monkeypatch.setattr(start_agent, "serve", fake_serve)
    assert start_agent.main([]) == 0
    assert before == {name: os.environ.get(name) for name in names}
