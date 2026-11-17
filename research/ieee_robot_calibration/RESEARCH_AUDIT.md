# Research audit

Date: 2026-11-17. Repository HEAD `89ad8e3` (branch `BE`). Audit was read-only; nothing outside
`research/ieee_robot_calibration/` was modified.

## 1. What the AI-VHRS repository provides for this study

| Item | Location | Used as |
|---|---|---|
| FR3 V6 vendor URDF | `robot_agent/vendor/fr3/fairino3_v6.urdf` | nominal kinematic model |
| Robot / controller version | robot_agent docs and project memory: FR3 V6.0, controller V3.8.25-QX | context; the controller is closed (no custom kinematic model can be uploaded) |
| Read-only controller readings | `robot_agent/runs/robot_inspection.json`, `robot_inspection_20261025.json` | validation of the nominal model + 100 mm flange offset |
| Paper probe points (A4) | `robot_agent/calibration.json` → `probe_points` | paper pose in the simulation |
| Pen tool offset | (0, 0, 179.62) mm in flange frame (stored TCP offset) | pen and ball tool nominal |
| Paper-frame construction | `BE/app/services/motion/frame.py` `build_frame` (Gram–Schmidt of 3 probes) | re-implemented and tested equal |
| Handwriting generator | `BE/app/services/stroke_ai/text_to_stroke.py` (Hershey single-line) | Vietnamese test set |
| Quality metrics | `BE/app/services/quality_eval.py` (Service G: Chamfer, HD95, Hausdorff) | same definitions on vector paths |
| PyBullet sim | `robot_agent/.simenv` | independent FK/IK cross-check |

What the repository does **not** contain: any absolute-accuracy measurement of the FR3 (laser tracker, CMM, ballbar), any
socket fixture, any measurement of joint stiffness, gear error or backlash, or any written-sample accuracy measurement with
a reference scan. Current practice (method B) is: nominal controller model + 3-point paper probing.

## 2. MUKCa verification

Verified from the primary sources (Crossref metadata and the publisher/arXiv pages, checked 2026-11-17):

* G. Franzese, M. Spahn, J. Kober, J. Alonso-Mora, C. Della Santina, "Accurate and affordable cobot calibration without
  external measurement devices", *Communications Engineering* 5, 138 (2026), doi:10.1038/s44172-026-00633-4.
* Preprint arXiv:2503.12584 (2025); code `platonics-delft/kinematics_calibration` (MIT).

What MUKCa does (as relevant here): a 3D-printable tool with two sockets at a known distance; a ball-tipped end effector is
placed in each socket in many configurations; the URDF joint origins (and ball offset) are identified by making the predicted
ball centre consistent within each socket while matching the known distance, with a regulariser towards the nominal model.
The paper reports mean absolute error reductions on Franka cobots from about 10 mm to about 0.2 mm. Stated assumptions
include kinematic redundancy (null-space motion provides configuration diversity) and negligible joint-angle error; backlash
is reported as a failure mode. MUKCa mentions more sockets / multiple placements as possible alternatives.

## 3. Transfer to the 6-DOF FR3

| Question | Finding (simulation) |
|---|---|
| Redundancy | FR3 is not redundant. With the ball centre pinned, the only freedom is tool orientation (3-DOF), which still gives a 3-DOF family of configurations per socket. MUKCa's redundancy assumption is not required for identifiability. |
| Identifiable rank | 21/39 for every layout and tilt cone — equals 4R + 6 − 3 − 6 for position-only, base-free data. |
| Jacobian rank deficiency | 18 directions: 6 base gauge + couplings (all of joint 1, j2.z, j2.yaw, j6.pitch fully in the null space). |
| Gauge | Base-frame rigid motion is unobservable by construction (no socket position in the base frame). For writing, it is absorbed by paper probing. |
| Closed controller | Calibrated model cannot be installed → targets are pre-compensated (Methodology §4). |

## 4. Novelty assessment (honest)

* **Not new**: socket/sphere and distance constraints for calibration (Joubair & Bonev 2015; Nubiola & Bonev ballbar 2014;
  Petrič & Žlajpah 2023; Nadeau et al. 2019); the MUKCa objective; the identifiable-parameter count; the idea of using more
  sockets (mentioned by MUKCa); target pre-compensation for closed controllers (common practice in industrial error
  compensation, e.g. Liao et al. 2023).
* **Plausibly new (to be confirmed by a wider literature search before submission)**: (1) a quantitative identifiability and
  conditioning study of the MUKCa formulation on a non-redundant 6-DOF cobot; (2) an equal-budget comparison of two-socket,
  collinear three-socket, triangular three-socket and two-placement layouts with an explanation via observability and
  regularisation bias; (3) end-to-end evaluation on Vietnamese handwriting trajectories with closed-controller
  pre-compensation and paper probing.
* Contribution type: engineering/analysis study in simulation. It is a workshop/conference-level contribution until real-robot
  validation is done.

## 5. Literature verification

All 26 entries in `paper/references.bib` were checked against Crossref or the publisher/repository page on 2026-11-17
(`scripts/crossref_lookup.py`); Holm 1979 has no DOI (JSTOR). No reference was added from memory without a lookup.
A systematic literature search (e.g. Scopus/IEEE Xplore queries for "socket calibration", "sphere constraint", "6-DOF
cobot", "robot handwriting accuracy") was **not** done; see `PAPER_REVIEW_CHECKLIST.md`.
