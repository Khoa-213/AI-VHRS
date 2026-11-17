# Reproducibility

All commands are run from `research/ieee_robot_calibration/` unless stated. Windows paths shown; on Linux replace
`Scripts/python.exe` by `bin/python`.

## Environments used (2026-11-17)

| Environment | Used for | Versions |
|---|---|---|
| System Python | framework, experiments, tests, analysis | Python 3.11.9, NumPy, SciPy 1.17.1, Matplotlib 3.10.9, pytest |
| `BE/.venv` (existing AI-VHRS backend venv) | only `scripts/export_strokes.py` (needs HersheyFonts + BE code) | as installed by BE |
| `robot_agent/.simenv` (existing) | only `scripts/validate_pybullet.py` (needs PyBullet) | as installed by robot_agent |
| `tools/tectonic.exe` | LaTeX build | tectonic 0.17.0 (XeTeX engine) |

Hardware: Windows 11, 12 worker processes (`pool_map` in `experiments/runner.py`). Results do not depend on the worker count:
every trial derives its random streams from `numpy.random.SeedSequence(seed, tags...)` (`pipeline.rng_for`).

None of the commands below contacts the robot, the backend server or Supabase.

## Pipeline

```bash
# 1. Handwriting test set (reads BE code, writes data/strokes.json; already present)
../../BE/.venv/Scripts/python.exe scripts/export_strokes.py

# 2. Model validation
python scripts/validate_urdf_vs_controller.py          # uses stored controller readings in robot_agent/runs
../../robot_agent/.simenv/python.exe scripts/validate_pybullet.py
python -m pytest -q tests                              # 14 tests

# 3. Experiments
python experiments/obs_observability.py                # OBS, seeds 500-509
python experiments/runner.py e1                        # seeds 1000-1029
python experiments/runner.py e5                        # seeds 1000-1029
python experiments/runner.py e2                        # seeds 2000-2019 (also writes e2_handwriting_page.csv)
python experiments/runner.py e2b
python experiments/runner.py e3
python experiments/runner.py e4

# 4. Statistics, tables, figures (writes results/processed, results/figures, paper/tables, paper/figures)
python analysis/analyze.py

# 5. Paper
cd paper && ../tools/tectonic.exe -X compile main.tex --keep-logs && cp main.pdf AI_VHRS_IEEE_Paper.pdf
```

## Seeds and sizes

| Experiment | Seeds | Units | Rows |
|---|---|---|---|
| OBS | 500–509 | 4 layouts × 6 tilt cones × 10 robots | 240 |
| E1 | 1000–1029 | 30 robots × 5 models | 150 |
| E5 | 1000–1029 | 30 robots × 6 methods × 10 samples | 1,800 |
| E2 | 2000–2019 | 20 robots per setting | 1,040 (+1,560 full-page rows) |
| E2b | 2000–2019 | λ ablation | 640 |
| E3 | 2000–2019 | sample count N | 480 |
| E4 | 2000–2019 | spacing and tilt cone | 700 |

Bootstrap: 10,000 resamples, seed 12345. All rows have `status = ok`; zero IK failures in E5.

## Provenance

Each `results/raw/*_meta.json` records the configuration, seeds, git HEAD of the repository at run time (`89ad8e3`, branch
`BE`, with uncommitted BE changes from other work that this study does not read), Python/NumPy/SciPy versions and SHA-256
hashes of the `src/vhrs_calib` sources. `data/strokes.json` records the generator path and the hash of `text_to_stroke.py`.

## Known non-determinism

None observed: re-running a trial with the same seed reproduces the row exactly (test `test_trials_are_reproducible`). Solver timings
(`solve_s`) vary with machine load and are the only non-reproducible column.
