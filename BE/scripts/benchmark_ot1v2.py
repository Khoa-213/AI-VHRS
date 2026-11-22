"""OT-1 recovery v2, phase R0 (docs/OT1_RECOVERY_V2_PLAN.md, owner approved 2026-11-21): a SYNTHETIC noise benchmark with a
known ground-truth ink mask, the v2 similarity measure, and the v1 baseline.

Build (deterministic, seed 2026):
  clean real handwriting from benchmarks/data/viet_hw/ (public sample of U3, research use, not committed) -> flatten + Otsu =
  ground-truth ink mask -> re-inked on a synthetic paper -> one noise family per sample:
    clean, ruled, ruled_same (lines in the ink colour), fold, tear, background (wood-like backdrop + perspective tilt),
    stain (yellowing + blotches), lowres (short side 700-900 px), mixed (ruled + fold + tear + background),
    ruled_hard (dark grey lines, faded ink, fold, low resolution: like the owner's letter).
  Every geometric step is applied to the mask too, so the mask stays exact in the final image. Backgrounds and paper are
  generated (no download). Output: benchmarks/data/ot1v2/synthetic/<id>.jpg, <id>_gt.png, manifest.json.

Measure (v2 similarity, fixed BEFORE measuring, plan section 2 / 4):
  the engine's strokes are mapped back to the input image pixels and drawn 1 px wide (centre lines);
  GT skeleton = Zhang-Suen of the GT mask; w = median GT stroke width; tau = max(1, w / 2) px;
  precision = share of predicted centre-line pixels within tau of the GT skeleton  (1 - precision = noise rate)
  recall    = share of GT skeleton pixels within tau of a predicted centre line      (coverage)
  similarity v2 = F1. Also the old pixel IoU that the product shows today.

    python scripts/benchmark_ot1v2.py build
    python scripts/benchmark_ot1v2.py measure --engine v1 --tag R0
    python scripts/benchmark_ot1v2.py real --engine v1 --tag R0      # the owner's photos: images only (no GT yet, Q2)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

BE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BE))

from app.services.stroke_ai import recovery as R  # noqa: E402
from app.services.stroke_ai.trajectory import PAPER_MM  # noqa: E402

SRC = BE / "benchmarks" / "data" / "viet_hw"
OUT = BE / "benchmarks" / "data" / "ot1v2"
SYN = OUT / "synthetic"
REAL = OUT / "real"
FAMILIES = ("clean", "ruled", "ruled_same", "fold", "tear", "background", "stain", "lowres", "mixed", "ruled_hard")
# ruled_hard (added in R0 before any v2 work): the owner's real letter beat v1 far worse than "ruled" did, so a family
# like it: dark grey lines close to the ink darkness, faded ink, a fold, short side 700-900 px. Appended last so the
# other families keep their seeds.
N_SOURCES = 22                       # 22 sources x 10 families = 220 images
SEED = 2026


# ------------------------------------------------------------------------------------------------ ground truth
def gt_mask(gray: np.ndarray) -> np.ndarray:
    """Clean scans: flatten + Otsu + speckle removal is the ink. Same simple rule for every source."""
    flat = R._flatten(gray)
    _, ink = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return R._remove_specks(ink)


def stroke_width(mask: np.ndarray) -> float:
    sk = R.zhang_suen(mask) > 0
    if not sk.any():
        return 2.0
    dt = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    return float(max(1.0, 2.0 * np.median(dt[sk])))


# ------------------------------------------------------------------------------------------------ synthesis
def _paper(h: int, w: int, rng: np.random.Generator, yellow: float = 0.0) -> np.ndarray:
    base = np.array([238, 242, 245], np.float32) - rng.uniform(0, 12)          # BGR, slightly off-white
    base = base * (1 - yellow) + np.array([150, 205, 230], np.float32) * yellow
    img = np.empty((h, w, 3), np.float32)
    img[:] = base
    grain = cv2.GaussianBlur(rng.normal(0, 6, (h, w)).astype(np.float32), (0, 0), 1.2)
    light = np.linspace(rng.uniform(-10, 0), rng.uniform(0, 8), w, dtype=np.float32)[None, :]
    return img + (grain + light)[..., None]


def _ink_colour(rng: np.random.Generator) -> np.ndarray:
    return np.array(rng.choice([[150, 40, 30], [120, 30, 60], [60, 40, 40], [170, 60, 40]]), np.float32)  # blue / violet / black


def _ruled(img: np.ndarray, rng: np.random.Generator, colour: np.ndarray, spacing: float, margin: bool) -> None:
    h, w = img.shape[:2]
    y = rng.uniform(0.3, 1.0) * spacing
    thick = int(rng.integers(1, 3))
    while y < h:
        cv2.line(img, (0, int(y)), (w, int(y + rng.uniform(-1.5, 1.5))), colour.tolist(), thick, cv2.LINE_AA)
        y += spacing
    if margin:
        x = int(w * rng.uniform(0.06, 0.12))
        cv2.line(img, (x, 0), (x + int(rng.uniform(-3, 3)), h), (60, 60, 200), thick, cv2.LINE_AA)


def _fold(img: np.ndarray, rng: np.random.Generator) -> None:
    h, w = img.shape[:2]
    for _ in range(int(rng.integers(1, 3))):
        horizontal = rng.random() < 0.5
        if horizontal:
            p0, p1 = (0, rng.uniform(0.2, 0.8) * h), (w, rng.uniform(0.2, 0.8) * h)
        else:
            p0, p1 = (rng.uniform(0.2, 0.8) * w, 0), (rng.uniform(0.2, 0.8) * w, h)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        a, b = np.array(p0, np.float32), np.array(p1, np.float32)
        d = b - a
        dist = ((xx - a[0]) * d[1] - (yy - a[1]) * d[0]) / (np.linalg.norm(d) + 1e-6)       # signed distance
        shade = -18 * np.exp(-np.maximum(dist, 0) / rng.uniform(8, 25)) * (dist > 0)
        ridge = -55 * np.exp(-(dist / 1.2) ** 2)
        img += (shade + ridge)[..., None]


def _stain(img: np.ndarray, rng: np.random.Generator) -> None:
    h, w = img.shape[:2]
    for _ in range(int(rng.integers(2, 5))):
        cx, cy, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0.04, 0.15) * min(h, w)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        blob = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r)))
        img -= (blob * rng.uniform(20, 45))[..., None] * np.array([1.0, 0.6, 0.25], np.float32)


def _wood(h: int, w: int, rng: np.random.Generator) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ang = rng.uniform(-0.3, 0.3)
    u = xx * math.sin(ang) + yy * math.cos(ang)
    grain = np.sin(u / rng.uniform(6, 14) + 3 * np.sin(xx / rng.uniform(80, 200))) * 18
    noise = cv2.GaussianBlur(rng.normal(0, 10, (h, w)).astype(np.float32), (0, 0), 2)
    base = np.array([40, 70, 115], np.float32) + rng.uniform(-15, 15)          # brown, BGR
    img = base + (grain + noise)[..., None]
    gap = rng.uniform(90, 160)                                                   # dark seams between boards
    seams = (np.mod(u, gap) < 3.0)
    img[seams] = [15, 20, 25]
    return img


def _compose(ink_mask: np.ndarray, paper: np.ndarray, colour: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    alpha = cv2.GaussianBlur(ink_mask.astype(np.float32) / 255.0, (0, 0), 0.6) * rng.uniform(0.85, 1.0)
    return paper * (1 - alpha[..., None]) + colour * alpha[..., None]


def _tear(img: np.ndarray, gt: np.ndarray, rng: np.random.Generator, backdrop: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cut the page along a jagged line into two pieces, shift the lower / right piece, show the backdrop in the gap."""
    h, w = gt.shape
    horizontal = rng.random() < 0.6
    n = 24
    if horizontal:
        xs = np.linspace(0, w, n)
        ys = np.clip(rng.uniform(0.35, 0.65) * h + np.cumsum(rng.normal(0, 0.02 * h, n)), 0.1 * h, 0.9 * h)
        poly = np.array([[0, 0], *zip(xs, ys), [w, 0]], np.int32)
    else:
        ys = np.linspace(0, h, n)
        xs = np.clip(rng.uniform(0.35, 0.65) * w + np.cumsum(rng.normal(0, 0.02 * w, n)), 0.1 * w, 0.9 * w)
        poly = np.array([[0, 0], *zip(xs, ys), [0, h]], np.int32)
    first = np.zeros((h, w), np.uint8)
    cv2.fillPoly(first, [poly], 255)
    dx, dy = (rng.uniform(-6, 6), rng.uniform(8, 22)) if horizontal else (rng.uniform(8, 22), rng.uniform(-6, 6))
    m = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-2, 2), 1.0)
    m[:, 2] += (dx, dy)
    second = cv2.warpAffine(255 - first, m, (w, h), flags=cv2.INTER_NEAREST)
    img2 = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    gt2 = cv2.warpAffine(gt, m, (w, h), flags=cv2.INTER_NEAREST)
    out = backdrop.copy()
    out[second > 0] = img2[second > 0]
    out[first > 0] = img[first > 0]
    gt_out = np.where(first > 0, gt, np.where(second > 0, gt2, 0)).astype(np.uint8)
    edge = cv2.morphologyEx(np.maximum(first, second), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))   # torn fibres
    out[edge > 0] = out[edge > 0] * 0.75 + 255 * 0.25
    return out, gt_out


def _on_background(img: np.ndarray, gt: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    h, w = gt.shape
    pad = int(0.18 * max(h, w))
    H, W = h + 2 * pad, w + 2 * pad
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    tilt = math.radians(rng.uniform(3, 15)) * (1 if rng.random() < 0.5 else -1)
    c, s = math.cos(tilt), math.sin(tilt)
    centre = np.float32([W / 2, H / 2])
    dst = []
    for x, y in src:
        px, py = x - w / 2, y - h / 2
        q = np.float32([px * c - py * s, px * s + py * c]) + centre
        dst.append(q + rng.uniform(-0.03, 0.03, 2).astype(np.float32) * np.float32([w, h]))      # perspective
    m = cv2.getPerspectiveTransform(src, np.float32(dst))
    back = _wood(H, W, rng)
    paper_mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (W, H), flags=cv2.INTER_NEAREST)
    warped = cv2.warpPerspective(img, m, (W, H), flags=cv2.INTER_LINEAR)
    gt2 = cv2.warpPerspective(gt, m, (W, H), flags=cv2.INTER_NEAREST)
    out = np.where(paper_mask[..., None] > 0, warped, back)
    return out, gt2


def build() -> None:
    rng = np.random.default_rng(SEED)
    files = sorted(SRC.glob("*.jpg"))
    if len(files) < N_SOURCES:
        sys.exit(f"need {N_SOURCES} images in {SRC} (scripts/fetch_hf_handwriting.py)")
    pick = [files[i] for i in np.linspace(0, len(files) - 1, N_SOURCES).round().astype(int)]
    SYN.mkdir(parents=True, exist_ok=True)
    manifest = []
    for si, f in enumerate(pick):
        gray = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        s = 1400 / max(gray.shape)
        if s < 1:
            gray = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        ink = gt_mask(gray)
        ys, xs = np.nonzero(ink)
        if len(xs) == 0:
            continue
        # page = text bounding box + margins, so the paper is visible around the writing
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
        mh, mw = int(0.15 * (y1 - y0) + 40), int(0.08 * (x1 - x0) + 40)
        ink = cv2.copyMakeBorder(ink[y0:y1 + 1, x0:x1 + 1], mh, mh, mw, mw, cv2.BORDER_CONSTANT, value=0)
        w_px = stroke_width(ink)
        for fam in FAMILIES:
            r = np.random.default_rng([SEED, si, FAMILIES.index(fam)])
            h, w = ink.shape
            colour = _ink_colour(r)
            paper = _paper(h, w, r, yellow=r.uniform(0.25, 0.55) if fam == "stain" else r.uniform(0, 0.1))
            spacing = r.uniform(7.0, 10.0) * w_px * 3.2                     # ~7-10 mm at ~0.3 mm / px pen width
            if fam in ("ruled", "mixed"):
                _ruled(paper, r, np.array(r.choice([[215, 170, 140], [200, 180, 190], [175, 175, 175]]), np.float32),
                       spacing, margin=r.random() < 0.6)
            if fam == "ruled_same":
                _ruled(paper, r, colour * 0.6 + paper.mean(axis=(0, 1)) * 0.4, spacing, margin=False)
            if fam == "stain":
                _stain(paper, r)
            if fam == "ruled_hard":
                grey = float(r.uniform(95, 135))
                _ruled(paper, r, np.array([grey + 10, grey, grey - 5], np.float32), spacing, margin=False)
                colour = colour * 0.55 + np.array([200, 170, 150], np.float32) * 0.45      # faded ink
            img = _compose(ink, paper, colour, r)
            gt = ink.copy()
            if fam in ("fold", "mixed", "ruled_hard"):
                _fold(img, r)
            if fam in ("tear", "mixed"):
                img, gt = _tear(img, gt, r, _wood(h, w, r) if fam == "mixed" else np.full((h, w, 3), r.uniform(60, 120), np.float32))
            if fam in ("background", "mixed"):
                img, gt = _on_background(img, gt, r)
            img = np.clip(img + r.normal(0, 2.5, img.shape), 0, 255).astype(np.uint8)
            if fam in ("lowres", "ruled_hard"):
                k = r.uniform(700, 900) / min(img.shape[:2])
                if k < 1:
                    img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
                    gt = (cv2.resize(gt, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_AREA) > 127).astype(np.uint8) * 255
            sid = f"{si:02d}_{fam}"
            cv2.imwrite(str(SYN / f"{sid}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            cv2.imwrite(str(SYN / f"{sid}_gt.png"), gt)
            manifest.append({"id": sid, "family": fam, "source": f.name, "shape": list(img.shape[:2])})
        print(f"source {si + 1}/{len(pick)} {f.name}", flush=True)
    (SYN / "manifest.json").write_text(json.dumps({"seed": SEED, "families": FAMILIES, "items": manifest}, indent=1))
    print(f"built {len(manifest)} images in {SYN}")


# ------------------------------------------------------------------------------------------------ engines
def run_v1(data: bytes, paper_size: str = "A4") -> tuple[list[np.ndarray], dict]:
    """v1 recovery; strokes mapped back to the pixels of the input image (undo fit-to-paper, deskew and down-scaling)."""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    H0, W0 = img.shape
    sc = min(1.0, R.MAX_SIDE_PX / max(H0, W0))
    h, w = (int(H0 * sc), int(W0 * sc)) if sc < 1 else (H0, W0)
    if sc < 1:                                   # cv2.resize rounds like this
        h, w = cv2.resize(img, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA).shape
    page, st = R.recover_page(data, paper_size=paper_size)
    pw, ph = PAPER_MM[paper_size]
    s = st.mm_per_px
    ox, oy = (pw - w * s) / 2, (ph - h * s) / 2
    inv = cv2.invertAffineTransform(cv2.getRotationMatrix2D((w / 2, h / 2), st.deskew_deg, 1.0)) if st.deskew_deg else None
    out = []
    for stroke in page.strokes:
        p = (np.asarray(stroke.points, np.float64) - (ox, oy)) / s
        if inv is not None:
            p = p @ inv[:, :2].T + inv[:, 2]
        out.append(p / sc)
    return out, {"similarity_v1": st.similarity, "n_strokes": len(page.strokes), "deskew": st.deskew_deg,
                 "restored": sum(1 for r in st.regions if r.label != "ORIGINAL"), "regions": len(st.regions)}


def run_v2(data: bytes, paper_size: str = "A4") -> tuple[list[np.ndarray], dict]:
    """v2 recovery (app/services/stroke_ai/recovery_v2.py, phases done so far); strokes mapped back the same way."""
    from app.services.stroke_ai import recovery_v2 as R2
    page, st, geo = R2.recover_page(data, paper_size=paper_size)
    out = [R2.to_photo_px(np.asarray(stroke.points, np.float64), geo) for stroke in page.strokes]
    return out, {"similarity_v1": st.similarity, "n_strokes": len(page.strokes), "deskew": st.deskew_deg,
                 "restored": sum(1 for r in st.regions if r.label != "ORIGINAL"), "regions": len(st.regions),
                 "paper": (geo["paper"] or {}).get("method"), "warnings": st.warnings}


ENGINES = {"v1": run_v1, "v2": run_v2}


# ------------------------------------------------------------------------------------------------ v2 similarity
def similarity_v2(strokes: list[np.ndarray], gt: np.ndarray) -> dict:
    h, w = gt.shape
    pred = np.zeros((h, w), np.uint8)
    for p in strokes:
        if len(p) >= 2:
            cv2.polylines(pred, [np.round(p).astype(np.int32).reshape(-1, 1, 2)], False, 255, 1)
        elif len(p) == 1:
            x, y = np.round(p[0]).astype(int)
            if 0 <= x < w and 0 <= y < h:
                pred[y, x] = 255
    gsk = R.zhang_suen(gt) > 0
    wid = stroke_width(gt)
    tau = max(1.0, wid / 2)
    d_gt = cv2.distanceTransform((~gsk).astype(np.uint8), cv2.DIST_L2, 5)
    d_pr = cv2.distanceTransform((pred == 0).astype(np.uint8), cv2.DIST_L2, 5)
    pp, gp = pred > 0, gsk
    precision = float((d_gt[pp] <= tau).mean()) if pp.any() else 0.0
    recall = float((d_pr[gp] <= tau).mean()) if gp.any() else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"f1": round(100 * f1, 2), "precision": round(100 * precision, 2), "recall": round(100 * recall, 2),
            "noise_rate": round(100 * (1 - precision), 2), "tau_px": round(tau, 2), "stroke_px": round(wid, 2)}


def measure(engine: str, tag: str) -> None:
    man = json.loads((SYN / "manifest.json").read_text())
    run = ENGINES[engine]
    rows = []
    for it in man["items"]:
        data = (SYN / f"{it['id']}.jpg").read_bytes()
        gt = cv2.imread(str(SYN / f"{it['id']}_gt.png"), cv2.IMREAD_GRAYSCALE)
        t = time.time()
        try:
            strokes, info = run(data)
            m = similarity_v2(strokes, gt)
        except Exception as exc:                           # a refused image counts as 0, reported
            info, m = {"error": type(exc).__name__}, {"f1": 0.0, "precision": 0.0, "recall": 0.0, "noise_rate": 100.0}
        rows.append({**it, **info, **m, "sec": round(time.time() - t, 2)})
        print(f"{it['id']:<16} F1 {m['f1']:6.2f}  P {m['precision']:6.2f}  R {m['recall']:6.2f}  "
              f"old {info.get('similarity_v1', '-')}", flush=True)
    res = OUT / f"results_{engine}_{tag}.json"
    res.write_text(json.dumps(rows, indent=1))
    print("\nfamily        n   F1    P(1-noise)  R(cover)  old-IoU  strokes  sec")
    for fam in [*man["families"], "ALL"]:
        rs = [r for r in rows if fam == "ALL" or r["family"] == fam]
        if not rs:
            continue
        mean = lambda k: float(np.mean([r.get(k, 0) or 0 for r in rs]))   # noqa: E731
        print(f"{fam:<12} {len(rs):3d} {mean('f1'):6.2f} {mean('precision'):9.2f} {mean('recall'):9.2f} "
              f"{mean('similarity_v1'):8.2f} {mean('n_strokes'):8.0f} {mean('sec'):5.2f}")
    print(f"-> {res}")


def real(engine: str, tag: str) -> None:
    """The owner's photos: no ground truth yet (Q2), so only the recovered strokes over the photo + old numbers."""
    out = OUT / f"real_{engine}_{tag}"
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted(REAL.iterdir()):
        if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        data = f.read_bytes()
        strokes, info = ENGINES[engine](data)
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        over = (img * 0.45 + 255 * 0.55).astype(np.uint8)
        for p in strokes:
            cv2.polylines(over, [np.round(p).astype(np.int32).reshape(-1, 1, 2)], False, (0, 0, 220), 1, cv2.LINE_AA)
        cv2.imwrite(str(out / f"{f.stem}_overlay.jpg"), over)
        print(f.name, info)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("build", "measure", "real"))
    ap.add_argument("--engine", default="v1", choices=tuple(ENGINES))
    ap.add_argument("--tag", default="R0")
    a = ap.parse_args()
    {"build": build, "measure": lambda: measure(a.engine, a.tag), "real": lambda: real(a.engine, a.tag)}[a.cmd]()


if __name__ == "__main__":
    main()
