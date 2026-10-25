import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))             # robot_agent/
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "BE"))      # app.* (shared deterministic geometry)
