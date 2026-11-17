# Real-world validation required

Nothing in this study has been measured on the physical FR3. Before any claim about physical accuracy, the parameters below
must be measured. **No step here may be run on the robot without the team's explicit approval, a safety check of the
workspace, reduced speed, and an operator at the emergency stop.** This file is a plan, not a record of work done.

Legend — Need: **M** must measure, **S** should measure, **C** confirm existing value.

| # | Parameter | Current value / source | Simulation assumption | Need | Measurement procedure | Unit | Equipment | Impact on conclusions |
|---|---|---|---|---|---|---|---|---|
| 1 | Absolute TCP accuracy of the uncalibrated FR3 over the writing workspace | unknown | nominal error RMSE 0.75 mm (from σ 0.5 mm / 0.1°) | M | Write a calibrated grid (e.g. 9×9 crosses, 20 mm pitch) on the A4 sheet with method B; scan at ≥1200 dpi; measure cross centres vs design after rigid fit | mm | flatbed scanner (calibrated scale), or a ruler/glass grid; ideally laser tracker | Sets whether calibration is even needed; scales all E1/E5 gains |
| 2 | Geometric error magnitude (σ of origins) | unknown | 0.5 mm, 0.1° | S | Inferred from #1 and from the calibrated parameter change after #6 | mm, deg | — | E2 shows S2 degrades with larger errors; choice of S2 vs S3 |
| 3 | Joint stiffness / gravity sag | unknown | K = (3,3,2,1,1,1)·10⁴ N·m/rad, payload 0.6 kg | S | Dial indicator on the pen holder; record deflection while adding known loads (0.5–2 kg) at 3–5 poses | mm/N, N·m/rad | dial indicator (0.01 mm), test masses | Unmodelled error floor; E2 "stiffness ×0.5" raises S3 RMSE from 0.042 to 0.064 mm |
| 4 | Harmonic / transmission error | unknown | ≤ 0.003° per joint | S | Not directly measurable without encoders on the output; bound via repeatability of #1 at different joint paths | deg | — | Unmodelled floor |
| 5 | Backlash / reversal error | unknown | not modelled | M | Approach the same point from ±x, ±y, ±z; dial indicator on a fixed block; difference = reversal error | mm | dial indicator, magnetic stand | MUKCa reports backlash as a failure mode; if > ~0.05 mm it dominates the S3 gain |
| 6 | Socket fixture geometry (distances d_kl) | fixture not built | 150 mm triangle, σ_d = 0.02 mm | M | Print/machine 3 sockets on one plate; measure centre distances with calipers using a ball in each socket | mm | 3D printer or CNC, Ø precision ball, digital caliper (0.01 mm) | Distance error enters as a scale error of the calibrated model |
| 7 | Ball tip diameter and roundness | not chosen | perfect sphere | M | Supplier certificate or micrometer at 3 orientations | mm | micrometer | Seating bias |
| 8 | Seating repeatability | unknown | σ = 0.02 mm | M | Seat the ball 20× in the same socket at the same orientation (hand-guiding or position moves); record controller FK of the ball centre; SD | mm | robot readout only (read-only queries) + socket | E2: S3 advantage vanishes at noise ×4–×8 |
| 9 | Achievable tilt cone and spin around a socket | unknown | 30° cone, ±60° spin | M | In PyBullet first, then at low speed with the real pen holder and cables, find the largest collision-free cone | deg | robot, socket fixture | E4: S3 at 10° ≈ 0.079 mm vs 0.042 mm at 30° |
| 10 | Encoder / readout resolution of `GetActualJointPosDegree` | readings show ~1e-5° digits | σ = 0.001° | C | 100 consecutive reads at rest; SD | deg | read-only SDK query | small |
| 11 | Flange offset 100 mm and TCP offset (0,0,179.62) | controller readings (fit 99.9997 / 100.0019 mm) | exact | C | Re-read `GetTCPOffset`; re-check after tool changes | mm | read-only SDK query | constant offsets cancel by probing, but ball/pen offset difference matters |
| 12 | Pen tip vs ball tip offset | not measured | pen and ball on the same nominal offset, each with σ 0.3 mm | M | Measure both tools in the holder with a height gauge / camera; or probe the paper with both | mm | height gauge or microscope camera | Pre-comp computed for the ball must transfer to the pen |
| 13 | Paper probing noise | unknown | 0.1 mm in-plane, 0.02 mm normal | M | Repeat 3-corner probing 10×; SD of corners | mm | robot + A4 sheet on the fixture | Oracle floor ≈ 0.14 mm in E5 is set by this |
| 14 | Paper flatness / deformation | assumed flat rigid plane | flat | S | Probe a 5×5 grid of heights | mm | robot probing | contact ratio, h |
| 15 | Pen compliance and press depth | press 0.3 / 1.0 mm in metrics | rigid pen | S | Measure line visibility vs commanded depth | mm | test sheet | contact ratio interpretation |
| 16 | Dynamic tracking error at writing speed | not modelled | static | M | Write circles r = 5 / 80 mm at production speed vs slow; compare scans | mm | scanner | could exceed the static gains at high speed |
| 17 | Thermal drift | not modelled | none | S | Repeat #1 cold and after 1 h of writing | mm | scanner | long sessions |
| 18 | Handwriting accuracy of methods B, C, D | simulated only | E5 | M | Write the 10 test samples with B, C, D on the same robot; scan; compute MAE/shape/HD95 with `metrics.py` on vectorised scans | mm | scanner, vectorisation | the main claim of the paper |

## Minimum physical protocol (proposal, to be approved by the supervisor)

1. Build the 3-socket plate (#6, #7) and measure distances.
2. Read-only checks (#10, #11) — no motion.
3. Low-speed seating repeatability (#8) and reachable cone (#9) with hand-guiding.
4. Collect N = 60 samples for S2 (two of the three sockets) and S3 on the same day; calibrate offline.
5. Write the test set with B, C, D (#18) and the grid (#1); scan; evaluate with this package.
6. Report physical results separately from simulation results.
