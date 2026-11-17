"""Shared experiment pipeline: scene, one calibration run, E1 evaluation, E5 handwriting evaluation, run metadata."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from vhrs_calib.calibrate import calibrate
from vhrs_calib.compensation import ProbeConfig, execute, frame_from_probes, probe_paper, resample_stroke
from vhrs_calib.evaluation import make_test_set, position_errors, summarize
from vhrs_calib.kinematics import KinModel
from vhrs_calib.metrics import handwriting_metrics
from vhrs_calib.truth import TruthConfig, TruthRobot, make_truth
from vhrs_calib.workspace import (BALL_TOOL_FLANGE, PAPER_CORNERS, PEN_TOOL_FLANGE, CollectConfig, Paper, collect_socket_data,
                                  layout, writing_rotation, writing_seed)

ROOT = Path(__file__).resolve().parents[2]
LAYOUT_IDS = {"S2": 1, "S3": 2, "S2x2": 3, "S3L": 4}


@dataclass
class ExpConfig:
    truth: TruthConfig = field(default_factory=TruthConfig)
    collect: CollectConfig = field(default_factory=CollectConfig)
    probe: ProbeConfig = field(default_factory=ProbeConfig)
    n_total: int = 60                 # calibration configurations per method (split evenly over the sockets)
    spacing_mm: float = 150.0
    socket_height_mm: float = 12.0
    lam: float = 1e-4
    n_test: int = 500
    stroke_step_mm: float = 1.0


def config_from_dict(d: dict) -> ExpConfig:
    c = ExpConfig()
    for k, v in d.items():
        if k in ("truth", "collect", "probe"):
            sub = getattr(c, k)
            for kk, vv in v.items():
                if not hasattr(sub, kk):
                    raise KeyError(f"{k}.{kk}")
                setattr(sub, kk, tuple(vv) if isinstance(vv, list) else vv)
        elif hasattr(c, k):
            setattr(c, k, v)
        elif not k.startswith("_"):
            raise KeyError(k)
    return c


def config_to_dict(c: ExpConfig) -> dict:
    return asdict(c)


class Scene:
    def __init__(self):
        self.paper = Paper.from_corners(PAPER_CORNERS)
        self.R_w = writing_rotation(self.paper.n)
        self.nominal = KinModel()
        self.nominal_pen = self.nominal.with_tool(PEN_TOOL_FLANGE)
        self.nominal_ball = self.nominal.with_tool(BALL_TOOL_FLANGE)
        self.q_seed = writing_seed(self.nominal_pen, self.paper)


def rng_for(seed: int, *tags: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([seed, *tags]))


def run_calibration(scene: Scene, truth: TruthRobot, layout_name: str, cfg: ExpConfig, seed: int, n_total: int | None = None):
    lay = layout(layout_name, scene.paper, cfg.spacing_mm, cfg.socket_height_mm)
    n_total = n_total or cfg.n_total
    k = len(lay.centres)
    per = [n_total // k + (1 if i < n_total % k else 0) for i in range(k)]
    rng = rng_for(seed, 10, LAYOUT_IDS.get(layout_name, 9), n_total)
    t0 = time.perf_counter()
    data, hidden = collect_socket_data(rng, truth.ball(), lay, per, scene.R_w, scene.q_seed, cfg.collect)
    assert set(data) == {"q", "cluster", "pairs", "d", "n_clusters"}      # no ground truth reaches the solver
    res = calibrate(data, BALL_TOOL_FLANGE, cfg.lam)
    return res, {**data, **hidden}, time.perf_counter() - t0


def pen_model(arm: KinModel) -> KinModel:
    return KinModel(origins=arm.origins.copy(), name=arm.name).with_tool(PEN_TOOL_FLANGE)


def e1_metrics(scene: Scene, truth: TruthRobot, model_ball: KinModel, q_test: np.ndarray, cfg: ExpConfig, seed: int) -> dict:
    rng = rng_for(seed, 20)                     # identical measurement noise draw for every method (paired comparison)
    e = position_errors(model_ball, truth.ball(), q_test, np.radians(cfg.collect.sigma_q_deg), rng)
    return {**{f"aligned_{k}": v for k, v in summarize(e["aligned"]).items()}, **{f"raw_{k}": v for k, v in summarize(e["raw"]).items()}}


def test_set(scene: Scene, truth: TruthRobot, cfg: ExpConfig, seed: int) -> np.ndarray:
    return make_test_set(rng_for(seed, 30), truth.ball(), scene.paper, scene.R_w, scene.q_seed, cfg.n_test)


def write_sample(scene: Scene, truth: TruthRobot, strokes_uv: list[np.ndarray], method: str, model_arm: KinModel | None,
                 q_probe: np.ndarray, precomp: bool) -> tuple[dict, list[np.ndarray]]:
    """Run one handwriting sample through one method. Returns metrics and executed strokes (base frame)."""
    truth_pen = truth.pen()
    if method == "A_nominal_ideal_fixture":
        frame = scene.paper                                     # the sheet pose is known exactly (no probing)
        model_pen = scene.nominal_pen
    else:
        model_pen = scene.nominal_pen if model_arm is None else model_arm
        frame = frame_from_probes(model_pen, q_probe)
    R_model = writing_rotation(frame.n)
    pts = [frame.to_base(s, 0.0) for s in strokes_uv]
    flat = np.concatenate(pts)
    ex = execute(flat, R_model, scene.nominal_pen, truth_pen, scene.q_seed, model_pen if precomp else None)
    splits = np.cumsum([len(p) for p in pts])[:-1]
    exe = np.split(ex.tip, splits)
    m = handwriting_metrics(strokes_uv, exe, scene.paper)
    m["ik_fail"] = int((~ex.ik_ok).sum())
    return m, exe


def metadata(experiment_id: str, cfg_dict: dict, seeds: list[int], extra: dict | None = None) -> dict:
    def git(*a):
        try:
            return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:                                   # noqa: BLE001
            return None
    src = sorted((ROOT / "src" / "vhrs_calib").glob("*.py"))
    h = hashlib.sha256()
    for p in src:
        h.update(p.read_bytes())
    return {"experiment_id": experiment_id, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "git_head": git("rev-parse", "HEAD"), "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "research_dir_tracked": bool(git("ls-files", "src")), "source_sha256": h.hexdigest(),
            "model_version": "FR3 V6 vendor URDF (fairino3_v6.urdf) + 100 mm flange offset", "python": platform.python_version(),
            "numpy": np.__version__, "seeds": seeds, "config": cfg_dict, **(extra or {})}


def load_strokes(step_mm: float = 1.0) -> dict:
    d = json.loads((ROOT / "data" / "strokes.json").read_text(encoding="utf8"))
    out = {}
    for name, s in d["samples"].items():
        out[name] = {"category": s["category"], "source": s["source"],
                     "strokes": [resample_stroke(np.array(st), step_mm) for st in s["strokes"]]}
    return out


def to_jsonable(o):
    if isinstance(o, dict):
        return {k: to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o
