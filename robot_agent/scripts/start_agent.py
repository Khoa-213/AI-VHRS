"""Start the agent using the account in console.json and the workstation credential.

Run from the workstation: .simenv\python.exe -X utf8 scripts\start_agent.py
An existing Windows-encrypted password is used automatically; otherwise it is prompted. Enabled robot modes
come from agent.json; this launcher does not enable REAL or send motion commands.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.robot_console import ConsoleError, load_settings
from vhrs_agent.credentials import CredentialError, get_password
from vhrs_agent.server import ServerConfig, serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "agent.json")
    parser.add_argument("--console-config", type=Path, default=ROOT / "console.json")
    args = parser.parse_args(argv)
    try:
        cfg = ServerConfig.from_file(args.config)
        console = load_settings(args.console_config)
        if cfg.backend_url.rstrip("/") != console["backend_url"].rstrip("/"):
            raise ConsoleError("backend_url trong agent.json và console.json phải giống nhau.")
        cfg.run_dir = (args.config.resolve().parent / cfg.run_dir).resolve()
        email = console["email"]
        print(f"Agent: {email} | robot {cfg.robot_id} | backend {cfg.backend_url} | modes {list(cfg.modes)}", flush=True)
        password = get_password(console["backend_url"], email)
        # Always use the selected technician session, including when another key
        # was inherited from a previous shell setup. Only this process is changed.
        names = ("VHRS_TECH_EMAIL", "VHRS_TECH_PASSWORD", "VHRS_AGENT_KEY")
        previous = {name: os.environ.get(name) for name in names}
        cfg.agent_key = None
        try:
            os.environ["VHRS_TECH_EMAIL"] = email
            os.environ["VHRS_TECH_PASSWORD"] = password
            os.environ.pop("VHRS_AGENT_KEY", None)
            serve(cfg)
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
    except KeyboardInterrupt:
        return 0
    except (ConsoleError, CredentialError, OSError, ValueError, TypeError) as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
