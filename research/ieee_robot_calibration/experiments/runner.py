"""Experiment runner for E1 (calibration accuracy), E5 (handwriting accuracy) and the sensitivity studies E2/E3/E4.

    python experiments/runner.py e1            # 30 trials
    python experiments/runner.py e5            # 30 trials
    python experiments/runner.py e2 | e3 | e4  # 20 trials per setting
    python experiments/runner.py all

Every trial = one independent ground-truth robot (seed). Within a trial all methods share the same robot, the same test set and
the same probe readings (paired design). Calibration data are drawn from a stream that depends on (seed, layout, sample count).
Raw rows go to results/raw/<exp>.csv, run metadata to results/raw/<exp>_meta.json, failures are kept (status column).
"""
from __future__ import annotations

import csv
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vhrs_calib.calibrate import observability, theta_of  # noqa: E402
from vhrs_calib.compensation import probe_paper  # noqa: E402
from vhrs_calib.pipeline import (ExpConfig, Scene, config_from_dict, config_to_dict, e1_metrics, load_strokes, metadata,  # noqa: E402
                                 pen_model, rng_for, run_calibration, test_set, to_jsonable, write_sample)
from vhrs_calib.truth import make_truth  # noqa: E402
from vhrs_calib.workspace import BALL_TOOL_FLANGE, PEN_TOOL_FLANGE, CollectConfig, collect_socket_data, layout  # noqa: E402

RAW = ROOT / "results" / "raw"
E1_SEEDS = list(range(1000, 1030))
E5_SEEDS = list(range(1000, 1030))
SENS_SEEDS = list(range(2000, 2020))
LAYOUTS = ["S2", "S3", "S2x2", "S3L"]
_SCENE = None
_STROKES = None


def scene() -> Scene:
    global _SCENE
    if _SCENE is None:
        _SCENE = Scene()
    return _SCENE


def strokes():
    global _STROKES
    if _STROKES is None:
        _STROKES = load_strokes()
    return _STROKES


def load_cfg() -> ExpConfig:
    return config_from_dict(json.loads((ROOT / "configs" / "default.json").read_text()))


def identifiable_projector(truth, sc: Scene) -> tuple[np.ndarray, np.ndarray]:
    """Row space of the zero-residual identification Jacobian (structure only: geometric truth, noise-free S3 data)."""
    from vhrs_calib.truth import TruthRobot
    from vhrs_calib.kinematics import KinModel
    geo = TruthRobot(arm=KinModel(origins=truth.arm.origins.copy()), ball_tool_flange=truth.ball_tool_flange,
                     pen_tool_flange=truth.pen_tool_flange, delta_origins=truth.delta_origins, seed=truth.seed)
    ccfg = CollectConfig(sigma_seat_mm=0, sigma_q_deg=0, sigma_d_mm=0)
    data, _ = collect_socket_data(rng_for(truth.seed, 70), geo.ball(), layout("S3", sc.paper), 20, sc.R_w, sc.q_seed, ccfg)
    th = theta_of(geo.arm.origins, geo.ball_tool_flange, BALL_TOOL_FLANGE)
    ob = observability(data, th, BALL_TOOL_FLANGE)
    _, _, Vt = np.linalg.svd(np.eye(39) - ob["null_space"].T @ ob["null_space"])
    return Vt[: ob["rank"]], th


# ------------------------------------------------------------------------------------------------------------------- E1
def e1_trial(args) -> list[dict]:
    seed, cfg, layouts, n_total, tag = args
    sc = scene()
    rows = []
    try:
        tr = make_truth(seed, cfg.truth, BALL_TOOL_FLANGE, PEN_TOOL_FLANGE)
        qt = test_set(sc, tr, cfg, seed)
        P, th_true = identifiable_projector(tr, sc)
        base = {"seed": seed, "tag": tag, "n_total": n_total}
        rows.append({**base, "method": "nominal", "status": "ok", **e1_metrics(sc, tr, sc.nominal_ball, qt, cfg, seed),
                     "param_err_rel": 1.0})
        for name in layouts:
            try:
                res, data, secs = run_calibration(sc, tr, name, cfg, seed, n_total)
                m = e1_metrics(sc, tr, res.model, qt, cfg, seed)
                perr = float(np.linalg.norm(P @ (res.theta - th_true)) / np.linalg.norm(P @ th_true))
                rows.append({**base, "method": name, "status": "ok" if res.success else "not_converged", **m, "param_err_rel": perr,
                             "nfev": res.nfev, "cost_final": res.cost_final, "consistency_rms_mm": res.consistency_rms_mm,
                             "distortion_max_mm": float(np.max(np.abs(res.distortion_mm))), "rejected_draws": data["rejected"],
                             "solve_s": secs})
            except Exception as exc:                                        # noqa: BLE001 - failures are data
                rows.append({**base, "method": name, "status": f"error: {exc!r}"})
    except Exception as exc:                                                # noqa: BLE001
        rows.append({"seed": seed, "tag": tag, "method": "trial", "status": f"error: {exc!r}", "trace": traceback.format_exc()})
    return rows


# ------------------------------------------------------------------------------------------------------------------- E5
E5_METHODS = [("A_nominal_ideal_fixture", None, False), ("B_nominal_probe", None, False), ("C_S2_precomp", "S2", True),
              ("D_S3_precomp", "S3", True), ("E_S2x2_precomp", "S2x2", True), ("O_oracle_precomp", "oracle", True)]


def e5_trial(args) -> tuple[list[dict], dict | None]:
    seed, cfg, samples, tag, keep_paths = args
    sc = scene()
    st = strokes()
    rows, paths = [], ({} if keep_paths else None)
    try:
        tr = make_truth(seed, cfg.truth, BALL_TOOL_FLANGE, PEN_TOOL_FLANGE)
        models = {"oracle": tr.pen()}
        conv = {}
        for name in {m[1] for m in E5_METHODS if m[1] not in (None, "oracle")}:
            res, _, _ = run_calibration(sc, tr, name, cfg, seed)
            models[name] = pen_model(res.model)
            conv[name] = res.success
        q_probe = probe_paper(rng_for(seed, 40), tr.pen(), sc.paper, sc.q_seed, cfg.probe)
        for sample in samples:
            for meth, key, pc in E5_METHODS:
                try:
                    m, exe = write_sample(sc, tr, st[sample]["strokes"], meth, models.get(key), q_probe, pc)
                    ok = "ok" if (key in (None, "oracle") or conv[key]) and m["ik_fail"] == 0 else "degraded"
                    rows.append({"seed": seed, "tag": tag, "sample": sample, "category": st[sample]["category"], "method": meth,
                                 "status": ok, **m})
                    if keep_paths is not None and seed == keep_paths:
                        paths[f"{sample}|{meth}"] = np.concatenate([sc.paper.to_paper(x)[:, :3] for x in exe])
                except Exception as exc:                                    # noqa: BLE001
                    rows.append({"seed": seed, "tag": tag, "sample": sample, "method": meth, "status": f"error: {exc!r}"})
    except Exception as exc:                                                # noqa: BLE001
        rows.append({"seed": seed, "tag": tag, "method": "trial", "status": f"error: {exc!r}", "trace": traceback.format_exc()})
    return rows, paths


# ------------------------------------------------------------------------------------------------------------------- io
def write_csv(path: Path, rows: list[dict]) -> None:
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def pool_map(fn, jobs, workers=12):
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, jobs))


def run_e1(cfg: ExpConfig) -> None:
    t0 = time.time()
    out = pool_map(e1_trial, [(s, cfg, LAYOUTS, cfg.n_total, "E1") for s in E1_SEEDS])
    rows = [r for rs in out for r in rs]
    write_csv(RAW / "e1_calibration.csv", rows)
    meta = metadata("E1", config_to_dict(cfg), E1_SEEDS, {"methods": ["nominal", *LAYOUTS], "wall_s": time.time() - t0,
                                                          "n_rows": len(rows),
                                                          "n_failed": sum(1 for r in rows if r["status"] != "ok")})
    (RAW / "e1_calibration_meta.json").write_text(json.dumps(to_jsonable(meta), indent=1))
    print(f"E1: {len(rows)} rows, {meta['n_failed']} not ok, {time.time() - t0:.0f} s")


def run_e5(cfg: ExpConfig) -> None:
    t0 = time.time()
    samples = list(strokes().keys())
    out = pool_map(e5_trial, [(s, cfg, samples, "E5", E5_SEEDS[0]) for s in E5_SEEDS])
    rows = [r for rs, _ in out for r in rs]
    paths = next(p for _, p in out if p)
    write_csv(RAW / "e5_handwriting.csv", rows)
    np.savez_compressed(RAW / f"e5_paths_seed{E5_SEEDS[0]}.npz", **{k.replace("|", "__"): v for k, v in paths.items()})
    meta = metadata("E5", config_to_dict(cfg), E5_SEEDS, {"methods": [m[0] for m in E5_METHODS], "samples": samples,
                                                          "wall_s": time.time() - t0, "n_rows": len(rows),
                                                          "n_not_ok": sum(1 for r in rows if r["status"] != "ok")})
    (RAW / "e5_handwriting_meta.json").write_text(json.dumps(to_jsonable(meta), indent=1))
    print(f"E5: {len(rows)} rows, {meta['n_not_ok']} not ok, {time.time() - t0:.0f} s")


def run_sens(exp: str, cfg: ExpConfig) -> None:
    """E2 noise / unmodelled-error / error-magnitude robustness, E2b regularisation (lambda) ablation, E3 sample efficiency,
    E4 socket geometry and cone angle."""
    t0 = time.time()
    settings: list[tuple[str, ExpConfig, int, list[str]]] = []
    if exp == "e2":
        for k in [0.0, 0.5, 1.0, 2.0, 4.0, 8.0]:
            c = replace(cfg, collect=replace(cfg.collect, sigma_seat_mm=cfg.collect.sigma_seat_mm * k,
                                             sigma_q_deg=cfg.collect.sigma_q_deg * k, sigma_d_mm=cfg.collect.sigma_d_mm * k))
            settings.append((f"noise_x{k:g}", c, cfg.n_total, ["S2", "S3", "S2x2"]))
        for lab, tc in [("unmod_none", replace(cfg.truth, harmonic_amp_deg=0.0, use_compliance=False)),
                        ("unmod_harmonic_only", replace(cfg.truth, use_compliance=False)),
                        ("unmod_default", cfg.truth),
                        ("unmod_soft_x0.5K", replace(cfg.truth, stiffness_nm_per_rad=tuple(0.5 * np.array(cfg.truth.stiffness_nm_per_rad))))]:
            settings.append((lab, replace(cfg, truth=tc), cfg.n_total, ["S2", "S3", "S2x2"]))
        for s in [0.5, 2.0, 4.0]:
            settings.append((f"geo_scale_x{s:g}", replace(cfg, truth=replace(cfg.truth, scale=s)), cfg.n_total, ["S2", "S3", "S2x2"]))
    elif exp == "e3":
        for n in [12, 24, 36, 60, 90, 150]:
            settings.append((f"n{n}", cfg, n, ["S2", "S3", "S2x2"]))
    elif exp == "e4":
        for d in [50.0, 100.0, 150.0, 200.0, 250.0]:
            settings.append((f"spacing_{d:g}", replace(cfg, spacing_mm=d), cfg.n_total, ["S2", "S3", "S3L"]))
        for cone in [5.0, 10.0, 20.0, 30.0, 45.0]:
            settings.append((f"cone_{cone:g}", replace(cfg, collect=replace(cfg.collect, cone_deg=cone)), cfg.n_total, ["S2", "S3"]))
    elif exp == "e2b":
        clean = replace(cfg, truth=replace(cfg.truth, harmonic_amp_deg=0.0, use_compliance=False),
                        collect=replace(cfg.collect, sigma_seat_mm=0.0, sigma_q_deg=0.0, sigma_d_mm=0.0))
        for lam in [1e-8, 1e-6, 1e-4, 1e-2]:
            settings.append((f"lam{lam:g}_default", replace(cfg, lam=lam), cfg.n_total, ["S2", "S3", "S2x2"]))
            settings.append((f"lam{lam:g}_clean", replace(clean, lam=lam), cfg.n_total, ["S2", "S3", "S2x2"]))
    jobs = [(s, c, lays, n, tag) for tag, c, n, lays in settings for s in SENS_SEEDS]
    rows = [r for rs in pool_map(e1_trial, jobs) for r in rs]
    # E2 also runs the handwriting page under each noise / error setting (B vs C vs D)
    if exp == "e2":
        e5_jobs = [(s, c, ["page"], tag, None) for tag, c, _, _ in settings for s in SENS_SEEDS]
        e5rows = [r for rs, _ in pool_map(e5_trial, e5_jobs) for r in rs]
        write_csv(RAW / "e2_handwriting_page.csv", e5rows)
    write_csv(RAW / f"{exp}_sensitivity.csv", rows)
    meta = metadata(exp.upper(), config_to_dict(cfg), SENS_SEEDS, {"settings": [t for t, *_ in settings], "wall_s": time.time() - t0,
                                                                   "n_rows": len(rows),
                                                                   "n_not_ok": sum(1 for r in rows if r["status"] != "ok")})
    (RAW / f"{exp}_sensitivity_meta.json").write_text(json.dumps(to_jsonable(meta), indent=1))
    print(f"{exp}: {len(rows)} rows, {meta['n_not_ok']} not ok, {time.time() - t0:.0f} s")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    cfg = load_cfg()
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("e1", "all"):
        run_e1(cfg)
    if which in ("e5", "all"):
        run_e5(cfg)
    for e in ("e2", "e2b", "e3", "e4"):
        if which in (e, "all"):
            run_sens(e, cfg)


if __name__ == "__main__":
    main()
