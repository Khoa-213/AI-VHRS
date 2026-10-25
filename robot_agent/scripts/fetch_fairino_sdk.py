"""Fetch the official FAIRINO Python SDK at the pinned commit into robot_agent/vendor/ (git-ignored).

    python scripts/fetch_fairino_sdk.py

The SDK is Apache-2.0 (github.com/FAIR-INNOVATION/fairino-python-sdk). It is NOT committed to this repository and not
installed with pip (the vendor publishes no pip package and no releases). The pinned commit is the last tag for
robot software 3.8.x; the workshop's controller is V3.8.25-QX, newer than that tag, so compatibility must be confirmed with
the read-only connect() on site before anything else. Windows 3.11 uses windows/libfairino/Robot.cp311-win_amd64.pyd.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = "https://github.com/FAIR-INNOVATION/fairino-python-sdk.git"
COMMIT = "55bcce6e7eab6a3ae45ddb0391e580ee06892248"      # Python_SDK_2.1.7.1_robot_v3.8.7.1


def main() -> int:
    dest = Path(__file__).resolve().parents[1] / "vendor" / "fairino"
    flavour = "windows" if sys.platform.startswith("win") else "linux"
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "clone", "--quiet", REPO, tmp], check=True)
        subprocess.run(["git", "-C", tmp, "checkout", "--quiet", COMMIT], check=True)
        src = Path(tmp) / flavour
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src / "fairino", dest)
        lib = src / "libfairino"
        for f in lib.glob(f"Robot.cp{sys.version_info.major}{sys.version_info.minor}-*"):
            shutil.copy2(f, dest / f.name)
    print(f"SDK {COMMIT[:7]} ({flavour}) copied to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
