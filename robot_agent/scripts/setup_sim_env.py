"""Create the simulation environment `robot_agent/.simenv` (Python 3.11 + PyBullet) without a C++ compiler or administrator rights.

    python scripts/setup_sim_env.py          # any Python 3 will do to run this script; it downloads micromamba (one exe, ~11 MB)

PyBullet publishes no Windows wheel for Python 3.11, so building it needs MSVC. conda-forge ships a ready build, hence micromamba.
Steps: micromamba -> env with python 3.11 + pybullet -> pip -> the backend's pinned requirements (+ websockets, pytest) -> the pip wheel of
numpy (conda's MKL numpy crashes inside LAPACK on this machine, error 0xc06d007f) -> the FR3 model and the viewer's JavaScript.
Everything lives under robot_agent/ and is git-ignored. Re-running skips what already exists.
"""
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
MM_URL = "https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64"
MM = HERE / "vendor" / "micromamba" / "micromamba.exe"
ENV = HERE / ".simenv"
PY = ENV / "python.exe"
BE_REQ = HERE.parent / "BE" / "requirements.txt"


def run(*cmd: object) -> None:
    print("+", *cmd, flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def main() -> int:
    if not sys.platform.startswith("win"):
        print("This script targets Windows; on Linux/macOS `pip install pybullet` normally works.")
        return 1
    if not MM.exists():
        MM.parent.mkdir(parents=True, exist_ok=True)
        MM.write_bytes(urllib.request.urlopen(MM_URL, timeout=120).read())
    if not PY.exists():
        env = dict(os.environ, MAMBA_ROOT_PREFIX=str(MM.parent / "root"))
        # the final "package cache" warning micromamba prints for a missing .pyc is harmless: the environment is complete
        subprocess.run([str(MM), "create", "-y", "-p", str(ENV), "-c", "conda-forge", "--override-channels", "python=3.11", "pybullet", "numpy"],
                       env=env)
    if not PY.exists():
        print("The environment was not created.")
        return 1
    run(PY, "-m", "ensurepip", "--upgrade")
    run(PY, "-m", "pip", "install", "-q", "-r", BE_REQ, "websockets", "pytest")
    run(PY, "-m", "pip", "install", "-q", "--force-reinstall", "--no-deps", "numpy==2.4.6")
    run(PY, HERE / "scripts" / "fetch_fr3_model.py")
    run(PY, HERE / "scripts" / "fetch_viewer_assets.py")
    run(PY, "-c", "import pybullet, numpy; print('PyBullet ok, numpy', numpy.__version__)")
    print("Ready. Try:  .simenv\\python.exe -m vhrs_agent.cli demo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
