"""Independent cross-check: numpy FK of vhrs_calib vs PyBullet FK of the vendor URDF, through AI-VHRS's own robot_agent module.

Run with the robot_agent simulation environment (it has PyBullet):
    ../../robot_agent/.simenv/python.exe scripts/validate_pybullet.py
Writes results/processed/validation_pybullet.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "robot_agent"))

from vhrs_agent.kinematics import FR3Kinematics  # noqa: E402  (AI-VHRS module, PyBullet DIRECT, no robot)

from vhrs_calib.kinematics import JOINT_LOWER, JOINT_UPPER, KinModel  # noqa: E402

TOOL_MM = 250.0


def main() -> None:
    kin = FR3Kinematics(tool_offset_mm=TOOL_MM)                       # pen tip = wrist3 origin + tool along wrist3 z
    ours = KinModel(tool=np.array([0.0, 0.0, TOOL_MM]))
    rng = np.random.default_rng(2026)
    q = rng.uniform(JOINT_LOWER, JOINT_UPPER, (2000, 6))
    pb = np.array([kin.fk(np.degrees(qi))[0] for qi in q])
    pb_axis = np.array([kin.fk(np.degrees(qi))[1] for qi in q])
    p, R = ours.fk(q)
    err = np.linalg.norm(p - pb, axis=1)
    ang = np.degrees(np.arccos(np.clip(np.einsum("ni,ni->n", R[:, :, 2], pb_axis), -1, 1)))
    # PyBullet's IK solution (AI-VHRS kinematics.ik, pen straight down) checked with our FK
    targets = np.stack([rng.uniform(-150, 100, 50), rng.uniform(220, 520, 50), rng.uniform(5, 60, 50)], 1)
    ik_err = []
    for t in targets:
        r = kin.ik(t)
        if r.joints_deg is not None:
            pt, _ = ours.fk(np.radians(r.joints_deg))
            ik_err.append(float(np.linalg.norm(pt[0] - t)))
    kin.close()
    out = {"n_random_configs": len(q), "fk_pos_err_mm": {"max": float(err.max()), "mean": float(err.mean())},
           "fk_tool_axis_err_deg": {"max": float(ang.max())}, "n_ik_targets": len(targets), "n_ik_solved": len(ik_err),
           "pybullet_ik_then_our_fk_err_mm": {"max": float(max(ik_err)), "mean": float(np.mean(ik_err))}}
    (HERE / "results" / "processed").mkdir(parents=True, exist_ok=True)
    (HERE / "results" / "processed" / "validation_pybullet.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
