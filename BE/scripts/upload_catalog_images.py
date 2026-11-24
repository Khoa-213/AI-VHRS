"""Load the workshop's product photos into the catalog in one go (migration 0030), and copy the stored template previews to
the public media bucket.

    .venv/bin/python scripts/upload_catalog_images.py --dir <folder>             # dry run: shows what would be uploaded
    .venv/bin/python scripts/upload_catalog_images.py --dir <folder> --apply
    .venv/bin/python scripts/upload_catalog_images.py --templates [--apply]

Folder layout (jpg / jpeg / png / webp; the file name without its extension names the row):
    papers/<paper code>.jpg          e.g. papers/ART120_A4.jpg
    pens/<pen code>.png              e.g. pens/GEL05.png
    inks/<pen code>/<ink>.jpg        <ink> = the ink's id, or its name (upper / lower case does not matter), e.g. inks/GEL05/Đen.jpg

Every file goes through the same rules as `PUT /manager/papers|pens|inks/{id}/image` (services.catalog_media: real type,
5 MB, upright, at most 800 px, WebP, no EXIF) and is recorded in the audit log (`--actor-email`: the Manager it is done for;
without it the actor is empty). A file that names no row or is not a usable image is reported and skipped. A row that already
has this exact photo is left as it is. Without --apply nothing is written anywhere.

--templates: every template whose `preview_url` is an object path gets that object copied from the private bucket to the
public media bucket (same path) unless the same file is already there. No database row changes.

The database URL and the storage key come from BE/.env and are never printed.
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.errors import AppError  # noqa: E402
from app.db.session import _factory  # noqa: E402
from app.integrations.storage import get_media_storage, get_storage  # noqa: E402
from app.models.account import Account  # noqa: E402
from app.models.catalog import InkColor, PaperType, PenType, Template  # noqa: E402
from app.services import catalog_media  # noqa: E402
from app.services.manager_catalog import ManagerCatalogService  # noqa: E402

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MODELS = {"paper": PaperType, "pen": PenType, "ink": InkColor}


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)             # macOS hands file names back decomposed


def _files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS)


def resolve(session, root: Path, file: Path) -> tuple[str, int, str] | str:
    """(material, row id, label) the file is the photo of, or a sentence saying why it names no row."""
    parts = [_nfc(x) for x in file.relative_to(root).parts]
    stem = _nfc(file.stem)
    if len(parts) == 2 and parts[0] in ("papers", "pens"):
        model, material = (PaperType, "paper") if parts[0] == "papers" else (PenType, "pen")
        row = session.scalar(select(model).where(model.code == stem))
        return (material, row.id, f"{row.code} ({row.name})") if row else f"no {material} with code '{stem}'"
    if len(parts) == 3 and parts[0] == "inks":
        pen = session.scalar(select(PenType).where(PenType.code == parts[1]))
        if pen is None:
            return f"no pen with code '{parts[1]}'"
        inks = list(session.scalars(select(InkColor).where(InkColor.pen_type_id == pen.id)))
        hit = [i for i in inks if str(i.id) == stem] or [i for i in inks if _nfc(i.name).casefold() == stem.casefold()]
        if len(hit) != 1:
            return f"pen {pen.code} has {len(hit)} inks called '{stem}' (its inks: {', '.join(f'{i.id}={i.name}' for i in inks)})"
        return "ink", hit[0].id, f"{pen.code} / {hit[0].name}"
    return "not under papers/<code>, pens/<code> or inks/<pen code>/<ink>"


def upload_dir(root: Path, apply: bool, actor_email: str | None) -> int:
    files = _files(root)
    if not files:
        print(f"No image (jpg, jpeg, png, webp) under {root}.")
        return 2
    media = get_media_storage() if apply else None
    actor_id = None
    if actor_email:
        with _factory()() as session:
            actor_id = session.scalar(select(Account.id).where(Account.email == actor_email))
        if actor_id is None:
            print(f"REFUSED: no account with e-mail {actor_email}.")
            return 2
    done = same = skipped = 0
    for file in files:
        rel = file.relative_to(root).as_posix()
        with _factory()() as session:
            target = resolve(session, root, file)
            if isinstance(target, str):
                print(f"SKIP  {rel}: {target}")
                skipped += 1
                continue
            material, row_id, label = target
            try:
                stored, width, height = catalog_media.normalise(file.read_bytes())
            except AppError as exc:
                print(f"SKIP  {rel}: {exc.code} {exc.message}")
                skipped += 1
                continue
            note = f"{rel} -> {material} {row_id} {label}: {width}x{height}, {len(stored) // 1024 or 1} KB"
            if session.get(MODELS[material], row_id).image_path == catalog_media.object_path(material, row_id, stored):
                print("SAME ", note)
                same += 1
                continue
            if not apply:
                print("WOULD", note)
                done += 1
                continue
            svc = ManagerCatalogService(session, SimpleNamespace(id=actor_id))
            row = svc.set_image(material, row_id, file.read_bytes(), media)
            session.commit()
            print("OK   ", note, "->", row.image_url)
            done += 1
    print(f"{'Uploaded' if apply else 'Would upload'}: {done}; already there: {same}; skipped: {skipped}."
          + ("" if apply else " DRY RUN: nothing was written. Re-run with --apply to write."))
    return 0 if not skipped else 1


def copy_template_previews(apply: bool) -> int:
    private, public = get_storage(), get_media_storage()
    with _factory()() as session:
        rows = list(session.scalars(select(Template).where(Template.preview_url.is_not(None)).order_by(Template.id)))
    todo = missing = same = 0
    for t in rows:
        path = t.preview_url
        if path.startswith(("http://", "https://")):
            continue
        data = private.read(path)
        if data is None:
            print(f"MISSING {t.code}: no object '{path}' in the private bucket")
            missing += 1
            continue
        if public.read(path) == data:
            print(f"SAME    {t.code}: {path}")
            same += 1
            continue
        if apply:
            public.write(path, data, "image/png" if path.lower().endswith(".png") else "image/webp")
        print(f"{'COPIED ' if apply else 'WOULD  '} {t.code}: {path} ({len(data)} B) -> {public.public_url(path)}")
        todo += 1
    print(f"{'Copied' if apply else 'Would copy'}: {todo}; already there: {same}; missing: {missing}."
          + ("" if apply else " DRY RUN: nothing was written. Re-run with --apply to write."))
    return 0 if not missing else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", help="folder with papers/, pens/, inks/ (see the module text)")
    ap.add_argument("--templates", action="store_true", help="copy stored template previews to the public media bucket")
    ap.add_argument("--actor-email", help="Manager account the audit log names for the uploads")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    if bool(a.dir) == a.templates:
        ap.error("give exactly one of --dir <folder> or --templates")
    try:
        return copy_template_previews(a.apply) if a.templates else upload_dir(Path(a.dir), a.apply, a.actor_email)
    except AppError as exc:
        print(f"REFUSED: {exc.code} {exc.message}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
