"""Independent ground-truth robots: the nominal FR3 with KNOWN, randomly drawn deviations the calibration never sees.

What a ground-truth robot contains (all magnitudes are SIMULATION ASSUMPTIONS, listed in configs/default.json and in
REAL_WORLD_VALIDATION_REQUIRED.md; none of them is a measurement of the workshop's FR3):

  geometric  every joint origin gets dx, dy, dz ~ N(0, sigma_p) mm and droll, dpitch, dyaw ~ N(0, sigma_r) (the yaw deviation is
             also the joint zero offset); this is the URDF parameterisation the calibration estimates.
  unmodelled (a) a periodic joint transmission error a_i sin(q_i + phi_i) + b_i sin(2 q_i + psi_i) per joint;
             (b) gravity compliance: link-side angle = encoder angle + tau_g(q) / K_i with a lumped-mass gravity model and joint
                 stiffness K_i. Neither term exists in the calibration model, so it cannot be fitted exactly (no inverse crime).
  tools      the calibration ball and the pen tip each get an offset error ~ N(0, sigma_tool) mm per axis.

The calibration code only receives joint readings, socket distances and the nominal model, never the objects created here.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vhrs_calib.kinematics import NOMINAL_ORIGINS, KinModel, gravity_torques


@dataclass
class TruthConfig:
    sigma_p_mm: float = 0.5
    sigma_r_deg: float = 0.1
    harmonic_amp_deg: float = 0.003      # per-joint amplitude, uniform in [0, value]
    stiffness_nm_per_rad: tuple = (3.0e4, 3.0e4, 2.0e4, 1.0e4, 1.0e4, 1.0e4)
    use_compliance: bool = True
    payload_kg: float = 0.6
    sigma_tool_mm: float = 0.3
    scale: float = 1.0                   # multiplies sigma_p and sigma_r (E2 sensitivity)


class JointError:
    """Link-side angle error that the calibration model does not contain."""

    def __init__(self, amp1, ph1, amp2, ph2, stiffness, compliance_model: KinModel | None, payload_kg: float):
        self.amp1, self.ph1, self.amp2, self.ph2 = amp1, ph1, amp2, ph2
        self.k = np.asarray(stiffness, float)
        self.cm = compliance_model
        self.payload = payload_kg

    def __call__(self, q: np.ndarray) -> np.ndarray:
        e = self.amp1 * np.sin(q + self.ph1) + self.amp2 * np.sin(2.0 * q + self.ph2)
        if self.cm is not None:
            e = e + gravity_torques(self.cm, q, self.payload) / self.k
        return e


@dataclass
class TruthRobot:
    arm: KinModel                     # true arm, tool = true calibration-ball offset (flange frame + 100 mm)
    ball_tool_flange: np.ndarray      # true ball centre in the flange frame (mm)
    pen_tool_flange: np.ndarray       # true pen tip in the flange frame (mm)
    delta_origins: np.ndarray         # the drawn geometric deviation (for parameter-error reporting only)
    seed: int

    def ball(self) -> KinModel:
        return self.arm.with_tool(self.ball_tool_flange)

    def pen(self) -> KinModel:
        return self.arm.with_tool(self.pen_tool_flange)


def make_truth(seed: int, cfg: TruthConfig, nominal_ball_flange: np.ndarray, nominal_pen_flange: np.ndarray) -> TruthRobot:
    rng = np.random.default_rng(seed)
    d = np.zeros((6, 6))
    d[:, :3] = rng.normal(0.0, cfg.sigma_p_mm * cfg.scale, (6, 3))
    d[:, 3:] = rng.normal(0.0, np.radians(cfg.sigma_r_deg) * cfg.scale, (6, 3))
    amp = np.radians(cfg.harmonic_amp_deg)
    a1, a2 = rng.uniform(0, amp, 6), rng.uniform(0, amp / 2, 6)
    p1, p2 = rng.uniform(-np.pi, np.pi, 6), rng.uniform(-np.pi, np.pi, 6)
    origins = NOMINAL_ORIGINS + d
    comp_model = KinModel(origins=origins.copy()) if cfg.use_compliance else None
    jerr = JointError(a1, p1, a2, p2, cfg.stiffness_nm_per_rad, comp_model, cfg.payload_kg)
    arm = KinModel(origins=origins, joint_error=jerr, name=f"truth-{seed}")
    ball = np.asarray(nominal_ball_flange, float) + rng.normal(0, cfg.sigma_tool_mm, 3)
    pen = np.asarray(nominal_pen_flange, float) + rng.normal(0, cfg.sigma_tool_mm, 3)
    return TruthRobot(arm=arm, ball_tool_flange=ball, pen_tool_flange=pen, delta_origins=d, seed=seed)
