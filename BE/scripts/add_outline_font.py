"""Add an outline (TTF/OTF) font as a writing template: checks, thins every glyph, stores the files, inserts the template.

    .venv/Scripts/python.exe scripts/add_outline_font.py --code PLAYPEN_SANS --name "Playpen Sans" ^
        --font C:\\path\\PlaypenSans.ttf --license-file C:\\path\\OFL.txt --license OFL-1.1 --source-url https://... --slug playpen-sans
        [--apply]

Without --apply nothing is written anywhere (checks, thinning and a local preview PNG only). With --apply:
  * Supabase Storage (existing bucket, prefix `fonts/<slug>/`): the font, its licence file, `<font>.glyphs.json` (the thinned
    glyphs, so a request never has to thin a glyph) and `preview.png`;
  * `templates`: ONE row (kind TYPOGRAPHY, font_uri `outline:fonts/<slug>/<file>`), `ON CONFLICT (code) DO NOTHING`, so
    re-running never overwrites a template the Manager edited. Nothing is deleted or updated.
It refuses fonts whose licence file is not one of the allowed open licences, fonts missing any Vietnamese letter, and fonts
that thin to nothing. The registry in app/assets/fonts/REGISTRY.md is edited by hand (licence, source, who checked).
The database URL and the storage key come from BE/.env and are never printed.
"""
import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.integrations.storage import SupabaseStorage  # noqa: E402
from app.services.stroke_ai import outline_font as of  # noqa: E402
from app.services.stroke_ai import text_to_stroke as tts  # noqa: E402
from app.services.stroke_ai.trajectory import render_preview  # noqa: E402

ALLOWED = {"OFL-1.1": "SIL OPEN FONT LICENSE", "Apache-2.0": "Apache License", "CC0-1.0": "CC0", "PD": "public domain"}
SAMPLE = "Xin chào Việt Nam\nPhở bò, ắ ề ỗ ử ặ\nHÀ NỘI ĐÀ LẠT"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", required=True, help="templates.code, e.g. PLAYPEN_SANS")
    ap.add_argument("--name", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--font", required=True)
    ap.add_argument("--license-file", required=True)
    ap.add_argument("--license", required=True, choices=sorted(ALLOWED))
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--preview-out", default=None)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    data = Path(a.font).read_bytes()
    lic = Path(a.license_file).read_text(encoding="utf-8", errors="replace")
    if ALLOWED[a.license].lower() not in lic.lower():
        print(f"REFUSED: the licence file does not look like {a.license}.")
        return 2
    miss = of.missing_glyphs(data)
    if miss:
        print("REFUSED: the font has no glyph for these Vietnamese characters:", "".join(miss))
        return 2
    src = of.OutlineSource(data)
    empty = src.precompute(of.vietnamese_charset())
    if empty:
        print("REFUSED: these characters thin to nothing:", "".join(empty))
        return 2
    pages = tts.compose_text(SAMPLE, source=src, paper_size="A5", font_size_mm=7.0, seed=1)
    png = render_preview(pages[0], px_per_mm=6.0)
    if a.preview_out:
        Path(a.preview_out).write_bytes(png)
    cache = json.dumps(src.export_cache(), separators=(",", ":")).encode()
    base = f"fonts/{a.slug}"
    font_path = f"{base}/{Path(a.font).name}"
    plan = [(font_path, len(data)), (f"{base}/LICENSE.txt", len(lic.encode())), (font_path + of.CACHE_SUFFIX, len(cache)),
            (f"{base}/preview.png", len(png))]
    print(f"{a.code}: licence {a.license} OK, full Vietnamese coverage, {len(src._cache)} glyphs thinned")
    print("storage objects:", *[f"{p} ({n} B)" for p, n in plan], sep="\n  ")
    print(f"templates row: code={a.code} name={a.name!r} kind=TYPOGRAPHY font_uri=outline:{font_path}")
    if not a.apply:
        print("DRY RUN: nothing was written. Re-run with --apply to write.")
        return 0

    s = get_settings()
    if not (s.supabase_url and s.supabase_service_key):
        print("REFUSED: storage is not configured in BE/.env.")
        return 2
    store = SupabaseStorage(s.supabase_url, s.supabase_service_key, s.storage_bucket, s.upload_url_ttl_seconds)
    store.write(font_path, data, "font/ttf")
    store.write(f"{base}/LICENSE.txt", lic.encode(), "text/plain")
    store.write(font_path + of.CACHE_SUFFIX, cache, "application/json")
    store.write(f"{base}/preview.png", png, "image/png")
    with get_engine().begin() as c:
        n = c.execute(text("""insert into templates (code, name, kind, font_uri, preview_url)
                              values (:c, :n, 'TYPOGRAPHY', :u, :p) on conflict (code) do nothing"""),
                      dict(c=a.code, n=a.name, u=f"outline:{font_path}", p=f"{base}/preview.png")).rowcount
    print("template inserted" if n else "template already existed: left untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
