"""Fetch the JavaScript the 3D viewer needs into vhrs_agent/static/vendor/ so the workshop network does not depend on a CDN.

    python scripts/fetch_viewer_assets.py

three.js r160 (MIT) and urdf-loader 0.12.1 (Apache-2.0), at pinned versions, from jsDelivr. They are git-ignored; this script is the record.
"""
import sys
import urllib.request
from pathlib import Path

CDN = "https://cdn.jsdelivr.net/npm"
THREE = "three@0.160.0"
URDF = "urdf-loader@0.12.1"
FILES = {
    f"{THREE}/build/three.module.js": "three/build/three.module.js",
    f"{THREE}/examples/jsm/loaders/STLLoader.js": "three/examples/jsm/loaders/STLLoader.js",
    f"{THREE}/examples/jsm/loaders/ColladaLoader.js": "three/examples/jsm/loaders/ColladaLoader.js",
    f"{THREE}/examples/jsm/loaders/TGALoader.js": "three/examples/jsm/loaders/TGALoader.js",
    f"{THREE}/examples/jsm/controls/OrbitControls.js": "three/examples/jsm/controls/OrbitControls.js",
    f"{URDF}/src/URDFLoader.js": "urdf-loader/src/URDFLoader.js",
    f"{URDF}/src/URDFClasses.js": "urdf-loader/src/URDFClasses.js",
}
DEST = Path(__file__).resolve().parents[1] / "vhrs_agent" / "static" / "vendor"


def main() -> int:
    total = 0
    for src, rel in FILES.items():
        data = urllib.request.urlopen(urllib.request.Request(f"{CDN}/{src}", headers={"User-Agent": "vhrs-fetch"}), timeout=60).read()
        out = DEST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        total += len(data)
    print(f"{len(FILES)} files, {total / 1e6:.1f} MB in {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
