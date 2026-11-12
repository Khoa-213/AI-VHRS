"""Upgrade U3: fetch a small, fixed sample of REAL Vietnamese handwriting images for the internal benchmark.

Source: Hugging Face dataset 5CD-AI/Viet-Handwriting-gemini-VQA (1,252 images from UIT-HWDB + Cinnamon AI Challenge;
`label` = the text of the image; the Gemini descriptions / Q&A are NOT used). The dataset is gated: the owner accepted its
terms on Hugging Face and supplies a read token as HF_TOKEN (environment or BE/.env). The token is never printed.

The card gives no licence and the source datasets are, as far as we know, for research only, so the images stay OUT of
git (benchmarks/data/ is ignored) and are used only to measure the system internally. Only the list of row ids + text +
SHA-256 (manifest.jsonl) describes the sample.

Sample: N rows evenly spread over the split (deterministic, same rows on every machine).

    python scripts/fetch_hf_handwriting.py            # 50 images into benchmarks/data/viet_hw/
    python scripts/fetch_hf_handwriting.py --n 20
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DATASET = "5CD-AI/Viet-Handwriting-gemini-VQA"
ROWS = "https://datasets-server.huggingface.co/rows"
TOTAL = 1252
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "benchmarks" / "data" / "viet_hw"


def _token() -> str:
    tok = os.environ.get("HF_TOKEN")
    if not tok and (BASE / ".env").exists():
        for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("HF_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not tok:
        sys.exit("HF_TOKEN is not set (environment or BE/.env).")
    return tok


def _get(url: str, token: str | None, tries: int = 8) -> bytes:
    """Retries with growing pauses: the public rows API answers 503 / 429 now and then."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                sys.exit(f"HTTP {exc.code}: token refused or dataset terms not accepted on Hugging Face.")
            err = exc
        except Exception as exc:                                                     # noqa: BLE001
            err = exc
        if i == tries - 1:
            raise RuntimeError(f"GET failed: {url.split('?')[0]}: {err}") from None
        wait = min(5 * 2 ** i, 60)
        print(f"     {err}; retry in {wait}s")
        time.sleep(wait)
    raise AssertionError


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    args = ap.parse_args()
    token = _token()
    offsets = sorted({round(i * (TOTAL - 1) / max(args.n - 1, 1)) for i in range(args.n)})
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "manifest.jsonl"                           # resumable: rows already saved are skipped
    done = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = json.loads(line)
            if (OUT / m["file"]).exists():
                done[m["offset"]] = m
    manifest = [done[o] for o in offsets if o in done]
    for off in offsets:
        if off in done:
            continue
        q = urllib.parse.urlencode({"dataset": DATASET, "config": "default", "split": "train",
                                    "offset": off, "length": 1})
        row = json.loads(_get(f"{ROWS}?{q}", token))["rows"][0]["row"]
        data = _get(row["image"]["src"], None)               # signed asset URL, no token needed
        ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
        name = f"{row['id']:05d}{ext}"
        (OUT / name).write_bytes(data)
        manifest.append({"id": row["id"], "offset": off, "file": name, "label": row.get("label"),
                         "width": row["image"].get("width"), "height": row["image"].get("height"),
                         "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(manifest[-1], ensure_ascii=False) + "\n")
        print(f"{len(manifest):3d}/{len(offsets)} id={row['id']} {len(data) // 1024} KB")
    total = sum(m["bytes"] for m in manifest)
    print(f"saved {len(manifest)} images, {total / 1e6:.1f} MB -> {OUT}")


if __name__ == "__main__":
    main()
