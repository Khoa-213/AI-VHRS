# Limitations and threats to validity

1. **Simulation only.** Every accuracy figure is for simulated robots whose error sources and magnitudes were chosen by us
   (`configs/default.json`). Simulated accuracy ≠ physical accuracy. The real FR3's absolute error is unknown.
2. **Ground truth shares structure with the model.** Geometric errors live in the same URDF parameterisation the solver
   identifies. Unmodelled terms (harmonic gear error, gravity compliance) are included but small and of assumed magnitude.
   Not modelled: backlash, hysteresis, thermal drift, encoder eccentricity, link flexibility beyond lumped joint stiffness,
   socket/ball form error, dynamic tracking error, controller interpolation, latency.
3. **Assumed magnitudes.** σ = 0.5 mm / 0.1° geometry, 0.003° harmonic, stiffness 1–3·10⁴ N·m/rad, payload 0.6 kg, seating
   0.02 mm, encoder 0.001°, probe 0.1 mm in-plane. E2 varies these, but conclusions outside the tested ranges are untested.
4. **Ball seating model.** Seating is modelled as isotropic Gaussian noise; real sockets may have systematic seating bias
   depending on approach direction and contact force (FR3 is not torque-controlled in this workflow, so seating must be done
   by hand-guiding or careful position moves).
5. **Reachability.** Tilt cone (30°) and spin (±60°) are achievable in simulation with joint-limit margins; real cable,
   pen-holder and socket collisions are not modelled. E4 shows accuracy falls at small cones.
6. **Gauge.** The base frame is not identified; the method relies on paper probing to absorb it. Tasks that need absolute
   base-frame accuracy are not covered.
7. **Regularisation choice.** λ = 1e-4 follows MUKCa; E2b shows smaller λ is better in simulation, but λ cannot be tuned on a
   real robot without ground truth. Part of the S2-vs-S3 gap at λ = 1e-4 is regulariser bias.
8. **Handwriting data.** Samples are font-generated single-line glyphs from the AI-VHRS pipeline, not human handwriting; ink,
   paper deformation, pen compliance and stroke-speed effects are not simulated. Contact ratio is a geometric proxy.
9. **Statistics.** 30 robots (E1/E5) and 20 robots (E2–E4) per setting; significance is with respect to the simulated
   population only. Several comparisons are not significant (S3L vs S2; D vs E and D vs O on MAE) and are reported as such.
10. **Optimiser.** SciPy LM instead of MUKCa's Ipopt/CasADi; the objective is the same, but solver differences could matter
    for badly conditioned real data.
11. **Single robot model.** Only the FR3 V6 geometry was studied.
12. **Paper length.** The manuscript is 8 pages; the requested target was 4–6 pages (see checklist).
