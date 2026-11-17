# Methodology

Simulation-only study. Units: mm, rad (deg where stated). Code references are to `src/vhrs_calib/`.

## 1. Robot and scene (module A — `kinematics.py`, `workspace.py`)

* **Nominal model**: FAIRINO FR3 V6 vendor URDF (`robot_agent/vendor/fr3/fairino3_v6.urdf`, from FAIR-INNOVATION/frcobot_ros2).
  Each joint *i* has a fixed origin transform (xyz, rpy) followed by `Rz(q_i)`. The controller's flange is the URDF `wrist3`
  frame shifted 100 mm along its z axis (`FLANGE_OFFSET_MM`).
* **Validation of the nominal model** (not of the robot's accuracy):
  * vs. the real controller: two read-only readings in `robot_agent/runs/robot_inspection*.json`
    (joint angles + controller-reported flange pose). Fitted flange offset 99.9997 / 100.0019 mm, residual 0.011 / 0.009 mm,
    0.0005° / 0.0003°.
  * vs. PyBullet loading the same URDF: max position difference 0.00076 mm over 2,000 random configurations; PyBullet IK
    solutions re-evaluated with our FK agree to 0.00036 mm.
* **Scene**: paper corners = `robot_agent/calibration.json` `probe_points` (A4); pen/ball tool = (0, 0, 179.62) mm in the
  flange frame; writing orientation = flange orientation at the stored pen-down inspection pose.
* **FK/IK**: batched NumPy FK, geometric Jacobian, damped-least-squares IK (rotation weighted 500 mm/rad), joint limits from URDF.

## 2. Ground-truth robot (module B — `truth.py`)

Each trial seed draws an independent "true" robot. The solver never sees it (asserted in `pipeline.run_calibration`; test
`test_solver_never_sees_ground_truth`). Error sources (all **simulation assumptions**, `configs/default.json`):

| Source | Model | Default | Inside calibrated model class? |
|---|---|---|---|
| Joint origin geometry | Gaussian perturbation of all 36 xyz/rpy origin parameters | σ = 0.5 mm, 0.1° | yes |
| Ball / pen tool offset | Gaussian, per tool | σ = 0.3 mm | ball: yes (3 params); pen: handled by paper probing |
| Harmonic (gear) error | a·sin(q+φ) + b·sin(2q+ψ) per joint | amplitudes uniform in [0, 0.003°] | **no** |
| Gravity compliance | lumped link masses, payload 0.6 kg, joint stiffness K = (3,3,2,1,1,1)·10⁴ N·m/rad | — | **no** |

## 3. Calibration (module C — `calibrate.py`)

Parameters θ ∈ R³⁹: 36 origin parameters + 3 ball-offset parameters. For K sockets, socket k has N_k joint readings; μ_k is
the mean predicted ball centre. Objective (generalised MUKCa Eq. 5):

    J(θ) = (1/N) Σ_k Σ_j ‖f(q_kj; θ) − μ_k(θ)‖² + Σ_{(k,l)∈D} (‖μ_k − μ_l‖ − d_kl)² + λ ‖θ − θ_nom‖²

λ = 1e-4 in mm/mrad units (equivalent to MUKCa's 1e-4 in m/rad). Solved with SciPy `least_squares` (Levenberg–Marquardt,
x/f/g tolerances 1e-12). Socket positions in the base frame never enter the objective, so the six rigid base-frame motions are a
gauge freedom.

**Data collection model**: the ball sits in socket k; the tool axis is tilted inside a cone of half-angle 30° and spun ±60°
about it; joint-limit margin 5°; samples that violate limits are redrawn (counted as `rejected_draws`). Noise: seating
σ = 0.02 mm, encoder σ = 0.001°, socket-distance σ = 0.02 mm. N = 60 total samples, split evenly over sockets.

**Layouts** (equal N): S2 = MUKCa two-socket tool (150 mm); S3L = three collinear sockets (150 mm spacing); S3 = three sockets in
an equilateral triangle on the writing plane (150 mm sides); S2x2 = the two-socket tool at two placements (x and y), with one
distance per placement.

**Observability** (`observability`): identification Jacobian (central differences, h = 1e-6) evaluated at the true parameters
on noise-free, in-class data (zero residual). Rank via singular values with relative tolerance 1e-6. Index
O1 = geometric mean of the identifiable singular values (Borm & Menq). Evaluating at a non-zero residual makes the gauge
directions look weakly observable; this was a bug found during validation and fixed.

**Evaluation (E1)**: 500 test poses spread over the writing workspace (height 0–60 mm above the paper, tool cone 20°). TCP
error between calibrated-model prediction and true robot after a Kabsch rigid alignment (the base gauge is unobservable, so
the comparable quantity is shape of the error field). Raw (unaligned) error is also reported.

## 4. Closed-controller pre-compensation and paper registration (module D — `compensation.py`)

The FR3 controller runs IK with its own nominal model and cannot be reprogrammed. For a desired pen pose (x_d, R_d):

1. q* = IK_cal(x_d, R_d) with the calibrated model;
2. command (x_cmd, R_cmd) = FK_nom(q*);
3. the controller solves IK_nom(x_cmd, R_cmd) = q*, so the true robot reaches FK_true(q*) ≈ (x_d, R_d).

Paper frame: three probe touches at the paper corners (noise in-plane 0.1 mm, normal 0.02 mm, encoder 0.001°), frame built by
Gram–Schmidt exactly as AI-VHRS `build_frame` (test `test_paper_frame_equals_ai_vhrs_build_frame`). Probing uses the same
model as execution, so constant offsets cancel.

**Methods compared in E5**: A nominal model + ideal (true) paper frame; B nominal model + probed paper frame (current AI-VHRS
practice); C S2 calibration + pre-comp; D S3 + pre-comp; E S2x2 + pre-comp; O oracle (true model) + pre-comp — a lower bound
set by probing noise.

## 5. Handwriting test set (module E — `scripts/export_strokes.py`)

10 samples generated by the production AI-VHRS text-to-stroke code (Hershey single-line fonts) on the BE virtualenv:
straight lines (horizontal, vertical, diagonal), circles r = 5 and 80 mm, corners, Vietnamese characters with diacritics,
words, a sentence and a full page (632 strokes, 4,897 mm). They are **font-generated**, not human handwriting. Strokes are
resampled at 1 mm.

## 6. Metrics (module F — `metrics.py`)

In the paper plane: point-wise MAE, RMSE, P95, max; Chamfer, HD95 and Hausdorff (same definitions as AI-VHRS Service G,
`BE/app/services/quality_eval.py`, applied to vector paths, query spacing 0.1 mm, reference 0.01 mm); shape MAE/P95 after a
rigid 2-D best fit (removes placement error, keeps distortion); pen height h; contact ratio = share of points with
h ≤ press depth for press 0.3 mm and 1.0 mm.

## 7. Statistics (`analysis/analyze.py`)

Unit of analysis = one simulated robot (trial). Per-robot values are averaged over test poses / samples. Mean ± SD, median,
bootstrap 95% CI of the mean (10,000 resamples, seed 12345). Paired two-sided Wilcoxon signed-rank tests with Holm correction
within each family of comparisons; win rate = share of robots where method a beats b. Relative changes are of the means.
