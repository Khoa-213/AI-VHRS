"""Nominal model vs the REAL controller's own kinematics, using read-only readings already stored in the repository
(robot_agent/runs/robot_inspection*.json: GetActualJointPosDegree + GetActualToolFlangePose + GetActualTCPPose + GetTCPOffset).
No robot is contacted. Fits the flange offset along wrist3 z and reports residuals. Writes results/processed/validation_controller.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))
from vhrs_calib.kinematics import KinModel, rpy_matrix  # noqa: E402


def main() -> None:
    rows = []
    for f in sorted((REPO / "robot_agent" / "runs").glob("robot_inspection*.json")):
        r = json.loads(f.read_text())["reads"]
        q = np.radians(r["GetActualJointPosDegree"][1])
        fl = np.array(r["GetActualToolFlangePose"][1])
        tcp = np.array(r["GetActualTCPPose"][1])
        tool = np.array(r["GetTCPOffset"][1])
        w3, Rw = KinModel(tool=np.zeros(3)).fk(q)                           # bare URDF wrist3 frame
        d_fit = float(np.dot(fl[:3] - w3[0], Rw[0][:, 2]))                  # offset along wrist3 z that best explains the flange
        Rc = rpy_matrix(*np.radians(fl[3:]))
        rot_err = float(np.degrees(np.arccos(np.clip((np.trace(Rc.T @ Rw[0]) - 1) / 2, -1, 1))))
        p100, _ = KinModel().fk(q)
        tcp_pred = fl[:3] + Rc @ tool[:3]
        rows.append({"file": f.name, "joints_deg": r["GetActualJointPosDegree"][1], "fitted_flange_offset_mm": d_fit,
                     "flange_pos_err_with_100mm_mm": float(np.linalg.norm(p100[0] - fl[:3])), "flange_rot_err_deg": rot_err,
                     "tcp_from_flange_plus_tool_err_mm": float(np.linalg.norm(tcp_pred - tcp[:3]))})
    out = {"source": "read-only controller readings stored in robot_agent/runs (FR3 V6.0, controller V3.8.25-QX)",
           "readings": rows,
           "conclusion": "The controller's reported flange pose equals the vendor-URDF wrist3 frame shifted by ~100 mm along its z "
                         "axis. This validates the NOMINAL model the controller uses; it says nothing about the robot's true "
                         "(absolute) accuracy, which needs an external reference."}
    (HERE / "results" / "processed").mkdir(parents=True, exist_ok=True)
    (HERE / "results" / "processed" / "validation_controller.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
