"""V2 Phase E2a, method B (owner, 2026-11-19): page transcript (E1 Gemini, cached, no new call) + local word -> U4 region
matching (`scripts/htr_align.py`). Writes `docs/benchmarks/E2a_htr_regions_2026-11-19.md`.

Measured with no ground truth per region:
* coverage: share of regions READ / UNREAD on the 50 pages, time of recovery + matching;
* hallucination: the blank and noise pages of E1 must give 0 READ regions; on the 5 pages with the middle third hidden,
  each READ region is compared with the region at the same place on the full page (same recovery, full transcript):
  a different word there is a word moved onto the wrong ink.
Measured by eye (the only per-region truth there is): `JUDGED` below, filled from check sheets (each READ group drawn on
the page with its word) by the AI, not by a person. Pages 884 / 42 / 119 were used to tune the matcher, so only the
held-out pages (drawn at random before looking, seeds 20261119 / 20261120) count for the E2-e gate (<= 5 % wrong).
Method A (Gemini reads numbered boxes; 3-page pilot, results in benchmarks/data/htr_regions) is summarised for context.
    .venv/Scripts/python.exe scripts/benchmark_htr_align.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import cv2

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "scripts"))

import htr_align                                              # noqa: E402
from app.core.errors import AppError                          # noqa: E402
from app.services.stroke_ai import recovery                   # noqa: E402
from benchmark_htr import _q, manifest, special_pages        # noqa: E402

PAGES = BASE / "benchmarks" / "data" / "viet_hw"
E1 = BASE / "benchmarks" / "data" / "htr" / "gemini"
A_RES = BASE / "benchmarks" / "data" / "htr_regions" / "results.json"
REPORT = BASE / "docs" / "benchmarks" / "E2a_htr_regions_2026-11-19.md"
PAPER, MARGIN = "A4", 10.0
REFUSED: dict[int, str] = {}

# page: (READ regions, wrong READ regions, what went wrong) - judged by eye on the check sheets, matcher sha256 below
TUNING = ("884", "42", "119")
JUDGED = {
    "941": (107, 2, "một vùng rộng chứa 4 chữ \"xác đến từng chi\": chữ \"chính\" bị bỏ, 2 vùng nhận chữ lệch"),
    "503": (35, 0, ""),
    "705": (136, 15, "dòng cuối viết chèn sát bên dưới (\"địa này, anh à.\") bị gộp vào dòng trên, cả dòng lệch"),
    "347": (109, 0, ""),
    "111": (118, 0, ""),
    "1223": (107, 7, "một dòng dốc lên bị tách đôi; \"không\" bị bỏ, 7 vùng ở cuối dòng 1 / đầu dòng 2 lệch"),
}
FROZEN_SHA = "569a42ab841b813beb8411495f98a9a9f00706c42d03de804054a2e3a1ad6ec8"     # the matcher the pages were judged with
# Two fixes came after, both from the hidden-band pages: "[?]" / "..." are holes, not words (no change on the 6 pages),
# and two lines at the same local height are merged (changed 9 regions of 1223 only; those were judged again).
JUDGED_SHA = "5c117ff36503ad1bd62f1c6e63057048f17113572fcdbde5b746b263dc87cd27"   # app copy (E2b), same outputs as 8051c2bd… (scripts/)
JUDGED_AFTER = {"1223": (109, 0, "dòng dốc lên nay là một dòng; 9 vùng đổi chữ đều đúng")}


def regions_of(data: bytes):
    try:
        _, st = recovery.recover_page(data, paper_size=PAPER, margin_mm=MARGIN)
    except AppError as exc:                       # blank / noise page: the product refuses it before any reading
        if exc.code not in ("NO_STROKES_FOUND", "IMAGE_TOO_NOISY"):
            raise
        REFUSED[id(data)] = exc.code
        return []
    return st.regions


def png(gray) -> bytes:
    return cv2.imencode(".png", gray)[1].tobytes()


def run():
    rows = manifest()
    pages = []
    full = {}
    for r in rows:
        pid = str(r["id"])
        data = (PAGES / r["file"]).read_bytes()
        t0 = time.perf_counter()
        regs = regions_of(data)
        t1 = time.perf_counter()
        text = (E1 / f"{pid}.txt").read_text(encoding="utf-8") if (E1 / f"{pid}.txt").exists() else ""
        res = htr_align.match(regs, text)
        t2 = time.perf_counter()
        R = res["regions"]
        full[pid] = (regs, R)
        pages.append({"id": pid, "regions": len(R), "read": sum(v["status"] == "READ" for v in R.values()),
                      "empty_text": not text.strip(), "recover_s": round(t1 - t0, 2), "match_s": round(t2 - t1, 3)})
        print(pid, pages[-1], flush=True)
    special = []
    for name, gray, _, kind in special_pages(rows):
        img = png(gray)
        regs = regions_of(img)
        text = (E1 / f"{name}.txt").read_text(encoding="utf-8") if (E1 / f"{name}.txt").exists() else ""
        R = htr_align.match(regs, text)["regions"]
        item = {"name": name, "kind": kind, "regions": len(R), "read": sum(v["status"] == "READ" for v in R.values()),
                "refused": REFUSED.get(id(img))}
        if kind == "masked":
            fregs, fR = full[name.split("_", 1)[1]]
            same = diff = unmatched = 0
            examples = []
            for g in regs:
                v = R[g.region_no]
                if v["status"] != "READ":
                    continue
                cx, cy = (g.bbox[0] + g.bbox[2]) / 2, (g.bbox[1] + g.bbox[3]) / 2
                best = min(fregs, key=lambda f: abs((f.bbox[0] + f.bbox[2]) / 2 - cx) + abs((f.bbox[1] + f.bbox[3]) / 2 - cy))
                d = abs((best.bbox[0] + best.bbox[2]) / 2 - cx) + abs((best.bbox[1] + best.bbox[3]) / 2 - cy)
                fv = fR[best.region_no]
                if d > 1.0 or fv["status"] != "READ":
                    unmatched += 1
                elif fv["text"] == v["text"]:
                    same += 1
                else:
                    diff += 1
                    if len(examples) < 4:
                        examples.append(f"{fv['text']} → {v['text']}")
            item.update(same=same, diff=diff, unmatched=unmatched, examples=examples)
        special.append(item)
        print(item, flush=True)
    return pages, special


def report(pages, special):
    sha = hashlib.sha256((BASE / "app" / "services" / "stroke_ai" / "htr_align.py").read_bytes()).hexdigest()
    held = {k: v for k, v in JUDGED.items() if k not in TUNING}
    hr, hw = sum(v[0] for v in held.values()), sum(v[1] for v in held.values())
    after = {**held, **JUDGED_AFTER}
    ar, aw = sum(v[0] for v in after.values()), sum(v[1] for v in after.values())
    regs = sum(p["regions"] for p in pages)
    read = sum(p["read"] for p in pages)
    ok_pages = [p for p in pages if not p["empty_text"]]
    noise = [s for s in special if s["kind"] in ("blank", "noise")]
    masked = [s for s in special if s["kind"] == "masked"]
    a = json.loads(A_RES.read_text(encoding="utf-8")) if A_RES.exists() else None
    L = ["# V2 Phase E2a: gắn chữ cho từng vùng U4 (2026-11-19)", "",
         "Câu hỏi của E2-e: gắn chữ đọc được vào từng vùng U4 của trang OT-1 có đủ đúng không (≤ 5 % vùng sai, không vùng "
         "nào bị bịa chữ). 50 trang công khai của U3 (như `E_htr_benchmark_2026-11-19.md`), vùng do bộ phục dựng thật tính "
         "(A4, lề 10 mm).", "",
         "## Cách A (bỏ): Gemini đọc từng khung đánh số", "",
         "Khung + số của từng vùng vẽ lên ảnh, Gemini trả JSON {số khung: chữ}. Thử 3 trang (884, 42, 119), 10 lượt gọi "
         "(`scripts/benchmark_htr_regions.py`). Gemini đọc đúng **thứ tự** chữ nhưng **gán nhầm khung**: U4 hay cắt một từ "
         "thành hai vùng (\"h\" + \"ỏi\", \"th\" + \"ành\"), Gemini lại đặt cả từ vào một khung rồi trượt sang khung sau "
         "(trang 884 dòng 2: từ khung 28 trở đi lệch 1–2 khung), có từ bị chép vào hai khung. Đo theo dóng hàng từ đã ra "
         + (f"{sum(p['wrong'] for p in a['pages'])}/{sum(p['read'] for p in a['pages'])} vùng sai" if a else "10,5 % vùng sai")
         + ", và cách đo đó còn không thấy lỗi lệch khung, nên số thật cao hơn. Khung giả trên dải bị che: 0/15 bị điền "
         "chữ. Không chạy tiếp 47 trang còn lại.", "",
         "## Cách B (đang đề xuất): đọc cả trang, gắn chữ vào vùng trên máy", "",
         "- Bản chép cả trang: kết quả Gemini của E1 (đã có, **không gọi thêm lượt nào**).",
         "- Gắn chữ: `app/services/stroke_ai/htr_align.py` (lúc đo nằm ở `scripts/htr_align.py`; Python thuần, không thêm thư viện). Vùng → dòng (theo dõi dòng chạy xiên, đuôi "
         "chữ \"g\" / \"y\" về đúng dòng) → đơn vị (vùng chồng nhau như dấu trên chữ là một) → quy hoạch động khớp từng từ với "
         "1–4 đơn vị liền nhau theo độ rộng chữ dự kiến, cho phép bỏ vùng nhiễu / từ không có mực; đầu dòng của bản chép "
         "phải rơi vào đầu dòng mực. Từ khớp kém hoặc bản chép ghi `[?]` → vùng **UNREAD** (không đoán).",
         f"- Bộ gắn chữ được chỉnh trên 3 trang 884, 42, 119; sau đó **đóng băng** (sha256 `{FROZEN_SHA[:12]}…`) rồi mới bốc "
         "ngẫu nhiên 6 trang khác để soát. Hai sửa đổi sau đó đều do trang bị che lộ ra: `[?]` / `...` là chỗ trống chứ "
         "không phải một từ (6 trang không đổi vùng nào), và hai \"dòng\" cùng độ cao tại chỗ là một dòng (chỉ đổi 9 vùng "
         f"của trang 1223, đã soát lại). Bản hiện tại `{JUDGED_SHA[:12]}…`.", "",
         "### Đúng / sai theo từng vùng (soát bằng mắt, trang chưa dùng để chỉnh)", "",
         "Không có đáp án theo vùng nên mỗi trang được vẽ thành bảng kiểm (khung từng nhóm vùng + chữ được gắn) và soát "
         "từng nhóm. **Người soát là AI (Claude), không phải người**; chỉ tính lỗi gắn sai chỗ và vùng nhận thiếu / thừa chữ, "
         "không tính lỗi chính tả do Gemini đọc sai một chữ (đã đo ở E1, CER 0,024).", "",
         "| Trang | Vùng READ | Vùng sai | Ghi chú |", "|---|---|---|---|"]
    for k, (r, w, note) in held.items():
        L.append(f"| {k} | {r} | {w} ({w / max(1, r):.1%}) | {note or '–'} |")
    L += [f"| **Tổng 6 trang, bản đóng băng** | **{hr}** | **{hw} = {hw / max(1, hr):.1%}** | ngưỡng E2-e ≤ 5 %; số dùng để "
          "so ngưỡng |",
          f"| Tổng 6 trang, bản hiện tại | {ar} | {aw} = {aw / max(1, ar):.1%} | 1223: {JUDGED_AFTER['1223'][2]}; sửa sau khi "
          "đã thấy trang nên không dùng số này để so ngưỡng |", "",
          "### Phủ vùng và thời gian (50 trang, không cần đáp án)", "",
          "| Chỉ số | Giá trị |", "|---|---|",
          f"| Vùng READ / tổng | {read}/{regs} = {read / max(1, regs):.1%} |",
          f"| Trang không có bản chép (Gemini chặn `RECITATION`) → toàn bộ UNREAD | "
          f"{', '.join(p['id'] for p in pages if p['empty_text']) or 'không'} |",
          f"| Vùng READ trên trang có bản chép, trung vị / thấp nhất | "
          f"{_q([p['read'] / max(1, p['regions']) for p in ok_pages], .5):.1%} / "
          f"{min(p['read'] / max(1, p['regions']) for p in ok_pages):.1%} |",
          f"| Thời gian gắn chữ / trang, trung vị / lớn nhất | {_q([p['match_s'] for p in pages], .5):.2f} s / "
          f"{max(p['match_s'] for p in pages):.2f} s (phục dựng: {_q([p['recover_s'] for p in pages], .5):.1f} s) |", "",
          "### Bịa chữ (Test 5)", "",
          "| Trang | Vùng | READ | Ghi chú |", "|---|---|---|---|"]
    for s in noise:
        L.append(f"| {s['name']} | {s['regions']} | {s['read']} | bản chép E1 là `[?]`"
                 + (f"; phục dựng từ chối ảnh (`{s['refused']}`)" if s['refused'] else "") + " |")
    for s in masked:
        L.append(f"| {s['name']} (che 1/3 giữa) | {s['regions']} | {s['read']} | so với cùng chỗ trên trang đủ: "
                 f"{s['same']} giống, **{s['diff']} khác**, {s['unmatched']} không so được"
                 + (f"; ví dụ {'; '.join(s['examples'])}" if s["examples"] else "") + " |")
    L += ["", "Cách B không tự sinh chữ: chữ chỉ đến từ bản chép cả trang; vùng không có chữ tương ứng thì UNREAD. Bịa chữ "
          "chỉ có thể đến từ bản chép, và E1 không thấy Gemini điền phần bị che (5 trang) hay chép chữ từ trang trắng / "
          "nhiễu. Trên trang bị che, một vùng nhận chữ khác với trang đủ là từ bị đặt nhầm chỗ, không phải chữ bịa.", "",
          "## Đọc kết quả", "", "(viết tay sau khi chạy)", ""]
    text = "\n".join(L)
    old = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    if "\n## Đọc kết quả" in old and "(viết tay sau khi chạy)" not in old.split("\n## Đọc kết quả", 1)[1][:60]:
        text = text.split("\n## Đọc kết quả")[0] + "\n## Đọc kết quả" + old.split("\n## Đọc kết quả", 1)[1]
    REPORT.write_text(text, encoding="utf-8")
    if sha != JUDGED_SHA:
        print("WARNING: htr_align.py changed since the pages were judged; the by-eye table is stale")
    print("wrote", REPORT)


def main():
    pages, special = run()
    out = BASE / "benchmarks" / "data" / "htr_align"
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps({"pages": pages, "special": special}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    report(pages, special)


if __name__ == "__main__":
    main()
