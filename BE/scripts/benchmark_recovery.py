"""Upgrade U3: measure the OT-1 stroke recovery (+ U4 regions) on REAL Vietnamese handwriting images.

Input: benchmarks/data/viet_hw/ (scripts/fetch_hf_handwriting.py; images never committed) with manifest.jsonl, whose
`label` is the text written in each image.

What can be measured honestly WITHOUT ground-truth pen trajectories (these images are photos / scans, nobody recorded
the pen):
  * robustness: does the recovery run, which error code, how long (NFR-01: OT-1 page <= 15 s);
  * ink fidelity: pixel IoU ink vs redrawn strokes (the existing `similarity`, NFR-02 asks >= 80);
  * topology: connected pieces of ink vs connected pieces of the redrawn strokes (a ratio far from 1 = strokes broken
    up or merged);
  * endpoints: free ends of the ink skeleton vs pen-down/pen-up points of the recovered strokes (far above 1 = the pen
    lifts much more often than the ink suggests);
  * words: U4 regions vs words of the reference text (1.0 = one region per word);
  * diacritics: strokes classed as marks vs tone/modifier marks in the reference text (a rough proxy, not a match);
  * U4 labels: share of RESTORED regions and the confidence distribution (input for calibrating the 0.6 threshold).
What CANNOT be measured here: stroke ORDER / DIRECTION accuracy (needs pen trajectories), CER / WER (there is no
handwriting recognition in the system yet), the look of the written result on paper (needs the robot).

    python scripts/benchmark_recovery.py                    # report to docs/benchmarks/, details + overlays to benchmarks/data/
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import cv2
import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from app.core.errors import AppError                                      # noqa: E402
from app.services.stroke_ai import recovery, regions as rg                 # noqa: E402
from app.services.stroke_ai.trajectory import PAPER_MM                    # noqa: E402

DATA = BASE / "benchmarks" / "data" / "viet_hw"
OVERLAYS = BASE / "benchmarks" / "data" / "overlays"
REPORTS = BASE / "docs" / "benchmarks"
PAPER = "A4"
MARGIN_MM = 10.0
DIACRITICS = {"̀", "́", "̃", "̉", "̣", "̂", "̆", "̛"}   # tones + â ă ơ/ư


def _ink(gray: np.ndarray) -> np.ndarray:
    """Same preprocessing as recovery.recover_page (no rotation / crop)."""
    scale = recovery.MAX_SIDE_PX / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ink = recovery._remove_specks(recovery._binarise(gray))
    ink, _ = recovery._deskew(ink)
    return recovery._remove_specks(ink)


def _components(mask: np.ndarray) -> int:
    return cv2.connectedComponents((mask > 0).astype(np.uint8), connectivity=8)[0] - 1


def _skeleton_ends(ink: np.ndarray) -> int:
    sk = recovery._drop_corner_pixels(recovery.zhang_suen(ink)).astype(np.uint8)
    n = cv2.filter2D(sk, -1, np.ones((3, 3), np.float32), borderType=cv2.BORDER_CONSTANT)
    return int(((sk > 0) & (n == 2)).sum())


def _diacritics(text: str) -> int:
    return sum(1 for ch in unicodedata.normalize("NFD", text) if ch in DIACRITICS)


def measure(m: dict) -> dict:
    data = (DATA / m["file"]).read_bytes()
    label = m.get("label") or ""
    out = {"id": m["id"], "chars": sum(1 for c in label if not c.isspace()), "words": len(label.split()),
           "diacritics": _diacritics(label)}
    t0 = time.perf_counter()
    try:
        page, st = recovery.recover_page(data, paper_size=PAPER, margin_mm=MARGIN_MM)
    except AppError as exc:
        out.update(ok=False, error=exc.code, seconds=round(time.perf_counter() - t0, 3))
        return out
    out["seconds"] = round(time.perf_counter() - t0, 3)

    gray = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    ink = _ink(gray)
    h, w = ink.shape
    s = st.mm_per_px
    pw, ph = PAPER_MM[PAPER]
    ox, oy = (pw - w * s) / 2, (ph - h * s) / 2
    thick = max(1, int(round(st.stroke_width_mm / s)))
    redraw = np.zeros_like(ink)
    for stroke in page.strokes:
        pts = np.array([((x - ox) / s, (y - oy) / s) for x, y in stroke.points])
        cv2.polylines(redraw, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], False, 255, thick)
    ink_comp, red_comp = _components(ink), _components(redraw)
    ends = _skeleton_ends(ink)
    marks = sum(1 for x in page.strokes if x.kind == "mark")
    labels = [r.label for r in st.regions]
    out.update(
        ok=True, similarity=st.similarity, strokes=len(page.strokes), strokes_per_char=round(len(page.strokes) / max(out["chars"], 1), 3),
        ink_components=ink_comp, stroke_components=red_comp, topology_ratio=round(red_comp / max(ink_comp, 1), 3),
        skeleton_ends=ends, pen_ends=2 * len(page.strokes), endpoint_ratio=round(2 * len(page.strokes) / max(ends, 1), 3),
        regions=len(st.regions), region_word_ratio=round(len(st.regions) / max(out["words"], 1), 3),
        mark_strokes=marks, mark_ratio=round(marks / max(out["diacritics"], 1), 3),
        restored=labels.count("RESTORED"), restored_share=round(labels.count("RESTORED") / max(len(labels), 1), 3),
        confidence=[r.confidence for r in st.regions], fit=[r.metrics["fit"] for r in st.regions],
        contrast=[r.metrics["contrast"] for r in st.regions], warnings=st.warnings)

    # overlay for a human check: green = ORIGINAL, orange = RESTORED
    vis = cv2.cvtColor(cv2.resize(gray, (w, h), interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
    for r in st.regions:
        x0, y0, x1, y1 = [int(round(v)) for v in ((r.bbox[0] - ox) / s, (r.bbox[1] - oy) / s,
                                                  (r.bbox[2] - ox) / s, (r.bbox[3] - oy) / s)]
        cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 160, 0) if r.label == "ORIGINAL" else (0, 140, 255), 2)
    OVERLAYS.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OVERLAYS / f"{m['id']:05d}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return out


FADE = 0.6          # share of the way from ink to paper colour inside the faded box


def measure_faded(m: dict, fade: float = FADE) -> dict | None:
    """Sensitivity check: wash out a box in the middle of a REAL image (ink moved FADE of the way to the paper colour),
    then count how many regions inside the box come out RESTORED (detected) and how many outside do (false alarms).
    Synthetic damage on real handwriting: it shows whether the labels react to fading, not how real damage looks."""
    gray = cv2.imdecode(np.frombuffer((DATA / m["file"]).read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
    H, W = gray.shape
    bx0, bx1, by0, by1 = int(W * 0.35), int(W * 0.65), int(H * 0.3), int(H * 0.7)
    paper = float(np.percentile(gray, 90))
    box = gray[by0:by1, bx0:bx1].astype(np.float32)
    gray[by0:by1, bx0:bx1] = np.clip(box + (paper - box) * fade, 0, 255).astype(np.uint8)
    try:
        page, st = recovery.recover_page(cv2.imencode(".png", gray)[1].tobytes(), paper_size=PAPER, margin_mm=MARGIN_MM)
    except AppError:
        return None
    scale = min(recovery.MAX_SIDE_PX / max(H, W), 1.0)
    w, h = int(round(W * scale)), int(round(H * scale))
    s = st.mm_per_px
    pw, ph = PAPER_MM[PAPER]
    ox, oy = (pw - w * s) / 2, (ph - h * s) / 2
    inside = outside = hit = false = 0
    for r in st.regions:
        cx = ((r.bbox[0] + r.bbox[2]) / 2 - ox) / s / scale
        cy = ((r.bbox[1] + r.bbox[3]) / 2 - oy) / s / scale
        if bx0 + 10 < cx < bx1 - 10 and by0 + 10 < cy < by1 - 10:
            inside += 1
            hit += r.label == "RESTORED"
        elif not (bx0 - 40 < cx < bx1 + 40 and by0 - 40 < cy < by1 + 40):
            outside += 1
            false += r.label == "RESTORED"
    return {"id": m["id"], "inside": inside, "detected": hit, "outside": outside, "false_alarms": false}


def _q(values: list[float], p: float) -> float:
    v = sorted(values)
    return v[min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))] if v else float("nan")


def summary_row(name: str, values: list[float], target: str = "") -> str:
    return (f"| {name} | {statistics.median(values):.3f} | {_q(values, 0.1):.3f} | {_q(values, 0.9):.3f} | "
            f"{min(values):.3f} | {max(values):.3f} | {target} |")


def main() -> None:
    manifest = [json.loads(x) for x in (DATA / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = []
    for i, m in enumerate(manifest, 1):
        rows.append(measure(m))
        r = rows[-1]
        print(f"{i:2d}/{len(manifest)} id={m['id']} " + (f"sim={r['similarity']} regions={r['regions']}/{r['words']} "
              f"t={r['seconds']}s" if r["ok"] else f"ERROR {r['error']}"))
    (BASE / "benchmarks" / "data" / "recovery_results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                                                        encoding="utf-8")
    ok = [r for r in rows if r["ok"]]
    faded, base_inside = [], 0
    for m in manifest:
        f, b = measure_faded(m), measure_faded(m, 0.0)
        if f and b:
            faded.append(f)
            base_inside += b["inside"]
    (BASE / "benchmarks" / "data" / "faded_results.json").write_text(json.dumps(faded, indent=1), encoding="utf-8")
    f_in, f_hit = sum(f["inside"] for f in faded), sum(f["detected"] for f in faded)
    f_out, f_false = sum(f["outside"] for f in faded), sum(f["false_alarms"] for f in faded)
    conf = [c for r in ok for c in r["confidence"]]
    fit = [c for r in ok for c in r["fit"]]
    contrast = [c for r in ok for c in r["contrast"]]
    today = date.today().isoformat()
    lines = [
        f"# U3: đo phục dựng OT-1 trên ảnh chữ viết tay tiếng Việt thật ({today})",
        "",
        f"- Dữ liệu: {len(rows)} ảnh lấy đều từ `5CD-AI/Viet-Handwriting-gemini-VQA` (gốc UIT-HWDB + Cinnamon AI Challenge), "
        "danh sách mã ảnh ở bảng cuối; ảnh **không** nằm trong repo (giấy phép chưa rõ, chỉ dùng đo nội bộ). "
        "Tải lại bằng `scripts/fetch_hf_handwriting.py`, đo lại bằng `scripts/benchmark_recovery.py`.",
        f"- Cấu hình: khổ {PAPER}, lề {MARGIN_MM:.0f} mm, engine `zhang-suen-skeleton` + vùng U4 (ngưỡng {rg.UNCERTAIN_BELOW}). "
        "Máy đo: máy phát triển Windows của dự án (CPU, không GPU).",
        "- **Không đo được ở đây:** độ đúng thứ tự / chiều nét (ảnh không có quỹ đạo bút gốc), CER / WER (hệ thống chưa có "
        "nhận dạng chữ), chất lượng nét trên giấy thật (cần robot).",
        "",
        "## Kết quả",
        "",
        f"- Chạy được: **{len(ok)}/{len(rows)}** ảnh. Lỗi: "
        + (", ".join(f"`{r['error']}` (id {r['id']})" for r in rows if not r["ok"]) or "không có") + ".",
        f"- Thời gian mỗi ảnh: trung vị {statistics.median([r['seconds'] for r in rows]):.2f} s, "
        f"lớn nhất {max(r['seconds'] for r in rows):.2f} s (NFR-01: ≤ 15 s mỗi trang OT-1).",
        f"- `similarity` ≥ 80 (mục tiêu NFR-02): **{sum(1 for r in ok if r['similarity'] >= 80)}/{len(ok)}** ảnh.",
        f"- Vùng U4: {sum(r['regions'] for r in ok)} vùng, RESTORED {sum(r['restored'] for r in ok)} "
        f"({100 * sum(r['restored'] for r in ok) / max(sum(r['regions'] for r in ok), 1):.1f}%).",
        f"- Thử độ nhạy (mực mờ nhân tạo trên ảnh thật, {len(faded)} ảnh: hộp giữa ảnh 30% × 40%, mực bị kéo {FADE:.0%} về màu "
        f"giấy): vùng trong hộp bị gắn RESTORED **{f_hit}/{f_in} ({100 * f_hit / max(f_in, 1):.1f}%)**; vùng ngoài hộp bị "
        f"gắn nhầm {f_false}/{f_out} ({100 * f_false / max(f_out, 1):.1f}%). Cùng hộp đó trên ảnh gốc có {base_inside} vùng: "
        f"**{max(base_inside - f_in, 0)} vùng ({100 * max(base_inside - f_in, 0) / max(base_inside, 1):.0f}%) biến mất hẳn** khi mực "
        "mờ (bị coi là nền, không có nét nên không có vùng để gắn nhãn). Đây là hư hại giả lập, không thay được ảnh hư hại thật.",
        "",
        "| Chỉ số | Trung vị | P10 | P90 | Nhỏ nhất | Lớn nhất | Ý nghĩa / mục tiêu |",
        "|---|---|---|---|---|---|---|",
        summary_row("similarity (IoU mực / nét, %)", [r["similarity"] for r in ok], "NFR-02 ≥ 80"),
        summary_row("topology_ratio (mảnh nét / mảnh mực)", [r["topology_ratio"] for r in ok], "gần 1"),
        summary_row("endpoint_ratio (đầu nét / đầu khung xương)", [r["endpoint_ratio"] for r in ok], "gần 1; > 1 = nhấc bút thừa"),
        summary_row("strokes_per_char", [r["strokes_per_char"] for r in ok], "tham khảo"),
        summary_row("region_word_ratio (vùng / từ)", [r["region_word_ratio"] for r in ok], "gần 1"),
        summary_row("mark_ratio (nét dấu / dấu trong văn bản)", [r["mark_ratio"] for r in ok], "gần 1 (thô)"),
        summary_row("confidence vùng", conf, f"< {rg.UNCERTAIN_BELOW} → RESTORED"),
        summary_row("fit vùng", fit, "IoU cục bộ"),
        summary_row("contrast vùng", contrast, "độ đậm so với trang"),
        summary_row("giây / ảnh", [r["seconds"] for r in rows], "NFR-01 ≤ 15"),
        "",
        "## Đọc kết quả và các thay đổi đã làm theo số đo",
        "",
        "- **`similarity` không đạt 80 trên ảnh thật nào, nhưng không vì nét sai:** mọi ảnh nằm trong khoảng hẹp 62–69 kể cả "
        "ảnh rất sạch, trong khi `topology_ratio` ~0,9 và `endpoint_ratio` ~1,3 cho thấy nét bám đúng mực. Cách đo vẽ lại nét "
        "với **một độ dày đều** rồi so điểm ảnh với mực thật (dày mỏng, nhoè mép), nên có trần thấp. Kết luận: chỉ số này không "
        "dùng được làm ngưỡng NFR-02 cho ảnh thật; cần chỉ số khác (ví dụ so khung xương với khung xương, hoặc đo trên quỹ đạo "
        "bút thật). Cảnh báo `SIMILARITY_BELOW_80` vì vậy bật cho **mọi** ảnh thật; chủ dự án quyết **tạm tắt** (2026-11-12) đến khi có cách đo tốt hơn.",
        "- **Đã đổi (U4):** lần đo đầu, ngưỡng tuyệt đối 0,6 trên `fit` gắn RESTORED cho **13,4%** vùng của ảnh sạch (báo động "
        "giả). Nay `fit` được so với trung vị của chính trang (`fit_rel`), giống cách `contrast` đã làm: còn 0,1%.",
        "- **Đã đổi (phục dựng):** lần đo đầu, hộp mực mờ nhân tạo làm **91% vùng biến mất hẳn**, không cảnh báo (Otsu coi "
        "mực nhạt là nền). Đây là lỗi im lặng, trái chế độ FAITHFUL. Nay `_binarise` thêm ngưỡng thứ hai (nửa đường giữa Otsu "
        "và màu giấy) cho các mảnh mực nhạt không chạm mực đậm, đủ lớn và mảnh như nét bút: không vùng nào biến mất, 96,9% "
        "được gắn RESTORED, ảnh sạch không đổi.",
        "- `region_word_ratio` ~1,19: vùng U4 hay tách một từ viết tay thành 2 (khoảng hở trong từ), đôi khi gộp. Chấp nhận "
        "được cho việc sửa theo vùng; chưa sửa.",
        "- `endpoint_ratio` ~1,3: robot nhấc bút nhiều hơn mức mực gợi ý khoảng 30% (nét bị cắt ở chỗ giao nhau). Ảnh hưởng "
        "thời gian viết, chưa ảnh hưởng hình chữ; cần đo trên robot thật.",
        "",
        "## Từng ảnh",
        "",
        "| id | ok | similarity | strokes | topology | endpoint | vùng / từ | RESTORED | giây |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["ok"]:
            lines.append(f"| {r['id']} | có | {r['similarity']} | {r['strokes']} | {r['topology_ratio']} | "
                         f"{r['endpoint_ratio']} | {r['regions']} / {r['words']} | {r['restored']} | {r['seconds']} |")
        else:
            lines.append(f"| {r['id']} | `{r['error']}` | | | | | | | {r['seconds']} |")
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"U3_recovery_viet_hw_{today}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report -> {path}")


if __name__ == "__main__":
    main()
