"""Upgrade U7: order the strokes of a page so the pen travels less in the air (docs/UPGRADE_AI_ROBOT_PLAN.md 3.6).

Rules (the plan, section 3.6 point 1):
* strokes of one WORD (`Stroke.group`, the same value on consecutive strokes) form a cluster: the order and direction of
  the strokes inside it never change, so a word's letters are still written before its tone marks;
* only the order of the clusters changes: nearest neighbour from the page's first cluster (it stays first), then 2-opt;
* a stroke without a group (customer drawing, underline / strike line) is a cluster of its own and may be drawn in the
  opposite direction; a stroke of a word never is;
* the result is kept only when the pen-up travel does not grow, so the optimiser can never make a page worse.

Pure computation, no I/O. Travel is the straight distance from one stroke's end to the next stroke's start on the paper
(the same figure as trajectory.compute_metrics), not a robot simulation.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np

from app.services.stroke_ai.trajectory import Page, Stroke

METHOD = "word-cluster-nn-2opt-v1"
TIME_BUDGET_S = 2.0          # per page; a dense A4 page has a few hundred words, 2-opt converges well inside this


@dataclass(frozen=True)
class OrderResult:
    order: list[int]             # new position -> old stroke index
    reversed: frozenset[int]     # old stroke indices drawn the other way
    travel_before_mm: float
    travel_after_mm: float
    clusters: int


def travel_mm(strokes: list[Stroke]) -> float:
    pts = [s for s in strokes if len(s.points) >= 2]
    return sum(math.dist(a.points[-1], b.points[0]) for a, b in zip(pts, pts[1:]))


def _clusters(strokes: list[Stroke]) -> list[list[int]]:
    out: list[list[int]] = []
    for i, s in enumerate(strokes):
        if out and s.group is not None and strokes[out[-1][-1]].group == s.group:
            out[-1].append(i)
        else:
            out.append([i])
    return out


def optimise(strokes: list[Stroke], time_budget_s: float = TIME_BUDGET_S) -> OrderResult:
    before = travel_mm(strokes)
    clusters = _clusters(strokes)
    n = len(clusters)
    identity = OrderResult(list(range(len(strokes))), frozenset(), round(before, 2), round(before, 2), n)
    if n < 3:
        return identity
    entry = np.array([strokes[c[0]].points[0] for c in clusters], float)
    exit_ = np.array([strokes[c[-1]].points[-1] for c in clusters], float)
    flippable = np.array([len(c) == 1 and strokes[c[0]].group is None for c in clusters])
    flipped = np.zeros(n, bool)

    def ends(k: int, flip: bool) -> tuple[np.ndarray, np.ndarray]:
        return (exit_[k], entry[k]) if flip else (entry[k], exit_[k])

    # nearest neighbour, the first cluster stays first and keeps its direction
    tour, left = [0], np.ones(n, bool)
    left[0] = False
    cur = exit_[0]
    for _ in range(n - 1):
        cand = np.flatnonzero(left)
        d_in = np.linalg.norm(entry[cand] - cur, axis=1)
        d_rev = np.where(flippable[cand], np.linalg.norm(exit_[cand] - cur, axis=1), np.inf)
        best = int(np.argmin(np.minimum(d_in, d_rev)))
        k = int(cand[best])
        flipped[k] = bool(d_rev[best] < d_in[best])
        tour.append(k)
        left[k] = False
        cur = ends(k, flipped[k])[1]

    # 2-opt on the open path: reverse the visiting order of tour[i..j]; flippable clusters inside also turn round
    t0 = time.monotonic()

    def arrays():
        a = np.array(tour)
        f = flipped[a]
        ent = np.where(f[:, None], exit_[a], entry[a])           # current entry / exit per position
        ext = np.where(f[:, None], entry[a], exit_[a])
        rf = f ^ flippable[a]                                    # orientation after a reversal
        rent = np.where(rf[:, None], exit_[a], entry[a])
        rext = np.where(rf[:, None], entry[a], exit_[a])
        fwd = np.linalg.norm(ent[1:] - ext[:-1], axis=1)         # edge k -> k+1 now
        bwd = np.linalg.norm(rent[:-1] - rext[1:], axis=1)       # edge k+1 -> k after reversing
        return ent, ext, rent, rext, fwd, bwd, np.concatenate([[0.0], np.cumsum(fwd)]), np.concatenate([[0.0], np.cumsum(bwd)])

    improved = True
    while improved and time.monotonic() - t0 < time_budget_s:
        improved = False
        ent, ext, rent, rext, fwd, bwd, cf, cb = arrays()
        i = 1
        while i < n - 1 and time.monotonic() - t0 < time_budget_s:
            j = np.arange(i + 1, n)
            old = fwd[i - 1] + (cf[j] - cf[i])
            new = np.linalg.norm(rent[j] - ext[i - 1], axis=1) + (cb[j] - cb[i])
            tail = j < n - 1
            jt = j[tail]
            old[tail] += fwd[jt]
            new[tail] += np.linalg.norm(ent[jt + 1] - rext[i], axis=1)
            gain = old - new
            best = int(np.argmax(gain))
            if gain[best] > 1e-6:                                # apply, then look again from the same position
                jj = int(j[best])
                seg = tour[i:jj + 1]
                for k in seg:
                    if flippable[k]:
                        flipped[k] = not flipped[k]
                tour[i:jj + 1] = seg[::-1]
                improved = True
                ent, ext, rent, rext, fwd, bwd, cf, cb = arrays()
            else:
                i += 1

    order = [s for k in tour for s in clusters[k]]
    rev = frozenset(clusters[k][0] for k in tour if flipped[k])
    after = travel_mm(apply(strokes, order, rev))
    if after > before - 1e-9:
        return identity
    return OrderResult(order, rev, round(before, 2), round(after, 2), n)


def apply(strokes: list[Stroke], order: list[int], reversed_: frozenset[int]) -> list[Stroke]:
    return [Stroke(list(reversed(strokes[i].points)), strokes[i].kind, strokes[i].group) if i in reversed_
            else strokes[i] for i in order]


def optimise_pages(pages: list[Page]) -> tuple[list[OrderResult], dict]:
    """Reorder every page in place; returns the per-page results and the summary that goes into engine metadata."""
    results = []
    for page in pages:
        r = optimise(page.strokes)
        page.strokes = apply(page.strokes, r.order, r.reversed)
        results.append(r)
    summary = {"method": METHOD,
               "travel_mm_before": round(sum(r.travel_before_mm for r in results), 2),
               "travel_mm_after": round(sum(r.travel_after_mm for r in results), 2),
               "clusters": sum(r.clusters for r in results),
               "reversed_strokes": sum(len(r.reversed) for r in results)}
    return results, summary
