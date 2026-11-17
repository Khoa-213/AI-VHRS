# Experiment results (simulation only)

Source of every number: `results/raw/*.csv` → `analysis/analyze.py` → `results/processed/statistics.json` and
`results/processed/*_summary.csv`. All experiments listed here were **run to completion** on 2026-11-17; every row has
`status = ok`; no trial was excluded. None of these numbers is a measurement on the real FR3.

| ID | Question | Status |
|---|---|---|
| OBS | Identifiability of the 39-parameter model from socket data | completed (240 rows) |
| E1 (P0) | TCP accuracy after calibration | completed (30 robots) |
| E5 (P0) | Handwriting trajectory accuracy with pre-compensation | completed (30 robots × 10 samples) |
| E2 | Robustness to noise, unmodelled errors, error magnitude | completed (20 robots/setting) |
| E2b | Regularisation λ ablation | completed |
| E3 | Sample count N | completed |
| E4 | Socket spacing and tilt cone | completed |

## OBS — identifiability

* Numerical rank = **21 of 39** for every layout (S2, S3L, S2x2, S3), every tilt cone (2°–45°) and all 10 robots. This equals the
  classical count 4R + 6 − 3 − 6 = 21 for position-only, base-free measurements of a 6R arm with an unknown tool.
* Fully unidentifiable: the 6 parameters of joint 1, plus j2.z, j2.yaw and j6.pitch (base gauge and parameter couplings).
* Adding sockets **does not raise the rank**; it raises the conditioning of the identifiable subspace. At 30° cone,
  O1 (×10⁻³): S2 37.8, S3L 39.1, S3 60.7, S2x2 62.3; geometric mean of the 6 weakest identifiable singular values (×10⁻³):
  1.29, 1.35, 2.75, 2.79.

## E1 — calibration accuracy (30 robots, seeds 1000–1029, 500 test poses each)

| Model | Aligned RMSE (mm) | 95% CI | Aligned P95 | Raw mean error | Rel. param. error |
|---|---|---|---|---|---|
| Nominal | 0.748 ± 0.260 | 0.658–0.841 | 1.260 | 2.914 | 1.00 |
| S2 (MUKCa) | 0.109 ± 0.045 | 0.093–0.125 | 0.188 | 1.485 | 0.67 |
| S3L | 0.109 ± 0.051 | 0.092–0.127 | 0.188 | 1.503 | 0.67 |
| S2x2 | 0.049 ± 0.011 | 0.045–0.053 | 0.081 | 1.286 | 0.52 |
| S3 (triangle) | **0.044 ± 0.005** | 0.042–0.046 | 0.074 | 1.282 | 0.52 |

(Other metrics: `statistics.json` → `e1_summary`.)

Paired tests (aligned RMSE, Holm-corrected):

| Comparison | Change of means | Win rate | p_Holm |
|---|---|---|---|
| S2 vs nominal | −85% | 30/30 | 1.3e-8 |
| S3 vs S2 | −60% | 28/30 | 5.2e-8 |
| S2x2 vs S2 | −55% | 27/30 | 7.8e-8 |
| S3 vs S3L | −60% | 29/30 | 1.9e-8 |
| S3 vs S2x2 | −10% | 21/30 | 0.039 |
| S3L vs S2 | +0.3% | 12/30 | **0.78 (n.s.)** |

* Raw error stays at 1.3–1.5 mm after calibration because the base frame is unobservable; in the application this offset is
  absorbed by paper probing (see E5).
* Relative parameter error in the identifiable subspace remains 52–67%: the TCP improves much more than individual parameters.
* Solver: 25–34 function evaluations, 0.4–0.7 s per solve. Rejected draws (joint limits): S3 81, S2x2 109, S2/S3L 0.
* **Failure cases**: S3 was worse than S2 on 2/30 robots (seeds 1009 and 1027).

## E5 — handwriting accuracy (30 robots × 10 samples, 9,321 points per robot)

| Method | MAE (mm) | Shape MAE | HD95 | Contact @0.3 mm |
|---|---|---|---|---|
| A nominal + ideal paper frame | 2.516 | 0.234 | 2.307 | 75.2% |
| B nominal + probed frame (current practice) | 0.796 | 0.233 | 0.921 | 100% |
| C S2 + pre-comp | 0.180 | 0.037 | 0.206 | 100% |
| E S2x2 + pre-comp | 0.145 | 0.014 | 0.161 | 100% |
| D S3 + pre-comp | 0.150 | **0.010** | 0.164 | 100% |
| O oracle + pre-comp | 0.141 | 0.000 | 0.153 | 100% |

Paired tests (Holm within metric):

* MAE: C vs B −77% (p = 3.7e-8); D vs B −81% (p = 1.9e-8); D vs C −16.7%, win 21/30, p = 0.028; D vs E +3.5%, p = 0.62
  (n.s.); D vs O p = 0.62 (n.s.).
* Shape MAE: D vs C −72%, win 28/30, p = 1.6e-7; D vs E −27%, win 20/30, p = 0.007.
* HD95: D vs C −20%, p = 0.0016; D vs E p = 0.50 (n.s.).
* Zero IK failures. Method A lost contact (at 0.3 mm press) in 99 sample rows; no other method lost contact.

Interpretation: paper probing (B) removes most of the placement error but cannot remove distortion (shape MAE unchanged
from A). Calibration + pre-comp removes the distortion. Remaining MAE ≈ 0.14 mm is the oracle floor set by probing noise.

**Failure cases**: seed 1004 — C's shape error (0.073) was worse than B's (0.067); seed 1021 — B's MAE (0.196) was lower than
D (0.253) and O (0.262), because probing noise happened to cancel that robot's error better than a correct model.
Worst single rows: A 6.08 mm max (seed 1017, sentence); B 3.43 mm (1014, diagonal line); C 0.62 mm (1012, sentence);
D 0.42 mm (1012, diagonal); O 0.38 mm (1012, diagonal).

## E2 — robustness (20 robots/setting, seeds 2000–2019, aligned RMSE in mm)

| Setting | Nominal | S2 | S2x2 | S3 |
|---|---|---|---|---|
| noise ×0 | 0.708 | 0.119 | 0.039 | 0.034 |
| noise ×1 (default) | 0.708 | 0.123 | 0.045 | 0.042 |
| noise ×4 | 0.710 | 0.165 | 0.101 | 0.104 |
| noise ×8 | 0.717 | 0.258 | **0.189** | 0.199 |
| no unmodelled errors | 0.720 | 0.112 | 0.036 | 0.031 |
| stiffness ×0.5 | 0.707 | 0.145 | 0.065 | 0.064 |
| geometry ×0.5 | 0.389 | 0.077 | 0.039 | 0.039 |
| geometry ×2 | 1.388 | 0.226 | 0.065 | 0.054 |
| geometry ×4 | 2.778 | 0.438 | 0.111 | 0.086 |

* The S3 advantage shrinks with measurement noise; at ×4 and ×8 S2x2 is equal or slightly better than S3.
* S2's error grows with the geometric error magnitude (regularisation bias, see E2b); S3 is far less affected.
* Full page under each setting (`e2_handwriting_page.csv`): at geometry ×4, B MAE 2.42 mm with 78.9% contact; D 0.146 mm with
  100%. At noise ×8, E (0.194) beat D (0.213).

## E2b — regularisation λ (aligned RMSE, mm)

| λ | S2 default | S3 default | S2 clean | S3 clean |
|---|---|---|---|---|
| 1e-8 | 0.088 | 0.039 | 0.0003 | 0.0001 |
| 1e-6 | 0.083 | 0.039 | 0.016 | 0.0005 |
| 1e-4 (MUKCa) | 0.123 | 0.042 | 0.107 | 0.020 |
| 1e-2 | 0.209 | 0.137 | 0.205 | 0.133 |

("clean" = no noise, no unmodelled error.) At MUKCa's λ, much of the S2 deficit is regularisation bias along weakly excited
directions; with λ ≤ 1e-6 S2 improves to 0.083–0.088 mm, still ~2× worse than S3. λ = 1e-6 was better than 1e-4 for every
layout in this simulation, but the paper keeps 1e-4 because λ cannot be tuned without ground truth on a real robot.

## E3 — sample count (aligned RMSE, mm)

| N | S2 | S2x2 | S3 |
|---|---|---|---|
| 12 | 0.146 | 0.087 | 0.068 |
| 24 | 0.129 | 0.055 | 0.048 |
| 60 | 0.123 | 0.045 | 0.042 |
| 150 | 0.116 | 0.042 | 0.040 |

S3 with 12 samples beats S2 with 150.

## E4 — socket geometry (aligned RMSE, mm)

| Spacing (mm) | 50 | 100 | 150 | 200 | 250 |
|---|---|---|---|---|---|
| S2 | 0.125 | 0.123 | 0.123 | 0.124 | 0.125 |
| S3L | 0.114 | 0.112 | 0.106 | 0.099 | 0.095 |
| S3 | 0.067 | 0.049 | 0.042 | 0.039 | 0.038 |

| Tilt cone (°) | 5 | 10 | 20 | 30 | 45 |
|---|---|---|---|---|---|
| S2 | 0.209 | 0.184 | 0.138 | 0.123 | 0.090 |
| S3 | 0.110 | 0.079 | 0.052 | 0.042 | 0.037 |

S3 at a 10° cone already beats S2 at 45°. Larger tilt cones may be limited by the real socket/ball geometry and pen holder
(see `REAL_WORLD_VALIDATION_REQUIRED.md`).
