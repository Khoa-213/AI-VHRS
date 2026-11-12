"""U7 benchmark: pen-up travel before / after word-cluster ordering (app/services/stroke_ai/path_order.py).

Usage (from BE/):  .venv/Scripts/python scripts/benchmark_path_order.py [--images benchmarks/data/viet_hw] [--limit 50]

* OT-1: every image in the folder (the U3 set, not in git) through recovery, regions as clusters;
* OT-3: fixed Vietnamese texts with the bundled Hershey fonts, several sizes / alignments, one with a drawing.
For each page it checks that the result keeps every stroke exactly once, keeps every word whole and in its own order,
and changes no point of a stroke that was not reversed; then reports travel (mm, exact on the paper) and the time it
saves under trajectory.TRAVEL_SPEED_MM_S (an ASSUMED pen-up speed, not measured on the robot).
"""
from __future__ import annotations

import argparse
import copy
import statistics
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from app.services.motion import plan as mp  # noqa: E402
from app.services.stroke_ai import path_order, recovery, text_to_stroke  # noqa: E402
from app.services.stroke_ai.trajectory import TRAVEL_SPEED_MM_S, Page, Stroke  # noqa: E402

TEXTS = [
    ("thiep-ngan", "Chúc mừng năm mới", "hershey:scripts", 10, "CENTER", "A6"),
    ("loi-chuc", "Kính gửi quý khách hàng thân mến, chúc mừng năm mới an khang thịnh vượng vạn sự như ý", "hershey:scripts", 8, "CENTER", "A5"),
    ("thu-a5", "Gửi bạn, đã lâu không gặp. Mình viết vài dòng hỏi thăm sức khoẻ của bạn và gia đình. Mong mọi điều tốt đẹp sẽ đến với bạn trong năm nay. Thân mến.", "hershey:scripts", 7, "LEFT", "A5"),
    ("thu-a4-deu", "Hà Nội, ngày mười hai tháng mười một. Kính thưa thầy cô, em xin gửi lời cảm ơn chân thành vì những năm tháng thầy cô đã dạy dỗ. Những bài học hôm ấy em vẫn còn nhớ mãi và luôn mang theo trên mỗi chặng đường. Chúc thầy cô luôn mạnh khoẻ, hạnh phúc.", "hershey:futural", 6, "JUSTIFY", "A4"),
    ("chu-lon", "Yêu thương trọn vẹn", "hershey:futural", 18, "CENTER", "A4"),
]


def check(before: list[Stroke], after: list[Stroke], res: path_order.OrderResult) -> list[str]:
    errs = []
    if sorted(res.order) != list(range(len(before))):
        errs.append("strokes lost or duplicated")
    for new, old in enumerate(res.order):
        want = list(reversed(before[old].points)) if old in res.reversed else before[old].points
        if after[new].points != want:
            errs.append(f"stroke {old} changed")
            break
        if old in res.reversed and before[old].group is not None:
            errs.append(f"word stroke {old} reversed")
    groups: dict[int, list[int]] = {}
    for new, old in enumerate(res.order):
        if before[old].group is not None:
            groups.setdefault(before[old].group, []).append((new, old))
    for g, items in groups.items():
        pos = [p for p, _ in items]
        if pos != list(range(pos[0], pos[0] + len(pos))) or [o for _, o in items] != sorted(o for _, o in items):
            errs.append(f"word {g} split or reordered")
            break
    return errs


def run_page(name: str, kind: str, strokes: list[Stroke]) -> dict:
    t = time.perf_counter()
    nn = path_order.optimise(strokes, time_budget_s=0)
    res = path_order.optimise(strokes)
    dt = time.perf_counter() - t
    after = path_order.apply(strokes, res.order, res.reversed)
    return {"name": name, "kind": kind, "strokes": len(strokes), "clusters": res.clusters, "before": res.travel_before_mm,
            "nn": nn.travel_after_mm, "after": res.travel_after_mm, "reversed": len(res.reversed), "ms": dt * 1000,
            "errors": check(strokes, after, res)}


DEMO = dict(v_max=40.0, a_lat=2000.0, a_tan=1000.0)     # robot_agent DEMO_CFG / test values: NOT measured on the FR3


def jerk_rows(pages: list[tuple[str, list[Stroke]]]) -> list[str]:
    """Writing time with and without the opt-in jerk limit (motion/plan.py), simulated with the demo values."""
    strokes = [mp.resample_stroke(s.points, mp.DEFAULT_DS_MM) for _, ss in pages for s in ss if len(s.points) >= 2]
    strokes = [p for p in strokes if len(p) >= 3]
    base = [mp.speed_profile(p, **DEMO) for p in strokes]
    t0 = sum(mp.duration_s(p, v) for p, v in zip(strokes, base))
    j0 = max(float(np.abs(mp.jerk_of(p, v)).max()) for p, v in zip(strokes, base))
    out = ["## Giới hạn jerk (tuỳ chọn, mô phỏng)", "",
           f"{len(strokes)} nét viết của {len(pages)} trang, thông số mẫu v_max {DEMO['v_max']:g} mm/s, a_lat {DEMO['a_lat']:g}, "
           f"a_tan {DEMO['a_tan']:g} mm/s² (giá trị demo của `robot_agent`, **chưa đo trên FR3**). Thời gian = chỉ phần bút chạm giấy; "
           "jerk tính rời rạc giữa các điểm cách 0,2 mm.", "",
           "| j_max (mm/s³) | Jerk lớn nhất | Thời gian viết (s) | Tăng | Tính (s) |", "|---|---|---|---|---|",
           f"| tắt | {j0:,.0f} | {t0:.1f} | – | – |"]
    for j in (100000.0, 50000.0, 20000.0):
        t = time.perf_counter()
        vs = [mp.speed_profile(p, **DEMO, j_max=j) for p in strokes]
        dt = time.perf_counter() - t
        tj = sum(mp.duration_s(p, v) for p, v in zip(strokes, vs))
        jm = max(float(np.abs(mp.jerk_of(p, v)).max()) for p, v in zip(strokes, vs))
        out.append(f"| {j:,.0f} | {jm:,.0f} | {tj:.1f} | {100 * (tj - t0) / t0:+.1f}% | {dt:.1f} |")
    return out + [""]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default="benchmarks/data/viet_hw")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--out", default=f"docs/benchmarks/U7_path_order_{date.today().isoformat()}.md")
    a = ap.parse_args()
    rows = []
    for name, text, font, size, align, paper in TEXTS:
        pages = text_to_stroke.compose_text(text, font_name=text_to_stroke.font_name_from_uri(font), source=None,
                                            paper_size=paper, font_size_mm=size, alignment=align, seed=7)
        for i, p in enumerate(pages, 1):
            rows.append(run_page(f"{name} p{i}", "OT-3", p.strokes))
    drawing = copy.deepcopy(text_to_stroke.compose_text("Thương tặng mẹ", font_name="scripts", source=None, paper_size="A5",
                                                         font_size_mm=10, alignment="CENTER", seed=3)[0])
    for k in range(8):                       # a customer drawing: short free strokes scattered under the text
        x = 20 + (k * 37) % 110
        drawing.strokes.append(Stroke([(x, 120 + k * 6), (x + 12, 124 + k * 6)], "canvas"))
    rows.append(run_page("loi-tang + hinh ve", "OT-3", drawing.strokes))
    jerk_pages = [(n, text_to_stroke.compose_text(t, font_name=text_to_stroke.font_name_from_uri(f), source=None, paper_size=pp,
                                                  font_size_mm=sz, alignment=al, seed=7)[0].strokes) for n, t, f, sz, al, pp in TEXTS]
    imgs = sorted(Path(a.images).glob("*.jpg"))[: a.limit] if Path(a.images).exists() else []
    for f in imgs:
        page, st = recovery.recover_page(f.read_bytes(), paper_size="A4")
        for r in st.regions:
            for s in page.strokes[r.stroke_start:r.stroke_end]:
                s.group = r.region_no
        rows.append(run_page(f.name, "OT-1", page.strokes))

    bad = [r for r in rows if r["errors"]]
    lines = [f"# U7: thứ tự nét và quãng nhấc bút ({date.today().isoformat()})", "",
             f"Lệnh: `.venv/Scripts/python scripts/benchmark_path_order.py` ({len(imgs)} ảnh OT-1 trong `{a.images}`, "
             f"{len(rows) - len(imgs)} trang OT-3). Quãng nhấc bút = tổng khoảng cách thẳng trên giấy từ cuối nét này tới đầu nét kế "
             "(cùng số với `trajectory.compute_metrics`), **không** phải mô phỏng robot. Thời gian tiết kiệm tính theo tốc độ "
             f"nhấc bút giả định {TRAVEL_SPEED_MM_S:g} mm/s (`TRAVEL_SPEED_MM_S`, chưa đo trên robot).", "",
             f"Kiểm tra toàn vẹn (đủ nét, mỗi từ liền và giữ thứ tự, nét không đảo thì không đổi điểm): "
             f"**{len(rows) - len(bad)}/{len(rows)} trang đạt**" + (f"; lỗi: {[(r['name'], r['errors']) for r in bad]}" if bad else "."), ""]
    for kind in ("OT-1", "OT-3"):
        rs = [r for r in rows if r["kind"] == kind]
        if not rs:
            continue
        gain = [100 * (r["before"] - r["after"]) / r["before"] for r in rs if r["before"] > 0]
        nn_gain = [100 * (r["before"] - r["nn"]) / r["before"] for r in rs if r["before"] > 0]
        saved = [(r["before"] - r["after"]) / TRAVEL_SPEED_MM_S for r in rs]
        lines += [f"## {kind} ({len(rs)} trang)", "",
                  "| Chỉ số | Trung vị | Nhỏ nhất | Lớn nhất |", "|---|---|---|---|",
                  f"| Quãng nhấc bút giảm (%), NN + 2-opt | {statistics.median(gain):.1f} | {min(gain):.1f} | {max(gain):.1f} |",
                  f"| Quãng nhấc bút giảm (%), chỉ NN | {statistics.median(nn_gain):.1f} | {min(nn_gain):.1f} | {max(nn_gain):.1f} |",
                  f"| Thời gian nhấc bút bớt được (s, giả định) | {statistics.median(saved):.1f} | {min(saved):.1f} | {max(saved):.1f} |",
                  f"| Số cụm (từ) | {statistics.median(r['clusters'] for r in rs):.0f} | {min(r['clusters'] for r in rs)} | {max(r['clusters'] for r in rs)} |",
                  f"| Thời gian chạy bộ tối ưu (ms) | {statistics.median(r['ms'] for r in rs):.0f} | {min(r['ms'] for r in rs):.0f} | {max(r['ms'] for r in rs):.0f} |", "",
                  f"Tổng: {sum(r['before'] for r in rs):,.0f} mm → {sum(r['after'] for r in rs):,.0f} mm.", ""]
    lines += jerk_rows(jerk_pages)
    lines += ["## Từng trang OT-3", "", "| Trang | Nét | Cụm | Trước (mm) | Sau (mm) | Giảm | Nét đảo chiều |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["kind"] == "OT-3":
            lines.append(f"| {r['name']} | {r['strokes']} | {r['clusters']} | {r['before']:.0f} | {r['after']:.0f} | "
                         f"{100 * (r['before'] - r['after']) / max(r['before'], 1e-9):.1f}% | {r['reversed']} |")
    lines += ["", "## Giới hạn", "",
              "- Chỉ đổi thứ tự **giữa các từ**; quãng nhấc bút **trong một từ** (giữa các nét của chữ, tới dấu thanh) giữ nguyên "
              "vì đó là thứ tự viết, và chiếm phần lớn quãng còn lại.",
              "- Với OT-3 robot có thể viết các từ không theo thứ tự đọc (kết quả trên giấy giống hệt).",
              "- Thời gian thật phụ thuộc tốc độ nhấc bút, thời gian hạ / nhấc bút và gia tốc của robot: phải đo trên FR3 (HW).",
              "- Giới hạn jerk chỉ đo được trên mô phỏng: có giảm rung, có làm nét đẹp hơn hay không phải thử trên robot thật."]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")                # Windows consoles default to cp1252
    print("\n".join(lines[:8]))
    print("wrote", out)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
