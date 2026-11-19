"""V2 Phase E part 1 (owner decision D4 + E-a..E-d, 2026-11-19): measure Vietnamese handwriting recognition (HTR) on the 50
public U3 pages before choosing anything. NOT product code; nothing here is imported by the app.

Engines
* vietocr  - VietOCR `vgg_transformer` on CPU, run inside the separate benchmark environment `benchmarks/.venv-htr`
             (torch + vietocr are NOT in requirements.txt). VietOCR reads one text line at a time, so pages are cut into
             lines first by a horizontal projection of the binarised page (no extra model, owner decision E-c); line cutting
             errors count against VietOCR and are reported.
* gemini   - the configured Gemini model (GEMINI_MODEL in BE/.env) reads the whole page; at most 100 calls per run
             directory (counted in calls.json), answers cached per page so a rerun does not call again.

Ground truth = the human `label` of each page (UIT-HWDB via 5CD-AI/Viet-Handwriting-gemini-VQA, benchmarks/data/viet_hw).
Metrics: CER / WER (NFC, whitespace collapsed) exact and "loose" (lower case, punctuation removed), insertions per reference
character, seconds per page, peak RSS (VietOCR), tokens (Gemini).
Hallucination checks (plan Test 5): a blank page, a noise page and 5 pages with a white band over the middle third. A good
reader returns nothing / "[?]" for the first two and clearly less text for the masked pages.

Usage (from BE/):
    benchmarks/.venv-htr/Scripts/python.exe scripts/benchmark_htr.py --engine vietocr
    benchmarks/.venv-htr/Scripts/python.exe scripts/benchmark_htr.py --engine gemini
    benchmarks/.venv-htr/Scripts/python.exe scripts/benchmark_htr.py --report
The API key is read from BE/.env and never printed.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "benchmarks" / "data"
PAGES = DATA / "viet_hw"
OUT = DATA / "htr"
WEIGHTS = DATA / "models" / "vgg_transformer.pth"
REPORT = BASE / "docs" / "benchmarks" / "E_htr_benchmark_2026-11-19.md"
MAX_GEMINI_CALLS = 100
MASKED = 5

PROMPT = ("Chép lại NGUYÊN VĂN toàn bộ chữ viết tay tiếng Việt trong ảnh, theo thứ tự đọc, giữ dấu và dấu câu. "
          "Không sửa chính tả, không thêm, không tóm tắt, không giải thích. Chữ nào không đọc được thì ghi [?] đúng chỗ "
          "đó, tuyệt đối không đoán hay tự điền. Nếu ảnh không có chữ viết tay thì chỉ trả lời [?]. Chỉ trả về phần chữ.")


# ---------------------------------------------------------------------------------------------------------- data
def manifest() -> list[dict]:
    return [json.loads(x) for x in (PAGES / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def norm(s: str, loose: bool = False) -> str:
    s = unicodedata.normalize("NFC", s or "")
    if loose:
        s = s.lower()
        s = "".join(ch if not unicodedata.category(ch).startswith("P") else " " for ch in s)
    return re.sub(r"\s+", " ", s).strip()


def edit_ops(ref: list, hyp: list) -> dict[str, int]:
    """Levenshtein with the counts of substitutions / deletions / insertions (one backtrace)."""
    n, m = len(ref), len(hyp)
    prev = list(range(m + 1))
    rows = [prev]
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        r = ref[i - 1]
        for j in range(1, m + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != hyp[j - 1]))
        rows.append(cur)
        prev = cur
    i, j, sub, dele, ins = n, m, 0, 0, 0
    while i or j:
        if i and j and rows[i][j] == rows[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            sub += ref[i - 1] != hyp[j - 1]
            i, j = i - 1, j - 1
        elif i and rows[i][j] == rows[i - 1][j] + 1:
            dele, i = dele + 1, i - 1
        else:
            ins, j = ins + 1, j - 1
    return {"dist": rows[n][m], "sub": sub, "del": dele, "ins": ins, "ref": n}


def scores(ref: str, hyp: str) -> dict:
    out = {}
    for tag, loose in (("exact", False), ("loose", True)):
        r, h = norm(ref, loose), norm(hyp.replace("[?]", " "), loose)
        c = edit_ops(list(r), list(h))
        w = edit_ops(r.split(), h.split())
        out[tag] = {"cer": c["dist"] / max(1, c["ref"]), "wer": w["dist"] / max(1, w["ref"]),
                    "ins_per_char": c["ins"] / max(1, c["ref"]), "del_per_char": c["del"] / max(1, c["ref"])}
    out["unknown_marks"] = hyp.count("[?]")
    return out


# ---------------------------------------------------------------------------------------------------------- images
def load_gray(path: Path):
    import cv2
    img = cv2.imdecode(__import__("numpy").fromfile(str(path), dtype="uint8"), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"cannot read {path}")
    return img


def special_pages(rows: list[dict]):
    """(name, gray image, reference or None, kind) for the hallucination checks."""
    import numpy as np
    first = load_gray(PAGES / rows[0]["file"])
    h, w = first.shape
    rng = np.random.default_rng(7)
    yield "blank", np.full((h, w), 245, np.uint8), None, "blank"
    yield "noise", rng.integers(0, 256, (h, w), dtype=np.uint8), None, "noise"
    for r in rows[:MASKED]:
        g = load_gray(PAGES / r["file"]).copy()
        hh = g.shape[0]
        g[hh // 3: 2 * hh // 3, :] = 245
        yield f"masked_{r['id']}", g, r["label"], "masked"


def split_lines(gray):
    """Text lines of a page, top to bottom (grayscale crops). Handwritten lines touch (accents, descenders), so a plain
    threshold on the horizontal ink profile merges them: the page is cut at the valleys of the smoothed profile, at least
    half a line pitch apart (pitch = first peak of the profile's autocorrelation)."""
    import cv2
    import numpy as np
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    # local threshold: some pages are collages of strips with different paper / scan backgrounds
    ink = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 41, 15)
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    h, w = ink.shape
    raw = (ink > 0).sum(axis=1).astype(float)
    if gray.std() < 3 or raw.max() < max(3.0, 0.005 * w):      # a blank sheet
        return []
    centred = raw - raw.mean()
    # line pitch: the autocorrelation peak of the ink profile, searched only between 1.5 and 4 x the median height of the
    # connected ink blobs (letters / letter groups); a free search locks onto 2-3 lines or onto single strokes
    n, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    hs = stats[1:, cv2.CC_STAT_HEIGHT] if n > 1 else np.array([])
    hs = hs[(hs >= 5) & (hs < h / 3)]
    hm = float(np.median(hs)) if hs.size else 20.0
    sm = np.convolve(centred, np.ones(5) / 5, mode="same")
    ac = np.correlate(sm, sm, mode="full")[h - 1:]
    lo, hi = max(8, int(1.5 * hm)), min(h // 2, int(4 * hm) + 1)
    pitch = int(lo + np.argmax(ac[lo:hi])) if hi > lo + 1 else max(12, int(2.5 * hm))
    pitch = max(pitch, 12)
    k = max(3, pitch // 4) | 1
    prof = np.convolve(raw, np.ones(k) / k, mode="same")
    p90 = np.percentile(prof[prof > 0], 90) if (prof > 0).any() else 0
    cuts = [0]
    y = 0
    while y < h:
        a, b = y + pitch // 2, min(h, y + int(1.5 * pitch))
        if a >= h:
            break
        seg = prof[a:b]
        c = a + int(np.argmin(seg))
        cuts.append(c)
        y = c
    if cuts[-1] < h:
        cuts.append(h)
    crops = []
    for y0, y1 in zip(cuts, cuts[1:]):
        if y1 - y0 < 4 or prof[y0:y1].max() < 0.25 * p90:      # empty band
            continue
        rows = np.where(raw[y0:y1] > 0)[0]
        a, b = y0 + rows[0], y0 + rows[-1] + 1
        cols = np.where((ink[a:b] > 0).any(axis=0))[0]
        if cols.size == 0 or b - a < 0.3 * pitch:
            continue
        x0, x1 = max(0, cols[0] - 4), min(w, cols[-1] + 5)
        crops.append(gray[max(0, a - 3):min(h, b + 3), x0:x1])
    return crops


# ---------------------------------------------------------------------------------------------------------- engines
def run_vietocr(rows):
    import psutil
    from PIL import Image
    from vietocr.tool.config import Cfg
    from vietocr.tool.predictor import Predictor
    cfg = Cfg.load_config_from_name("vgg_transformer")
    cfg["weights"] = str(WEIGHTS)
    cfg["device"] = "cpu"
    cfg["predictor"]["beamsearch"] = False
    cfg["cnn"]["pretrained"] = False      # the ImageNet backbone is overwritten by the weights file anyway; no download
    t0 = time.perf_counter()
    model = Predictor(cfg)
    load_s = time.perf_counter() - t0
    proc = psutil.Process()
    peak = proc.memory_info().rss
    out_dir = OUT / "vietocr"
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = [(r["id"], load_gray(PAGES / r["file"]), r["label"], "page") for r in rows] + list(special_pages(rows))
    results = []
    for pid, gray, ref, kind in pages:
        t = time.perf_counter()
        crops = split_lines(gray)
        texts = [model.predict(Image.fromarray(c).convert("RGB")) for c in crops]
        sec = time.perf_counter() - t
        peak = max(peak, proc.memory_info().rss)
        hyp = "\n".join(texts)
        (out_dir / f"{pid}.txt").write_text(hyp, encoding="utf-8")
        results.append({"id": pid, "kind": kind, "seconds": round(sec, 2), "lines": len(crops),
                        "ref_lines": None, "chars": len(norm(hyp))})
        print(pid, kind, len(crops), "lines", f"{sec:.1f}s", flush=True)
    (out_dir / "run.json").write_text(json.dumps({"load_seconds": round(load_s, 1), "peak_rss_mb": round(peak / 2**20),
                                                  "pages": results}, ensure_ascii=False, indent=1), encoding="utf-8")


def _key() -> tuple[str, str]:
    env = {}
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    key, model = env.get("GEMINI_API_KEY"), env.get("GEMINI_MODEL")
    if not key or not model:
        sys.exit("GEMINI_API_KEY / GEMINI_MODEL missing in BE/.env")
    return key, model


def run_gemini(rows):
    import cv2
    key, model = _key()
    out_dir = OUT / "gemini"
    out_dir.mkdir(parents=True, exist_ok=True)
    calls_file = out_dir / "calls.json"
    calls = json.loads(calls_file.read_text()) if calls_file.exists() else {"calls": 0, "model": model}
    run_file = out_dir / "run.json"
    results = {p["id"]: p for p in (json.loads(run_file.read_text(encoding="utf-8"))["pages"] if run_file.exists() else [])}
    pages = [(r["id"], PAGES / r["file"], None, "page") for r in rows] + list(special_pages(rows))
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    for pid, src, ref, kind in pages:
        if (out_dir / f"{pid}.txt").exists():
            continue
        if isinstance(src, Path):
            jpg = src.read_bytes()
        else:
            ok, buf = cv2.imencode(".jpg", src, [cv2.IMWRITE_JPEG_QUALITY, 90])
            jpg = buf.tobytes()
        body = {"contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpg).decode()}}, {"text": PROMPT}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 4096}}
        data, err, t = None, None, time.perf_counter()
        for attempt in range(3):
            if calls["calls"] >= MAX_GEMINI_CALLS:
                sys.exit(f"stopped: {MAX_GEMINI_CALLS} calls used (owner limit E-b)")
            calls["calls"] += 1
            calls_file.write_text(json.dumps(calls))
            req = urllib.request.Request(url, json.dumps(body).encode(), {"x-goog-api-key": key,
                                                                           "content-type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read())
                break
            except urllib.error.HTTPError as exc:
                err = f"HTTP {exc.code}"
                if exc.code not in (429, 500, 503):
                    break
                time.sleep(10 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError) as exc:
                err = type(exc).__name__
                time.sleep(10 * (attempt + 1))
        sec = time.perf_counter() - t
        if data is None:
            print(pid, "FAILED", err, flush=True)
            results[pid] = {"id": pid, "kind": kind, "error": err}
        else:
            cand = (data.get("candidates") or [{}])[0]
            text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
            u = data.get("usageMetadata") or {}
            (out_dir / f"{pid}.txt").write_text(text.strip(), encoding="utf-8")
            results[pid] = {"id": pid, "kind": kind, "seconds": round(sec, 2), "finish": cand.get("finishReason"),
                            "prompt_tokens": u.get("promptTokenCount"),
                            "output_tokens": (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0),
                            "chars": len(norm(text))}
            print(pid, kind, f"{sec:.1f}s", results[pid]["output_tokens"], "tokens", flush=True)
        run_file.write_text(json.dumps({"model": model, "pages": list(results.values())}, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print("calls used:", calls["calls"])


# ---------------------------------------------------------------------------------------------------------- report
def _q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else float("nan")


def evaluate(engine: str, rows) -> dict:
    labels = {r["id"]: r["label"] for r in rows}
    run = json.loads((OUT / engine / "run.json").read_text(encoding="utf-8"))
    per = []
    for p in run["pages"]:
        f = OUT / engine / f"{p['id']}.txt"
        hyp = f.read_text(encoding="utf-8") if f.exists() else None
        item = {**p, "hyp_chars": len(norm(hyp)) if hyp is not None else None}
        if p["kind"] == "page" and hyp is not None:
            item.update(scores(labels[p["id"]], hyp))
        if p["kind"] in ("blank", "noise") and hyp is not None:
            item["text"] = norm(hyp)[:120]
        if p["kind"] == "masked" and hyp is not None:
            full = OUT / engine / f"{p['id'].split('_')[1]}.txt"
            item["full_chars"] = (len(norm(full.read_text(encoding="utf-8"))) or None) if full.exists() else None
            item.update(scores(labels[int(p["id"].split("_")[1])], hyp))
        per.append(item)
    return {"run": run, "pages": per}


def report(rows):
    engines = [e for e in ("vietocr", "gemini") if (OUT / e / "run.json").exists()]
    res = {e: evaluate(e, rows) for e in engines}
    (OUT / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# V2 Phase E phần 1: đo nhận dạng chữ viết tay tiếng Việt (HTR) (2026-11-19)", "",
         "- Dữ liệu: 50 trang viết tay công khai của U3 (`5CD-AI/Viet-Handwriting-gemini-VQA`, gốc UIT-HWDB), đáp án = "
         "`label` do người gõ. Ảnh và kết quả từng trang ở `benchmarks/data/` (không commit, giấy phép chưa rõ).",
         "- Đo lại: `scripts/benchmark_htr.py` (xem docstring). Máy: máy phát triển Windows, CPU 16 luồng, không GPU.",
         "- CER / WER `exact`: chuẩn NFC, gộp khoảng trắng. `loose`: thêm chữ thường, bỏ dấu câu (dấu thanh giữ nguyên). "
         "`[?]` (chỗ mô hình báo không đọc được) được bỏ trước khi so, nên vẫn tính là thiếu chữ.", ""]
    L += ["## Tổng hợp (50 trang)", "", "| Engine | CER exact (trung vị) | CER exact P90 | WER exact (trung vị) | "
          "CER loose (trung vị) | WER loose (trung vị) | chèn thừa / ký tự (trung vị) | giây / trang (trung vị) | ghi chú |",
          "|---|---|---|---|---|---|---|---|---|"]
    for e in engines:
        pages = [p for p in res[e]["pages"] if p["kind"] == "page" and "exact" in p]
        ce = [p["exact"]["cer"] for p in pages]
        note = ""
        if e == "vietocr":
            note = (f"nạp mô hình {res[e]['run']['load_seconds']} s, RAM tối đa {res[e]['run']['peak_rss_mb']} MB, "
                    f"dòng tách trung vị {_q([p['lines'] for p in pages], .5)}")
        else:
            tin = sum(p.get("prompt_tokens") or 0 for p in res[e]["pages"])
            tout = sum(p.get("output_tokens") or 0 for p in res[e]["pages"])
            calls = json.loads((OUT / e / "calls.json").read_text())["calls"]
            fails = sum(1 for p in res[e]["pages"] if p.get("error"))
            recit = [str(p["id"]) for p in res[e]["pages"] if p.get("finish") == "RECITATION"]
            note = (f"mô hình `{res[e]['run']['model']}`, {calls} lượt gọi, {tin} token vào, {tout} token ra, lỗi {fails}, "
                    f"bị chặn RECITATION (trả rỗng, tính CER 1): {', '.join(recit) or 'không'}")
        L.append(f"| {e} | {_q(ce, .5):.3f} | {_q(ce, .9):.3f} | {_q([p['exact']['wer'] for p in pages], .5):.3f} | "
                 f"{_q([p['loose']['cer'] for p in pages], .5):.3f} | {_q([p['loose']['wer'] for p in pages], .5):.3f} | "
                 f"{_q([p['exact']['ins_per_char'] for p in pages], .5):.3f} | "
                 f"{_q([p['seconds'] for p in pages if p.get('seconds') is not None], .5):.1f} | {note} ({len(pages)}/50 trang) |")
    L += ["", "## Kiểm tra bịa chữ (Test 5)", "", "| Engine | Trang | Kết quả | Ghi chú |", "|---|---|---|---|"]
    for e in engines:
        for p in res[e]["pages"]:
            if p["kind"] in ("blank", "noise"):
                L.append(f"| {e} | {p['id']} | {p.get('hyp_chars')} ký tự | `{(p.get('text') or '')[:80]}` |")
            elif p["kind"] == "masked":
                ratio = f"{p['hyp_chars'] / p['full_chars']:.2f}" if p.get("full_chars") else "– (bản không che rỗng)"
                L.append(f"| {e} | {p['id']} (che 1/3 giữa trang) | {p.get('hyp_chars')} ký tự = {ratio} × bản không che "
                         f"| CER so với cả đáp án {p['exact']['cer']:.3f}, `[?]` {p['unknown_marks']} |")
    L += ["", "## Từng trang", "", "| id | " + " | ".join(f"{e} CER | {e} WER" for e in engines) + " |",
          "|---|" + "---|---|" * len(engines)]
    by = {e: {p["id"]: p for p in res[e]["pages"] if p["kind"] == "page"} for e in engines}
    for r in rows:
        cells = []
        for e in engines:
            p = by[e].get(r["id"], {})
            cells.append(f"{p['exact']['cer']:.3f} | {p['exact']['wer']:.3f}" if "exact" in p else "– | –")
        L.append(f"| {r['id']} | " + " | ".join(cells) + " |")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(L) + "\n"
    old = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    if "\n## Đọc kết quả" in old:                  # the hand-written reading of the numbers survives a rerun
        reading = "\n## Đọc kết quả" + old.split("\n## Đọc kết quả", 1)[1].split("\n## Kiểm tra bịa chữ", 1)[0]
        text = text.replace("\n## Kiểm tra bịa chữ", reading.rstrip("\n") + "\n\n## Kiểm tra bịa chữ", 1)
    REPORT.write_text(text, encoding="utf-8")
    print("wrote", REPORT)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["vietocr", "gemini"])
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="first N pages only (smoke test)")
    a = ap.parse_args()
    rows = manifest()
    if a.limit:
        rows = rows[:a.limit]
    if a.engine == "vietocr":
        run_vietocr(rows)
    elif a.engine == "gemini":
        run_gemini(rows)
    if a.report:
        report(rows)


if __name__ == "__main__":
    main()
