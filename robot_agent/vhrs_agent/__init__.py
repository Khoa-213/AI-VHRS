"""VHRS Robot Agent: runs on the workstation next to the FAIRINO FR3, never inside the web backend.

It reuses the backend's deterministic geometry (`app.services.motion`, `app.services.stroke_ai.trajectory`) so the
workstation and the server validate the very same code. When the backend package is not importable the sibling
`BE/` folder of this repository is put on the path.
"""
import sys
from pathlib import Path

try:
    import app.services.motion  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "BE"))

__version__ = "0.1.0"
