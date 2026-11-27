"""OT-2 Phase O2 (owner approved 2026-11-20, docs/OT2_LEARNED_STYLE_PLAN.md section 9): the handwriting sample sheet.

A fixed A4 sheet (SHEET_V1, 3 pages) with one box per character. The writer writes each printed character in the box
under it; because the character of every box is known, nothing has to be read by an AI and the photo never leaves the
server. Reading a photo of a page:
  1. find the four black corner squares, warp the page to the sheet's own millimetres (PX_PER_MM);
  2. check the page number printed as filled slots next to the header (a photo of page 2 sent as page 1 is refused);
  3. binarise the whole page once (the OT-1 binarisation), cut every box a little inside its printed border;
  4. trace the ink of each box with the OT-1 tracer (`recovery.trace`) and express it in x-height units from the box's
     printed baseline: x / XH_MM, (y - baseline) / XH_MM. Nothing is guessed about the writer's size.
A box is EMPTY (no ink), OVERFLOW (ink runs under the border, so the letter is cut) or OK. Carrier boxes (á à ả ã ạ ă â
ê ô) also give the mark alone: the marks are the pieces above the x-height band (or below the baseline for the dot) when
their count matches the marks the character needs; otherwise the box is MARKS_UNCLEAR. Nothing is repaired: flagged
boxes are shown to the Staff, who drop bad samples before approving the style.

The layout sizes are design values, not validated with real writers yet (the O2 measurement on real sheets does that).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from app.core.errors import AppError
from app.services import image_guard
from app.services.stroke_ai import recovery

SHEET_VERSION = "SHEET_V1"
PAGE_W, PAGE_H = 210.0, 297.0
PX_PER_MM = 10.0
MARK = 8.0                                  # corner square side (mm)
MARK_AT = ((8.0, 8.0), (PAGE_W - 16.0, 8.0), (8.0, PAGE_H - 16.0), (PAGE_W - 16.0, PAGE_H - 16.0))   # top-left corners
SLOT = 4.0                                  # page-number slots: page k fills slot k
SLOTS_AT = [(150.0 + 7.0 * i, 10.0) for i in range(3)]
BOX = 20.0                                  # writing box side (mm)
LABEL_H = 5.0                               # printed character above the box
COLS, ROWS = 8, 9
GRID_X0, GRID_Y0 = (PAGE_W - COLS * BOX - (COLS - 1) * 2.0) / 2, 30.0
COL_STEP, ROW_STEP = BOX + 2.0, BOX + LABEL_H + 2.0
BASELINE, XH_MM = 14.0, 6.0                 # baseline 14 mm below the box top; x-height 6 mm (ticks on both sides)
INSET = 1.2                                 # cut inside the printed border (mm)

TONES = {"̀": "grave", "́": "acute", "̉": "hook", "̃": "tilde", "̣": "dot_below"}
HATS = {"̆": "breve", "̂": "circumflex"}
MARK_NAMES = ("acute", "grave", "hook", "tilde", "dot_below", "breve", "circumflex")

LOWER = list("abcdefghijklmnopqrstuvwxyz") + ["ơ", "ư", "đ"]
UPPER = [c.upper() for c in LOWER]
DIGITS = list("0123456789")
PUNCT = list('.,?!:;-()"\'')
CARRIERS = ["á", "à", "ả", "ã", "ạ", "ă", "â", "ê", "ô"]


@dataclass(frozen=True)
class Cell:
    id: str          # "p1c07" (page, index on the page)
    page: int        # 1-based
    index: int       # 0-based on the page
    char: str
    x: float         # box top-left (mm)
    y: float


def _content() -> list[str]:
    return ([c for c in LOWER for _ in range(3)] + [c for c in UPPER for _ in range(2)] + [c for c in DIGITS for _ in range(2)]
            + PUNCT + [c for c in CARRIERS for _ in range(2)])


@lru_cache(maxsize=1)
def layout() -> tuple[Cell, ...]:
    per_page = COLS * ROWS
    cells = []
    for k, ch in enumerate(_content()):
        page, i = k // per_page + 1, k % per_page
        r, c = divmod(i, COLS)
        cells.append(Cell(f"p{page}c{i:02d}", page, i, ch, GRID_X0 + c * COL_STEP, GRID_Y0 + LABEL_H + r * ROW_STEP))
    return tuple(cells)


def pages() -> int:
    return max(c.page for c in layout())


def targets() -> list[str]:
    """What a complete style covers: every character of the sheet (carriers excluded) and every mark."""
    seen: list[str] = []
    for c in _content():
        if c not in CARRIERS and c not in seen:
            seen.append(c)
    return seen + list(MARK_NAMES)


def marks_of(ch: str) -> list[str]:
    d = unicodedata.normalize("NFD", ch)
    return [HATS[m] for m in d[1:] if m in HATS] + [TONES[m] for m in d[1:] if m in TONES]


# ---------------------------------------------------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------------------------------------------------
FONT = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "DejaVuSans.ttf"


def sheet_pdf() -> bytes:
    from fpdf import FPDF
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_font("dv", "", str(FONT))
    for p in range(1, pages() + 1):
        pdf.add_page()
        pdf.set_fill_color(0, 0, 0)
        for x, y in MARK_AT:
            pdf.rect(x, y, MARK, MARK, style="F")
        for i, (x, y) in enumerate(SLOTS_AT):
            pdf.set_draw_color(0, 0, 0)
            pdf.set_line_width(0.3)
            pdf.rect(x, y, SLOT, SLOT, style="F" if i + 1 == p else "D")
        pdf.set_font("dv", size=11)
        pdf.set_xy(20, 9)
        pdf.cell(120, 5, f"AI-VHRS - Phiếu mẫu chữ {SHEET_VERSION} - trang {p}/{pages()}")
        pdf.set_font("dv", size=7.5)
        pdf.set_xy(20, 15)
        pdf.multi_cell(170, 3.4, "Viết mỗi chữ in nhỏ vào ô bên dưới nó, bằng bút sẽ dùng thường ngày, cỡ chữ bình thường. "
                       "Chân chữ đặt ở vạch dưới, thân chữ thường cao tới vạch trên; nét không chạm viền ô. "
                       "Chụp thẳng cả trang, thấy đủ 4 ô vuông đen ở góc.")
        for cell in (c for c in layout() if c.page == p):
            pdf.set_font("dv", size=9)
            pdf.set_xy(cell.x, cell.y - LABEL_H)
            pdf.cell(BOX, LABEL_H - 0.5, cell.char, align="C")
            pdf.set_draw_color(150, 150, 150)
            pdf.set_line_width(0.25)
            pdf.rect(cell.x, cell.y, BOX, BOX)
            pdf.set_draw_color(0, 0, 0)
            for yy in (cell.y + BASELINE, cell.y + BASELINE - XH_MM):            # ticks outside the box only
                pdf.line(cell.x - 1.5, yy, cell.x, yy)
                pdf.line(cell.x + BOX, yy, cell.x + BOX + 1.5, yy)
    return bytes(pdf.output())


# ---------------------------------------------------------------------------------------------------------------------
# reading a photo
# ---------------------------------------------------------------------------------------------------------------------
def _corner_squares(gray: np.ndarray) -> np.ndarray | None:
    """Centres of the four corner squares (TL, TR, BL, BR) in image pixels, or None."""
    h, w = gray.shape
    _, bw = cv2.threshold(cv2.GaussianBlur(gray, (5, 5), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # RETR_LIST: a dark table / background around the paper must not swallow the squares as holes of one big contour
    contours, _ = cv2.findContours(bw, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cands = []
    for c in contours:
        a = cv2.contourArea(c)
        if a < 0.00004 * h * w or a > 0.01 * h * w:
            continue
        (cx, cy), (rw, rh), _ = cv2.minAreaRect(c)
        if min(rw, rh) <= 0 or max(rw, rh) / min(rw, rh) > 1.4 or a / (rw * rh) < 0.8:
            continue
        bx, by, bw_, bh_ = cv2.boundingRect(c)
        inner = bw[by + bh_ // 4:by + 3 * bh_ // 4, bx + bw_ // 4:bx + 3 * bw_ // 4]
        if inner.size == 0 or float(np.mean(inner > 0)) < 0.9:      # filled, not a printed box outline
            continue
        cands.append((cx, cy, a))
    if len(cands) < 4:
        return None
    pts = np.array([(x, y) for x, y, _ in cands], float)
    picks = [np.argmin(pts[:, 0] + pts[:, 1]), np.argmax(pts[:, 0] - pts[:, 1]),
             np.argmax(pts[:, 1] - pts[:, 0]), np.argmax(pts[:, 0] + pts[:, 1])]
    if len(set(int(i) for i in picks)) < 4:
        return None
    quad = pts[picks]
    areas = [cands[i][2] for i in picks]
    if max(areas) > 3 * min(areas):                     # four squares of one sheet are about the same size
        return None
    return quad


def warp(data: bytes) -> np.ndarray:
    img = image_guard.decode(data, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise AppError(422, "INVALID_IMAGE", "Không đọc được ảnh. Vui lòng tải lại file jpg/png.")
    scale = 2400 / max(img.shape)
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    quad = _corner_squares(img)
    if quad is None:
        raise AppError(422, "SHEET_CORNERS_NOT_FOUND",
                       "Không thấy đủ 4 ô vuông đen ở góc phiếu. Hãy chụp thẳng cả trang, đủ sáng, không che góc.")
    dst = np.array([(x + MARK / 2, y + MARK / 2) for x, y in MARK_AT], float) * PX_PER_MM
    m = cv2.getPerspectiveTransform(quad.astype(np.float32), dst.astype(np.float32))
    size = (int(PAGE_W * PX_PER_MM), int(PAGE_H * PX_PER_MM))
    return cv2.warpPerspective(img, m, size, flags=cv2.INTER_LINEAR, borderValue=255)


def _px(v: float) -> int:
    return int(round(v * PX_PER_MM))


def page_number(page_gray: np.ndarray) -> int | None:
    dark = []
    for x, y in SLOTS_AT:
        a = page_gray[_px(y + 0.8):_px(y + SLOT - 0.8), _px(x + 0.8):_px(x + SLOT - 0.8)]
        dark.append(float(np.mean(a < 128)) if a.size else 0.0)
    filled = [i for i, d in enumerate(dark) if d > 0.6]
    return filled[0] + 1 if len(filled) == 1 else None


def _pieces(strokes: list[np.ndarray], touch: float) -> list[list[int]]:
    n = len(strokes)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        for j in range(i + 1, n):
            d = np.min(np.linalg.norm(strokes[i][:, None, :] - strokes[j][None, :, :], axis=2))
            if d <= touch:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _carrier_marks(strokes: list[np.ndarray], need: list[str]) -> list[dict] | None:
    """Split a carrier box (x-height units, y down, baseline 0) into its marks; None when they cannot be told apart."""
    groups = _pieces(strokes, touch=0.08)
    boxes = [(min(strokes[i][:, 0].min() for i in g), min(strokes[i][:, 1].min() for i in g),
              max(strokes[i][:, 0].max() for i in g), max(strokes[i][:, 1].max() for i in g)) for g in groups]
    upper = [k for k, b in enumerate(boxes) if b[3] < -0.85]            # wholly above the x-height band (top is -1)
    lower = [k for k, b in enumerate(boxes) if b[1] > 0.15 and (b[3] - b[1]) < 0.6]       # small, under the baseline
    body = [k for k in range(len(groups)) if k not in upper and k not in lower]
    want_up = [m for m in need if m != "dot_below"]
    want_low = [m for m in need if m == "dot_below"]
    if not body or len(upper) != len(want_up) or len(lower) != len(want_low):
        return None
    hb = (min(boxes[k][0] for k in body), min(boxes[k][1] for k in body), max(boxes[k][2] for k in body),
          max(boxes[k][3] for k in body))
    upper.sort(key=lambda k: -boxes[k][3])                               # the hat sits under the tone mark
    out = []
    for name, k in list(zip(want_up, upper)) + list(zip(want_low, lower)):
        b = boxes[k]
        out.append({"mark": name, "strokes": [_round(strokes[i] - (b[0], b[3])) for i in groups[k]],
                    "dx": round(((b[0] + b[2]) - (hb[0] + hb[2])) / 2, 4), "dy": round(b[3] - hb[1], 4)})
    return out


def _round(a: np.ndarray) -> list[list[float]]:
    return [[round(float(x), 4), round(float(y), 4)] for x, y in a]


def read_page(data: bytes, page_no: int) -> dict:
    """Read one photographed page. Returns {"page", "sheet_version", "cells": [...]}; raises AppError when the page
    cannot be located or is another page of the sheet."""
    if not 1 <= page_no <= pages():
        raise AppError(422, "SHEET_PAGE_INVALID", f"Phiếu có {pages()} trang.")
    g = warp(data)
    found = page_number(g)
    if found is None:
        raise AppError(422, "SHEET_PAGE_UNREADABLE", "Không đọc được số trang in trên phiếu. Hãy chụp lại rõ hơn.")
    if found != page_no:
        raise AppError(422, "SHEET_PAGE_MISMATCH", f"Ảnh này là trang {found} của phiếu, không phải trang {page_no}.")
    ink_page = recovery._binarise(g)
    cells = []
    for cell in (c for c in layout() if c.page == page_no):
        x0, y0 = _px(cell.x + INSET), _px(cell.y + INSET)
        x1, y1 = _px(cell.x + BOX - INSET), _px(cell.y + BOX - INSET)
        ink = recovery._remove_specks(ink_page[y0:y1, x0:x1].copy())
        out = {"cell": cell.id, "char": cell.char, "status": "OK", "strokes": [], "pen_width_mm": None}
        if int((ink > 0).sum()) < 0.6 * PX_PER_MM * PX_PER_MM:          # less than ~0.6 mm2 of ink
            out["status"] = "EMPTY"
            cells.append(out)
            continue
        edge = np.concatenate([ink[0, :], ink[-1, :], ink[:, 0], ink[:, -1]])
        try:
            paths, _, width_px = recovery.trace(ink)
        except AppError as exc:
            out["status"] = "EMPTY" if exc.code == "NO_STROKES_FOUND" else "NOISY"
            cells.append(out)
            continue
        off = np.array([INSET, INSET - BASELINE])
        strokes = [(p / PX_PER_MM + off) / XH_MM for p in paths]
        out["strokes"] = [_round(s) for s in strokes]
        out["pen_width_mm"] = round(width_px / PX_PER_MM, 3)
        if int((edge > 0).sum()) > 2:
            out["status"] = "OVERFLOW"
        need = marks_of(cell.char)
        if cell.char in CARRIERS and out["status"] == "OK":
            marks = _carrier_marks(strokes, need)
            if marks is None:
                out["status"] = "MARKS_UNCLEAR"
            else:
                out["marks"] = marks
        cells.append(out)
    return {"page": page_no, "sheet_version": SHEET_VERSION, "cells": cells}


def summary(page_results: list[dict], rejected: set[str] | frozenset[str] = frozenset()) -> dict:
    """Coverage of a style from its read pages: which characters / marks have at least one usable sample."""
    have: dict[str, int] = {}
    issues = []
    for p in page_results:
        for c in p["cells"]:
            if c["status"] != "OK":
                issues.append({"cell": c["cell"], "char": c["char"], "status": c["status"]})
                continue
            if c["cell"] in rejected:
                continue
            if c["char"] not in CARRIERS:
                have[c["char"]] = have.get(c["char"], 0) + 1
            for m in c.get("marks", []):
                key = f"{c['cell']}:{m['mark']}"
                if key not in rejected:
                    have[m["mark"]] = have.get(m["mark"], 0) + 1
    t = targets()
    missing = [x for x in t if x not in have]
    return {"coverage_pct": round(100.0 * (len(t) - len(missing)) / len(t), 2), "missing": missing, "issues": issues,
            "samples": have}


def glyph_set(page_results: list[dict], rejected: set[str] | frozenset[str] = frozenset()) -> dict:
    """The stored glyph set of an approved style (`handwriting_styles.glyph_set_uri`)."""
    glyphs: dict[str, list] = {}
    marks: dict[str, list] = {}
    for p in page_results:
        for c in p["cells"]:
            if c["status"] != "OK" or c["cell"] in rejected:
                continue
            if c["char"] not in CARRIERS:
                glyphs.setdefault(c["char"], []).append({"id": c["cell"], "strokes": c["strokes"],
                                                          "pen_width_mm": c["pen_width_mm"]})
            for m in c.get("marks", []):
                if f"{c['cell']}:{m['mark']}" in rejected:
                    continue
                marks.setdefault(m["mark"], []).append({"id": f"{c['cell']}:{m['mark']}", "strokes": m["strokes"],
                                                        "dx": m["dx"], "dy": m["dy"]})
    s = summary(page_results, rejected)
    return {"format": "ot2-glyphs/1", "sheet_version": SHEET_VERSION, "units": "x-height, y down, baseline 0",
            "x_height_mm": XH_MM, "glyphs": glyphs, "marks": marks, "coverage_pct": s["coverage_pct"],
            "missing": s["missing"]}


def page_png(page_gray: np.ndarray) -> bytes:
    return cv2.imencode(".png", page_gray)[1].tobytes()


def cell_png(data: bytes, page_no: int, cell_id: str) -> bytes:
    """The photographed box of a cell (for the Staff review), cut from the warped page."""
    cell = next((c for c in layout() if c.id == cell_id and c.page == page_no), None)
    if cell is None:
        raise AppError(404, "CELL_NOT_FOUND", "Không có ô này trên phiếu.")
    g = warp(data)
    pad = 2.0
    crop = g[_px(cell.y - pad):_px(cell.y + BOX + pad), _px(cell.x - pad):_px(cell.x + BOX + pad)]
    return cv2.imencode(".png", crop)[1].tobytes()

