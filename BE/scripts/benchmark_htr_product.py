"""V2 Phase I2 (owner approved 2026-11-20): read 5 public pages through the PRODUCT code path (app.services.ai.htr:
page_jpeg -> read_page with the configured readers -> htr_align.match on the regions of the real recovery), not the E1 script.

Pages: the 5 held-out pages judged by eye in E2a (941, 503, 705, 347, 111), public UIT-HWDB pages, never a customer photo.
Each page is read once per configured reader (a reader is called on its own, so a reader that fails is recorded, not skipped).
Raw answers are kept in benchmarks/data/htr_product/ (not committed); a page already there is not read again.
Writes docs/benchmarks/I2_htr_product_2026-11-20.md.
    .venv/Scripts/python.exe scripts/benchmark_htr_product.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "scripts"))

from benchmark_htr import PAGES, manifest, scores          # noqa: E402
from benchmark_htr_align import regions_of                  # noqa: E402
from app.services.ai import htr                             # noqa: E402
from app.services.ai.llm import ProviderError               # noqa: E402
from app.services.stroke_ai import htr_align                # noqa: E402

PAGE_IDS = ["941", "503", "705", "347", "111"]
OUT = BASE / "benchmarks" / "data" / "htr_product"
E1 = BASE / "benchmarks" / "data" / "htr" / "gemini"
REPORT = BASE / "docs" / "benchmarks" / "I2_htr_product_2026-11-20.md"


def read_all() -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = {str(r["id"]): r for r in manifest()}
    readers = htr.configured_readers()
    results = []
    for pid in PAGE_IDS:
        r = rows[pid]
        data = (PAGES / r["file"]).read_bytes()
        jpeg = htr.page_jpeg(data)
        regs = regions_of(data)
        for rd in readers:
            f = OUT / f"{pid}_{rd.name}.json"
            if f.exists():
                rec = json.loads(f.read_text(encoding="utf-8"))
            else:
                t0 = time.perf_counter()
                try:
                    t = rd.read(jpeg)
                    rec = {"ok": True, "model": t.model, "finish": t.finish, "text": t.text, "in": t.input_tokens,
                           "out": t.output_tokens}
                except ProviderError as exc:
                    rec = {"ok": False, "model": rd.model, "reason": exc.reason, "status": exc.status}
                rec["seconds"] = round(time.perf_counter() - t0, 1)
                rec["jpeg_bytes"] = len(jpeg)
                f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            item = {"page": pid, "reader": rd.name, **{k: rec.get(k) for k in ("ok", "model", "finish", "reason", "status",
                                                                                  "seconds", "in", "out")}}
            if rec.get("ok"):
                s = scores(r["label"], rec["text"])
                m = htr_align.match(regs, rec["text"])
                item.update(cer=round(s["exact"]["cer"], 4), wer=round(s["exact"]["wer"], 4),
                            cer_loose=round(s["loose"]["cer"], 4), unknown=s["unknown_marks"], regions=len(regs),
                            read=sum(v["status"] == "READ" for v in m["regions"].values()), refused=m["refused"])
                e1 = E1 / f"{pid}.txt"
                if e1.exists():
                    item["e1_cer"] = round(scores(r["label"], e1.read_text(encoding="utf-8"))["exact"]["cer"], 4)
            results.append(item)
            print(item, flush=True)
    return results


def report(results: list[dict]) -> None:
    ok = [x for x in results if x.get("ok")]
    L = ["# V2 Phase I2: đọc chữ viết tay qua code sản phẩm (2026-11-20)", "",
         "Câu hỏi: đường đọc chữ của sản phẩm (`app/services/ai/htr.py`: `page_jpeg` → bên đọc đã cấu hình; rồi "
         "`htr_align.match` trên vùng của bộ phục dựng thật) có chạy thật và cho kết quả như lúc đo ở E1 / E2a không. "
         "5 trang công khai UIT-HWDB (5 trang đã chấm bằng mắt ở E2a, không dùng để chỉnh bộ gắn), không có ảnh khách.", "",
         "Chỉ số: CER / WER so với nhãn người của bộ dữ liệu (chuẩn hoá như E1, `exact`), số vùng nhận gợi ý (READ) / tổng "
         "vùng, và chặn của Phase I (`TOO_MANY_WORDS`). Câu trả lời thô lưu ở `benchmarks/data/htr_product/` (không commit).", "",
         "| Trang | Bên đọc | Mô hình | Kết thúc | Giây | Token vào / ra | CER | WER | CER E1 | Vùng READ / tổng | Chặn |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in results:
        if x.get("ok"):
            L.append(f"| {x['page']} | {x['reader']} | {x['model']} | {x['finish']} | {x['seconds']} | {x['in']} / {x['out']} | "
                     f"{x['cer']:.3f} | {x['wer']:.3f} | {x.get('e1_cer', float('nan')):.3f} | {x['read']} / {x['regions']} | "
                     f"{x['refused'] or '-'} |")
        else:
            L.append(f"| {x['page']} | {x['reader']} | {x['model']} | LỖI {x.get('reason')} ({x.get('status')}) | "
                     f"{x.get('seconds')} | - | - | - | - | - | - |")
    if ok:
        L += ["", f"Trung bình trên {len(ok)} lượt đọc thành công: CER {sum(x['cer'] for x in ok) / len(ok):.3f}, "
                  f"WER {sum(x['wer'] for x in ok) / len(ok):.3f}; vùng READ "
                  f"{sum(x['read'] for x in ok)} / {sum(x['regions'] for x in ok)}."]
    L += ["", f"Lượt gọi thật: {sum(1 for x in results if x.get('seconds') is not None)} (mỗi trang × mỗi bên đọc có khoá)."]
    names = {x["reader"] for x in results}
    if "anthropic" not in names:
        L += ["", "**Claude chưa đo:** máy chạy không có `ANTHROPIC_API_KEY` (không tự tạo khoá). Đường dự phòng Claude chỉ được "
                  "kiểm bằng `httpx.MockTransport` trong `tests/test_v2_htr_hints.py`, chưa gọi thật."]
    L += ["", "Bộ gắn chữ là bản có chặn `TOO_MANY_WORDS` của Phase I; trên 5 trang này chặn không bật (trang thật có tối đa "
              "1,22 chữ / vùng mực trên 48 trang của E2a, ngưỡng là 1,5)."]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    report(read_all())
