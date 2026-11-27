"""Redraw the public sample picture of every outline-font template (`fonts/<slug>/preview.png` in the catalog media bucket)
as the customer-facing card: the sample strokes cut to the text, no sheet, no stroke-start dots (owner 2026-11-27: the web
app shows only what the robot writes). The fonts and their thinned glyphs are read from the private bucket; nothing there
and nothing in the database is changed. Dry run unless --apply.

    .venv/bin/python scripts/refresh_font_cards.py [--out DIR] [--apply]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.integrations.storage import SupabaseStorage, get_media_storage  # noqa: E402
from app.services.stroke_ai import outline_font as of  # noqa: E402
from app.services.stroke_ai import text_to_stroke as tts  # noqa: E402
from app.services.stroke_ai.trajectory import render_card  # noqa: E402

SAMPLE = "Xin chào Việt Nam\nPhở bò, ắ ề ỗ ử ặ\nHÀ NỘI ĐÀ LẠT"      # the sample of add_outline_font.py


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="also save the pictures here")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_key):
        print("REFUSED: storage is not configured in BE/.env.")
        return 2
    store = SupabaseStorage(s.supabase_url, s.supabase_service_key, s.storage_bucket, s.upload_url_ttl_seconds)
    with get_engine().connect() as c:
        rows = c.execute(text("""select code, font_uri, preview_url from templates
                                 where kind = 'TYPOGRAPHY' and font_uri like 'outline:fonts/%' and preview_url like 'fonts/%/preview.png'
                                 order by id""")).all()
    for code, font_uri, preview in rows:
        src = of.load_source(font_uri[len(of.OUTLINE_PREFIX):], store.read)
        page = tts.compose_text(SAMPLE, source=src, paper_size="A5", font_size_mm=7.0, seed=1)[0]
        png = render_card(page)
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            (Path(a.out) / f"{code}.png").write_bytes(png)
        if a.apply:
            get_media_storage().write(preview, png, "image/png")
        print(f"{'WROTE ' if a.apply else 'WOULD WRITE '}{preview} ({len(png)} B) for {code}")
    print("done" if a.apply else "DRY RUN: nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
