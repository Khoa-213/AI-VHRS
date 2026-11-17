"""OBS: identifiability of the 39-parameter URDF model from socket constraints on the 6-DOF FR3.

For each socket layout and each socket cone half-angle alpha (the only source of configuration diversity for a 6-DOF arm whose
ball centre is pinned in a socket), noise-free data are generated from robots INSIDE the model class (no unmodelled errors), and
the identification Jacobian is evaluated at the true parameters (zero residual). Reported: numerical rank, number of
unidentifiable combinations, smallest identifiable singular value and condition number. 10 random robots per cell.
Output: results/raw/obs_observability.csv, results/raw/obs_observability_meta.json
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vhrs_calib.calibrate import PARAM_NAMES, observability, theta_of  # noqa: E402
from vhrs_calib.pipeline import Scene, metadata, rng_for, to_jsonable  # noqa: E402
from vhrs_calib.truth import TruthConfig, make_truth  # noqa: E402
from vhrs_calib.workspace import BALL_TOOL_FLANGE, PEN_TOOL_FLANGE, CollectConfig, collect_socket_data, layout  # noqa: E402

LAYOUTS = ["S2", "S3", "S3L", "S2x2"]
CONES = [2.0, 5.0, 10.0, 20.0, 30.0, 45.0]
SEEDS = list(range(500, 510))
N_TOTAL = 60


def main() -> None:
    sc = Scene()
    tcfg = TruthConfig(harmonic_amp_deg=0.0, use_compliance=False)
    rows, null_example = [], None
    t0 = time.time()
    for seed in SEEDS:
        tr = make_truth(seed, tcfg, BALL_TOOL_FLANGE, PEN_TOOL_FLANGE)
        th = theta_of(tr.arm.origins, tr.ball_tool_flange, BALL_TOOL_FLANGE)
        for name in LAYOUTS:
            lay = layout(name, sc.paper)
            per = N_TOTAL // len(lay.centres)
            for cone in CONES:
                ccfg = CollectConfig(cone_deg=cone, sigma_seat_mm=0, sigma_q_deg=0, sigma_d_mm=0)
                data, _ = collect_socket_data(rng_for(seed, 60, int(cone * 10)), tr.ball(), lay, per, sc.R_w, sc.q_seed, ccfg)
                ob = observability(data, th, BALL_TOOL_FLANGE)
                s = ob["singular_values"]
                rows.append({"seed": seed, "layout": name, "cone_deg": cone, "n_total": per * len(lay.centres), "rank": ob["rank"],
                             "n_unidentifiable": ob["n_unidentifiable"], "sigma_max": float(s[0]),
                             "sigma_min_identifiable": ob["sigma_min_identifiable"], "cond": ob["cond"],
                             "sv": ";".join(f"{v:.6e}" for v in s)})
                if null_example is None and name == "S3" and cone == 30.0:
                    N = ob["null_space"]
                    null_example = {"seed": seed, "layout": name, "cone_deg": cone,
                                    "param_null_fraction": {PARAM_NAMES[j]: float(np.linalg.norm(N[:, j])) for j in range(39)}}
        print(f"seed {seed} done ({time.time() - t0:.0f} s)", flush=True)
    out = ROOT / "results" / "raw"
    with open(out / "obs_observability.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    meta = metadata("OBS", {"layouts": LAYOUTS, "cones_deg": CONES, "n_total": N_TOTAL, "truth": "geometric only, no noise"}, SEEDS,
                    {"null_space_example": null_example, "rank_tol": 1e-6, "param_units": "mm, mrad"})
    (out / "obs_observability_meta.json").write_text(json.dumps(to_jsonable(meta), indent=1))


if __name__ == "__main__":
    main()
