"""Deterministic safety / feasibility validation of a trajectory before any robot moves (SRS S8, FR-45, Service F).

No LLM, no learned model, nothing random: the same inputs always give the same verdict. The validator rebuilds the
robot-frame plan itself and checks the result geometrically, independently of how the plan was produced.

What it does NOT cover is stated in the report under `checks` as NOT_CHECKED: joint-level reachability (inverse
kinematics, joint limits, wrist singularities) needs the controller's own kinematics and is checked by the Robot Agent
against the real controller before the first move (no motion is needed for that). A report with a NOT_CHECKED
entry is still a pass for the server side, never a claim that the robot can do it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.services.motion.frame import FrameChecks, FrameError, PaperFrame, build_frame
from app.services.motion.plan import DEFAULT_DS_MM, MotionConfig, PagePlan, PlanError, plan_page
from app.services.stroke_ai.trajectory import Page

REACH_FRACTION = 0.9           # SRS S8: stay within 0.9 x the nominal reach
FR3_NOMINAL_REACH_MM = 622.0   # SRS / Report 1 (vendor figure; the team verifies it on the robot)
GEOM_TOL_MM = 0.05             # tolerance of the independent geometric re-check


@dataclass(frozen=True)
class Workspace:
    """Allowed volume in the robot BASE frame. A box is required for REAL runs (None = UNCONFIGURED)."""
    box_min_mm: tuple[float, float, float] | None = None
    box_max_mm: tuple[float, float, float] | None = None
    max_reach_mm: float = REACH_FRACTION * FR3_NOMINAL_REACH_MM   # radial distance from the base origin (conservative)
    edge_margin_mm: float = 0.0                                    # keep-out band inside the sheet edge

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Workspace":
        data = data or {}
        kw: dict[str, Any] = {}
        for key in ("box_min_mm", "box_max_mm"):
            if data.get(key) is not None:
                kw[key] = tuple(float(v) for v in data[key])
        for key in ("max_reach_mm", "edge_margin_mm"):
            if data.get(key) is not None:
                kw[key] = float(data[key])
        return cls(**kw)


@dataclass
class Issue:
    code: str
    message: str
    page: int | None = None
    stroke: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "page": self.page, "stroke": self.stroke}


@dataclass
class Report:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    checks: dict[str, str] = field(default_factory=dict)       # name -> PASS | FAIL | NOT_CHECKED
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors

    def err(self, code: str, message: str, page: int | None = None, stroke: int | None = None) -> None:
        self.errors.append(Issue(code, message, page, stroke))

    def warn(self, code: str, message: str, page: int | None = None, stroke: int | None = None) -> None:
        self.warnings.append(Issue(code, message, page, stroke))

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "errors": [e.as_dict() for e in self.errors],
                "warnings": [w.as_dict() for w in self.warnings], "checks": self.checks, "stats": self.stats}

    def error_texts(self) -> list[str]:
        return [f"{e.code}: {e.message}" for e in self.errors]


def _check(report: Report, name: str, before: int) -> None:
    report.checks[name] = "FAIL" if len(report.errors) > before else "PASS"


def validate(pages: list[Page], probe_points: list[Any], cfg: MotionConfig, workspace: Workspace = Workspace(), *,
             require_box: bool = True, frame_checks: FrameChecks = FrameChecks(), ds: float = DEFAULT_DS_MM
             ) -> tuple[Report, list[PagePlan]]:
    """Validate and plan. Returns (report, plans); `plans` is empty when the report has errors that stop planning."""
    rep = Report()
    rep.checks["joint_reachability_ik"] = "NOT_CHECKED"          # Robot Agent, against the real controller
    rep.checks["joint_limits_singularity"] = "NOT_CHECKED"
    plans: list[PagePlan] = []

    # 1. measured configuration present
    n = len(rep.errors)
    miss = cfg.missing()
    if miss:
        rep.err("UNCONFIGURED", "Thiếu thông số đã đo: " + ", ".join(miss))
    if require_box and (workspace.box_min_mm is None or workspace.box_max_mm is None):
        rep.err("UNCONFIGURED", "Chưa cấu hình hộp không gian làm việc (box_min_mm, box_max_mm).")
    elif workspace.box_min_mm is not None and workspace.box_max_mm is not None:
        if any(lo >= hi for lo, hi in zip(workspace.box_min_mm, workspace.box_max_mm)):
            rep.err("INVALID_CONFIG", "Hộp không gian làm việc có min >= max.")
    _check(rep, "configuration", n)
    if not pages:
        rep.err("EMPTY_TRAJECTORY", "Quỹ đạo không có trang nào.")
    if rep.errors:
        return rep, plans

    # 2. paper frame from the probes
    n = len(rep.errors)
    try:
        frame = build_frame(probe_points, frame_checks)
    except FrameError as exc:
        rep.err(exc.code, exc.message)
        _check(rep, "calibration_frame", n)
        return rep, plans
    rep.stats["frame"] = frame.to_dict()
    _check(rep, "calibration_frame", n)

    # 3. spring contact is mechanically possible
    n = len(rep.errors)
    try:
        cfg.require()
    except PlanError as exc:
        rep.err(exc.code, exc.message)
    else:
        if cfg.press_mm > cfg.max_spring_travel_mm:
            rep.err("SPRING_TRAVEL_EXCEEDED",
                    f"Nén lò xo {cfg.press_mm:.2f} mm vượt hành trình {cfg.max_spring_travel_mm:g} mm.")
        elif cfg.press_mm > 0.8 * cfg.max_spring_travel_mm:
            rep.warn("SPRING_TRAVEL_NEAR_LIMIT", f"Nén lò xo {cfg.press_mm:.2f} mm, sát hành trình cho phép.")
        if cfg.v_max_mm_s < 5.0:
            rep.warn("PEN_SPEED_BELOW_FLOOR", "v_max của bút thấp hơn tốc độ sàn 5 mm/s của hồ sơ vận tốc.")
    _check(rep, "gripper_contact", n)
    if rep.errors:
        return rep, plans

    total_s, total_len, n_strokes = 0.0, 0.0, 0
    for pi, page in enumerate(pages):
        # 4. every point inside the sheet (and its keep-out band)
        n = len(rep.errors)
        m = workspace.edge_margin_mm
        for si, st in enumerate(page.strokes):
            pts = np.asarray(st.points, dtype=np.float64)
            if not np.all(np.isfinite(pts)):
                rep.err("NON_FINITE_POINT", "Có toạ độ không hữu hạn.", pi, si)
            elif (pts[:, 0].min() < m or pts[:, 1].min() < m or pts[:, 0].max() > page.width_mm - m
                  or pts[:, 1].max() > page.height_mm - m):
                rep.err("OUTSIDE_PAPER", f"Nét nằm ngoài vùng viết của giấy {page.paper_size}.", pi, si)
        _check(rep, f"page{pi}_inside_paper", n)
        if rep.errors:
            continue

        try:
            plan = plan_page(page, frame, cfg, ds=ds)
        except PlanError as exc:
            rep.err(exc.code, exc.message, pi)
            continue
        plans.append(plan)
        total_s += plan.duration_s
        total_len += plan.write_length_mm
        n_strokes += plan.n_strokes

        # 5. independent geometric re-check of the robot-frame plan
        n = len(rep.errors)
        _check_plan(rep, plan, frame, cfg, workspace, ds, pi)
        _check(rep, f"page{pi}_plan_geometry", n)

    rep.stats.update({"pages": len(pages), "strokes": n_strokes, "write_length_mm": round(total_len, 2),
                      "estimated_seconds": int(math.ceil(total_s)), "press_mm": round(cfg.press_mm, 4),
                      "max_reach_mm": workspace.max_reach_mm})
    if rep.errors:
        plans = []
    return rep, plans


def _check_plan(rep: Report, plan: PagePlan, frame: PaperFrame, cfg: MotionConfig, ws: Workspace, ds: float,
                pi: int) -> None:
    lo = np.array(ws.box_min_mm) if ws.box_min_mm is not None else None
    hi = np.array(ws.box_max_mm) if ws.box_max_mm is not None else None
    expect_seq = {"travel": {"plunge"}, "plunge": {"write"}, "write": {"retract"}, "retract": {"travel"}}
    prev_kind: str | None = None
    for mv in plan.moves:
        if prev_kind is not None and mv.kind not in expect_seq[prev_kind]:
            rep.err("PEN_STATE_SEQUENCE", f"Thứ tự pen-up/pen-down sai: {prev_kind} -> {mv.kind}.", pi, mv.stroke_index)
        if prev_kind is None and mv.kind not in ("travel", "plunge"):
            rep.err("PEN_STATE_SEQUENCE", "Quỹ đạo bắt đầu không ở trạng thái pen-up.", pi, mv.stroke_index)
        prev_kind = mv.kind
        pts = mv.points
        if not (np.all(np.isfinite(pts)) and np.all(np.isfinite(mv.speeds))):
            rep.err("NON_FINITE_POINT", "Quỹ đạo robot có giá trị không hữu hạn.", pi, mv.stroke_index)
            continue

        # height of every point above the sheet surface, along the sheet normal
        rel = pts - frame.origin
        u, w, hgt = rel @ frame.x_axis, rel @ frame.y_axis, rel @ frame.normal
        lift = hgt - frame.height(u, w)
        if mv.kind == "write":
            if np.any(np.abs(lift + cfg.press_mm) > GEOM_TOL_MM):
                rep.err("PEN_HEIGHT_WRONG", "Độ cao ngòi bút khi viết không bằng độ nén lò xo đã tính.", pi, mv.stroke_index)
            if np.any(mv.speeds > cfg.v_max_mm_s + 1e-6):
                rep.err("SPEED_ABOVE_PEN_LIMIT", "Tốc độ viết vượt v_max của bút.", pi, mv.stroke_index)
            gaps = np.linalg.norm(np.diff(pts, axis=0), axis=1)
            if len(gaps) and float(gaps.max()) > ds * 1.05 + 1e-9:
                rep.err("POINT_JUMP", f"Hai điểm liên tiếp cách nhau {float(gaps.max()):.2f} mm.", pi, mv.stroke_index)
        elif mv.kind == "travel":
            if np.any(lift < cfg.pen_up_clearance_mm - GEOM_TOL_MM):
                rep.err("PEN_DOWN_DURING_TRAVEL", "Bút thấp hơn độ cao nâng khi di chuyển giữa các nét.", pi, mv.stroke_index)
            if np.any(mv.speeds > cfg.travel_speed_mm_s + 1e-6):
                rep.err("SPEED_ABOVE_TRAVEL_LIMIT", "Tốc độ di chuyển vượt giới hạn.", pi, mv.stroke_index)
        else:   # plunge / retract are straight along the normal
            d = pts[1] - pts[0]
            along = float(np.dot(d, frame.normal))
            if np.linalg.norm(d - along * frame.normal) > GEOM_TOL_MM:
                rep.err("PLUNGE_NOT_VERTICAL", "Hạ/nhấc bút không vuông góc mặt giấy.", pi, mv.stroke_index)
            if np.any(mv.speeds > cfg.approach_speed_mm_s + 1e-6):
                rep.err("SPEED_ABOVE_APPROACH_LIMIT", "Tốc độ hạ/nhấc bút vượt giới hạn.", pi, mv.stroke_index)

        # reach and box in the robot base frame
        radial = np.linalg.norm(pts, axis=1)
        if float(radial.max()) > ws.max_reach_mm:
            rep.err("OUT_OF_REACH", f"Điểm cách gốc robot {float(radial.max()):.1f} mm, vượt {ws.max_reach_mm:.1f} mm.",
                    pi, mv.stroke_index)
        if lo is not None and hi is not None and (np.any(pts < lo) or np.any(pts > hi)):
            rep.err("OUTSIDE_WORKSPACE", "Điểm nằm ngoài hộp không gian làm việc đã cấu hình.", pi, mv.stroke_index)
    if prev_kind is not None and prev_kind != "retract":
        rep.err("PEN_STATE_SEQUENCE", "Quỹ đạo kết thúc khi bút còn hạ.", pi)
