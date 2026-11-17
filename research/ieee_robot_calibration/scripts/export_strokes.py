"""Export the handwriting test set (paper-frame pen-down strokes, mm) using AI-VHRS's own OT-3 text-to-stroke composer.

Run with the BACKEND virtual environment (it has HersheyFonts); it only imports a pure function, touches no database:
    ../../BE/.venv/Scripts/python.exe scripts/export_strokes.py
Output: data/strokes.json (+ provenance). The Vietnamese samples are FONT-GENERATED single-line glyphs (Hershey 'scripts' plus
AI-VHRS's hand-designed diacritic strokes), not recorded human handwriting: there is no human ground-truth pen trajectory.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "BE"))

from app.services.stroke_ai.text_to_stroke import compose_text  # noqa: E402

FONT = "scripts"
PAGE_TEXT = ("Hệ thống tái tạo chữ viết tay tiếng Việt dùng robot cộng tác để viết thiệp, thư cảm ơn và lời chúc. "
             "Mỗi nét chữ được sinh từ phông chữ một nét, đặt lên trang giấy rồi chuyển thành quỹ đạo của đầu bút. "
             "Độ chính xác của robot quyết định nét chữ có đều, liền mạch và đúng vị trí hay không. "
             "Nghiên cứu này đánh giá hiệu chuẩn động học bằng các hốc cầu đơn giản và bù trước quỹ đạo.")


def text_strokes(text: str, size_mm: float, offset=(0.0, 0.0), seed: int = 0) -> list[list[list[float]]]:
    pages = compose_text(text, font_name=FONT, paper_size="A4", font_size_mm=size_mm, seed=seed)
    out = []
    for s in pages[0].strokes:
        if len(s.points) >= 2:
            out.append([[x + offset[0], y + offset[1]] for x, y in s.points])
    return out


def line(a, b):
    return [[list(map(float, a)), list(map(float, b))]]


def circle(c, r, n=None):
    n = n or max(16, int(2 * np.pi * r / 0.5))
    t = np.linspace(0, 2 * np.pi, n + 1)
    return [np.stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)], 1).tolist()]


def polyline(pts):
    return [[list(map(float, p)) for p in pts]]


def main() -> None:
    samples = {
        "line_h": {"category": "straight line", "source": "synthetic", "strokes": line((20, 40), (190, 40))},
        "line_v": {"category": "straight line", "source": "synthetic", "strokes": line((105, 20), (105, 277))},
        "line_d": {"category": "straight line", "source": "synthetic", "strokes": line((20, 20), (190, 277))},
        "circle_r5": {"category": "curve", "source": "synthetic",
                      "strokes": circle((40, 100), 5) + circle((170, 100), 5) + circle((40, 250), 5) + circle((170, 250), 5)},
        "circle_r80": {"category": "curve", "source": "synthetic", "strokes": circle((105, 150), 80)},
        "corners": {"category": "corner", "source": "synthetic",
                    "strokes": polyline([(45, 120), (165, 120), (165, 240), (45, 240), (45, 120)])
                    + polyline([(30, 60), (60, 90), (90, 60), (120, 90), (150, 60), (180, 90)])},
        "chars": {"category": "Vietnamese characters with diacritics", "source": "font (Hershey scripts + AI-VHRS marks)",
                  "text": "ắ ệ ợ ữ ỹ đ Ư ổ", "strokes": text_strokes("ắ ệ ợ ữ ỹ đ Ư ổ", 10.0, (0, 0))},
        "words": {"category": "Vietnamese words", "source": "font (Hershey scripts + AI-VHRS marks)",
                  "text": "Việt Nam  người  Hà Nội", "strokes": text_strokes("Việt Nam  người  Hà Nội", 9.0, (0, 110))},
        "sentence": {"category": "short sentence", "source": "font (Hershey scripts + AI-VHRS marks)",
                     "text": "Xin chào Việt Nam, chúc mừng năm mới!",
                     "strokes": text_strokes("Xin chào Việt Nam, chúc mừng năm mới!", 8.0, (0, 220))},
        "page": {"category": "full A4 page", "source": "font (Hershey scripts + AI-VHRS marks)", "text": PAGE_TEXT,
                 "strokes": text_strokes(PAGE_TEXT, 7.0, (0, 0), seed=1)},
    }
    for k, v in samples.items():
        pts = np.concatenate([np.array(s) for s in v["strokes"]])
        v["n_strokes"] = len(v["strokes"])
        v["length_mm"] = float(sum(np.sum(np.linalg.norm(np.diff(np.array(s), axis=0), axis=1)) for s in v["strokes"]))
        v["bbox_mm"] = [float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())]
        assert pts[:, 0].min() >= 0 and pts[:, 0].max() <= 210 and pts[:, 1].min() >= 0 and pts[:, 1].max() <= 297, k
    rev = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    src = (REPO / "BE" / "app" / "services" / "stroke_ai" / "text_to_stroke.py").read_bytes()
    out = {"provenance": {"generator": "BE/app/services/stroke_ai/text_to_stroke.py::compose_text", "font": f"hershey:{FONT}",
                          "git_head": rev, "generator_sha256": hashlib.sha256(src).hexdigest(),
                          "note": "font-generated and synthetic trajectories; no recorded human handwriting"},
           "paper": {"size": "A4", "width_mm": 210.0, "height_mm": 297.0, "frame": "origin top-left, x right, y down"},
           "samples": samples}
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "strokes.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")
    for k, v in samples.items():
        print(f"{k:12s} strokes={v['n_strokes']:4d} length={v['length_mm']:8.1f} mm bbox={np.round(v['bbox_mm'], 1).tolist()}")


if __name__ == "__main__":
    main()
