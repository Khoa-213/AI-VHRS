"""Upload the FAIRINO FR3 V6 model (URDF + STL meshes) to object storage so the backend-hosted 3D view can serve it.

    .venv/Scripts/python.exe scripts/upload_robot_model.py [--src ../robot_agent/vendor/fr3] [--apply]

The files come from the vendor's public SDK repository (fetched by robot_agent/scripts/fetch_fr3_model.py). Without --apply nothing is
uploaded (lists what would be). Prefix in the bucket: `robot-models/fr3/`. The storage key comes from BE/.env and is never printed.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.integrations.storage import SupabaseStorage  # noqa: E402
from app.services.robot_view import MODEL_PREFIX  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(Path(__file__).resolve().parents[2] / "robot_agent" / "vendor" / "fr3"))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    src = Path(a.src)
    urdf = src / "fairino3_v6.urdf"
    meshes = sorted((src / "meshes").glob("*.STL"))
    if not urdf.exists() or not meshes:
        print(f"Missing {urdf} or meshes: run robot_agent/scripts/fetch_fr3_model.py first.", file=sys.stderr)
        return 2
    items = [(urdf, MODEL_PREFIX + urdf.name, "application/xml")] + [(m, f"{MODEL_PREFIX}meshes/{m.name}", "model/stl") for m in meshes]
    total = sum(p.stat().st_size for p, _, _ in items)
    print(f"{len(items)} files, {total / 1e6:.1f} MB -> {MODEL_PREFIX}")
    if not a.apply:
        for p, path, _ in items:
            print("  would upload", path)
        return 0
    s = get_settings()
    store = SupabaseStorage(s.supabase_url, s.supabase_service_key, s.storage_bucket, s.upload_url_ttl_seconds)
    for p, path, ctype in items:
        data = p.read_bytes()
        store.write(path, data, ctype)
        back = store.read(path)
        print(("ok   " if back == data else "FAIL ") + path)
        if back != data:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
