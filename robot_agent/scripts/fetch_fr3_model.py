"""Fetch the official FAIRINO FR3 V6 robot model (URDF + STL meshes) into robot_agent/vendor/fr3/ (git-ignored).

    python scripts/fetch_fr3_model.py

Source: github.com/FAIR-INNOVATION/frcobot_ros2, package `fairino_description` (urdf/fairino3_v6.urdf, meshes/fairino3_v6/*.STL), about 5.7 MB.
That repository has NO licence file, so the model is for INTERNAL use (the workshop's own simulator/viewer) and is deliberately not committed
here. Before any public release, ask FAIRINO for permission or use their CAD downloads under the terms on their download page.
The URDF refers to `package://fairino_description/meshes/...`: the viewer and the simulator rewrite that to the local copy.
"""
import json
import sys
import urllib.request
from pathlib import Path

RAW = "https://raw.githubusercontent.com/FAIR-INNOVATION/frcobot_ros2/main/fairino_description"
API = "https://api.github.com/repos/FAIR-INNOVATION/frcobot_ros2/contents/fairino_description/meshes/fairino3_v6"
DEST = Path(__file__).resolve().parents[1] / "vendor" / "fr3"


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "vhrs-fetch"}), timeout=60) as r:
        return r.read()


def main() -> int:
    (DEST / "meshes").mkdir(parents=True, exist_ok=True)
    (DEST / "fairino3_v6.urdf").write_bytes(get(f"{RAW}/urdf/fairino3_v6.urdf"))
    names = [e["name"] for e in json.loads(get(API)) if e["name"].lower().endswith(".stl")]
    for n in names:
        (DEST / "meshes" / n).write_bytes(get(f"{RAW}/meshes/fairino3_v6/{n}"))
    total = sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())
    print(f"FR3 V6 model: URDF + {len(names)} meshes, {total / 1e6:.1f} MB, in {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
