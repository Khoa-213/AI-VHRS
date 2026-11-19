"""V2 Phase E2a (owner, 2026-11-19): can Gemini read the text of each U4 region (one region ~ one word) of an OT-1 page?

Before any product code: the U4 regions of the 50 public U3 pages are computed by the real recovery (`recovery.recover_page`,
as the product does), their boxes are drawn and numbered on the page image, and Gemini answers JSON
{"<region number>": "<text>" | "[?]"}. Measured:
* page CER / WER of the region texts joined in region order (the order the product would show), against the human label;
* wrong regions: a region whose text is not matched to the label by a word alignment (difflib on loose-normalised words)
  and is not "[?]" - a proxy for "this region got the wrong text" (there is no per-word ground truth); gate E2-e: <= 5 %;
* hallucination (Test 5): on 5 pages a white band hides the middle third and 5 fake, empty boxes are drawn on it; any text
  returned for a fake box is a made-up word; gate E2-e: 0.
Max 100 calls (cached per page). Run with the BE venv (OpenCV + the app's recovery):
    .venv/Scripts/python.exe scripts/benchmark_htr_regions.py            # calls Gemini (cached), then writes the report
    .venv/Scripts/python.exe scripts/benchmark_htr_regions.py --report   # report only
"""
from __future__ import annotations

import argparse
import base64
import difflib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "scripts"))

from app.services.stroke_ai import recovery                    # noqa: E402
from app.services.stroke_ai.trajectory import PAPER_MM          # noqa: E402
from benchmark_htr import _key, _q, edit_ops, manifest, norm   # noqa: E402

PAGES = BASE / "benchmarks" / "data" / "viet_hw"
OUT = BASE / "benchmarks" / "data" / "htr_regions"
REPORT = BASE / "docs" / "benchmarks" / "E2a_htr_regions_2026-11-19.md"
PAPER, MARGIN = "A4", 10.0
MAX_CALLS = 100
MASKED, FAKE = 5, 5

PROMPT = ("Ảnh là một trang chữ viết tay tiếng Việt. Mỗi khung màu đỏ có số là một vùng (thường là một từ). Với MỖI số, "
          "chép NGUYÊN VĂN chữ viết tay nằm trong khung đó (giữ dấu, dấu câu dính liền). Không sửa chính tả, không đoán. "
          "Khung không có chữ, hoặc chữ không đọc được, thì ghi \"[?]\". Không được lấy chữ ở khung khác hay đoán theo "
          "ngữ cảnh. Chỉ trả về một đối tượng JSON {\"số khung\": \"chữ\"} cho tất cả các khung, không giải thích.")


def page_frame(data: bytes):
    """The image as the recovery sees it (resized, deskewed) and the mm -> px mapping of its strokes / regions."""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    scale = recovery.MAX_SIDE_PX / max(img.shape)
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    h, w = img.shape
    _, angle = recovery._deskew(recovery._remove_specks(recovery._binarise(img)))
    if angle:
        rot = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        img = cv2.warpAffine(img, rot, (w, h), flags=cv2.INTER_LINEAR, borderValue=255)
    pw, ph = PAPER_MM[PAPER]
    s = min((pw - 2 * MARGIN) / w, (ph - 2 * MARGIN) / h)
    ox, oy = (pw - w * s) / 2, (ph - h * s) / 2
    return img, (lambda x, y: ((x - ox) / s, (y - oy) / s))


def boxes_for(data: bytes):
    page, st = recovery.recover_page(data, paper_size=PAPER, margin_mm=MARGIN)
    img, to_px = page_frame(data)
    out = []
    for r in st.regions:
        x0, y0 = to_px(r.bbox[0], r.bbox[1])
        x1, y1 = to_px(r.bbox[2], r.bbox[3])
        out.append({"no": r.region_no, "box": [int(x0) - 2, int(y0) - 2, int(x1) + 3, int(y1) + 3], "label": r.label})
    return img, out


def draw(img, boxes):
    col = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    for b in boxes:
        x0, y0, x1, y1 = b["box"]
        cv2.rectangle(col, (x0, y0), (x1, y1), (0, 0, 220), 1)
        cv2.putText(col, str(b["no"]), (x0, max(10, y0 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 220), 1, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", col, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return buf.tobytes()


def masked(img, boxes):
    """Hide the middle third and put FAKE empty boxes on the white band (numbers after the real ones)."""
    g = img.copy()
    h, w = g.shape
    g[h // 3: 2 * h // 3, :] = 255
    keep = [b for b in boxes if b["box"][3] < h // 3 or b["box"][1] > 2 * h // 3]
    n = max([b["no"] for b in boxes] + [0])
    fakes = [{"no": n + i + 1, "box": [int(w * (0.1 + 0.16 * i)), h // 2 - 15, int(w * (0.1 + 0.16 * i)) + 120, h // 2 + 15],
              "label": "FAKE"} for i in range(FAKE)]
    return g, keep + fakes


def call(key, model, jpg, calls):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"role": "user", "parts": [
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpg).decode()}}, {"text": PROMPT}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 8192, "responseMimeType": "application/json"}}
    err = None
    for attempt in range(3):
        if calls["calls"] >= MAX_CALLS:
            sys.exit(f"stopped: {MAX_CALLS} calls used")
        calls["calls"] += 1
        (OUT / "calls.json").write_text(json.dumps(calls))
        req = urllib.request.Request(url, json.dumps(body).encode(), {"x-goog-api-key": key, "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read()), None
        except urllib.error.HTTPError as exc:
            err = f"HTTP {exc.code}"
            if exc.code not in (429, 500, 503):
                break
        except (urllib.error.URLError, TimeoutError) as exc:
            err = type(exc).__name__
        time.sleep(10 * (attempt + 1))
    return None, err


def run(rows):
    OUT.mkdir(parents=True, exist_ok=True)
    key, model = _key()
    cf = OUT / "calls.json"
    calls = json.loads(cf.read_text()) if cf.exists() else {"calls": 0, "model": model}
    jobs = []
    for r in rows:
        jobs.append((str(r["id"]), r, False))
    for r in rows[:MASKED]:
        jobs.append((f"masked_{r['id']}", r, True))
    for pid, r, is_masked in jobs:
        f = OUT / f"{pid}.json"
        if f.exists():
            continue
        data = (PAGES / r["file"]).read_bytes()
        t = time.perf_counter()
        img, boxes = boxes_for(data)
        if is_masked:
            img, boxes = masked(img, boxes)
        jpg = draw(img, boxes)
        resp, err = call(key, model, jpg, calls)
        sec = time.perf_counter() - t
        rec = {"id": pid, "boxes": boxes, "seconds": round(sec, 2), "error": err}
        if resp is not None:
            cand = (resp.get("candidates") or [{}])[0]
            text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
            u = resp.get("usageMetadata") or {}
            rec.update(finish=cand.get("finishReason"), raw=text, prompt_tokens=u.get("promptTokenCount"),
                       output_tokens=(u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0))
        f.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        print(pid, len(boxes), "boxes", f"{sec:.1f}s", rec.get("finish"), err or "", flush=True)
    print("calls used:", calls["calls"])


def parse(raw: str | None) -> dict[int, str] | None:
    if not raw:
        return None
    s = raw.strip().strip("`")
    if s.startswith("json"):
        s = s[4:]
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    out = {}
    for k, v in obj.items():
        try:
            out[int(k)] = str(v).strip()
        except (TypeError, ValueError):
            continue
    return out


def evaluate(rows):
    labels = {str(r["id"]): r["label"] for r in rows}
    res = {"pages": [], "masked": []}
    for r in rows:
        f = OUT / f"{r['id']}.json"
        if not f.exists():
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))
        texts = parse(rec.get("raw"))
        nos = [b["no"] for b in rec["boxes"]]
        item = {"id": r["id"], "regions": len(nos), "finish": rec.get("finish"), "error": rec.get("error"),
                "parsed": texts is not None, "seconds": rec["seconds"], "prompt_tokens": rec.get("prompt_tokens"),
                "output_tokens": rec.get("output_tokens")}
        texts = texts or {}
        unread = [n for n in nos if texts.get(n, "[?]") in ("", "[?]")]
        extra = [k for k in texts if k not in nos]
        joined = " ".join(texts.get(n, "") for n in nos if texts.get(n, "[?]") not in ("", "[?]"))
        ref = norm(labels[str(r["id"])])
        c = edit_ops(list(ref), list(norm(joined)))
        w = edit_ops(ref.split(), norm(joined).split())
        # wrong regions: align region words to label words (loose); a read region whose words are not all matched
        lw = norm(labels[str(r["id"])], True).split()
        toks = [(n, t) for n in nos if texts.get(n, "[?]") not in ("", "[?]") for t in norm(texts[n], True).split()]
        ok = set()
        for a, b, size in difflib.SequenceMatcher(None, lw, [t for _, t in toks], autojunk=False).get_matching_blocks():
            ok.update(range(b, b + size))
        bad = {toks[i][0] for i in range(len(toks)) if i not in ok}
        read = [n for n in nos if n not in unread]
        item.update(cer=c["dist"] / max(1, c["ref"]), wer=w["dist"] / max(1, w["ref"]), unread=len(unread),
                    read=len(read), wrong=len(bad), extra_keys=len(extra),
                    restored=sum(1 for b in rec["boxes"] if b["label"] != "ORIGINAL"))
        res["pages"].append(item)
    for r in rows[:MASKED]:
        f = OUT / f"masked_{r['id']}.json"
        if not f.exists():
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))
        texts = parse(rec.get("raw")) or {}
        fakes = [b["no"] for b in rec["boxes"] if b["label"] == "FAKE"]
        made_up = {n: texts[n] for n in fakes if texts.get(n, "[?]") not in ("", "[?]")}
        res["masked"].append({"id": r["id"], "fake_boxes": len(fakes), "made_up": made_up, "finish": rec.get("finish"),
                              "parsed": bool(texts)})
    return res


def report(rows):
    res = evaluate(rows)
    (OUT / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    P = res["pages"]
    calls = json.loads((OUT / "calls.json").read_text())
    read = sum(p["read"] for p in P)
    wrong = sum(p["wrong"] for p in P)
    regions = sum(p["regions"] for p in P)
    unread = sum(p["unread"] for p in P)
    made = sum(len(m["made_up"]) for m in res["masked"])
    fakes = sum(m["fake_boxes"] for m in res["masked"])
    L = ["# V2 Phase E2a: Gemini đọc chữ theo từng vùng U4 (2026-11-19)", "",
         "- Dữ liệu: 50 trang công khai của U3 (như `E_htr_benchmark_2026-11-19.md`). Vùng = vùng U4 do bộ phục dựng thật "
         "tính (A4, lề 10 mm), khung + số vẽ lên ảnh đã chỉnh nghiêng, Gemini trả JSON {số vùng: chữ | \"[?]\"}.",
         f"- Mô hình `{calls['model']}`, {calls['calls']} lượt gọi. Script: `scripts/benchmark_htr_regions.py`.",
         "- \"Vùng sai\" = vùng đọc ra chữ nhưng chữ đó không khớp đáp án khi dóng hàng từ (difflib, bỏ hoa thường và dấu "
         "câu). Không có đáp án theo từng từ nên đây là ước lượng; vùng U4 hay tách một từ làm hai (U3: 1,19 vùng / từ), "
         "nửa từ cũng tính là sai.", "",
         "## Tổng hợp", "",
         f"| Chỉ số | Giá trị | Ngưỡng E2-e |", "|---|---|---|",
         f"| Trang trả JSON đọc được | {sum(1 for p in P if p['parsed'])}/{len(P)} | |",
         f"| Bị chặn `RECITATION` / lỗi | {sum(1 for p in P if p['finish'] == 'RECITATION')} / "
         f"{sum(1 for p in P if p['error'])} | |",
         f"| Vùng | {regions} (RESTORED {sum(p['restored'] for p in P)}) | |",
         f"| Vùng không đọc (`[?]`, rỗng, thiếu) | {unread} ({unread / max(1, regions):.1%}) | |",
         f"| **Vùng sai** / vùng đọc ra chữ | **{wrong}/{read} = {wrong / max(1, read):.1%}** | ≤ 5 % |",
         f"| **Khung giả (vùng trống) bị điền chữ** | **{made}/{fakes}** | 0 |",
         f"| CER trang (ghép chữ các vùng), trung vị / P90 | {_q([p['cer'] for p in P], .5):.3f} / {_q([p['cer'] for p in P], .9):.3f} | |",
         f"| WER trang, trung vị | {_q([p['wer'] for p in P], .5):.3f} | |",
         f"| Giây / trang (phục dựng + gọi), trung vị | {_q([p['seconds'] for p in P], .5):.1f} | |",
         f"| Token vào / ra (tổng) | {sum(p['prompt_tokens'] or 0 for p in P)} / {sum(p['output_tokens'] or 0 for p in P)} | |",
         "", "## Khung giả trên dải bị che (Test 5)", "", "| Trang | Khung giả | Bị điền chữ |", "|---|---|---|"]
    for m in res["masked"]:
        L.append(f"| {m['id']} | {m['fake_boxes']} | {json.dumps(m['made_up'], ensure_ascii=False) if m['made_up'] else 'không'} |")
    L += ["", "## Từng trang", "", "| id | vùng | không đọc | vùng sai | CER | WER | kết thúc |", "|---|---|---|---|---|---|---|"]
    for p in P:
        L.append(f"| {p['id']} | {p['regions']} | {p['unread']} | {p['wrong']} | {p['cer']:.3f} | {p['wer']:.3f} | "
                 f"{p['finish'] or p['error']} |")
    text = "\n".join(L) + "\n"
    old = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    if "\n## Đọc kết quả" in old:
        reading = "\n## Đọc kết quả" + old.split("\n## Đọc kết quả", 1)[1].split("\n## Khung giả", 1)[0]
        text = text.replace("\n## Khung giả", reading.rstrip("\n") + "\n\n## Khung giả", 1)
    REPORT.write_text(text, encoding="utf-8")
    print("wrote", REPORT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    rows = manifest()
    if a.limit:
        rows = rows[:a.limit]
    if not a.report:
        run(rows)
    report(rows)


if __name__ == "__main__":
    main()
