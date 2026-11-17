"""Statistics, tables and figures from results/raw (nothing here creates data; it only reads simulation output).

    python analysis/analyze.py
Outputs: results/processed/*.json|csv, results/figures/*.pdf|png, paper/figures/*.pdf, paper/tables/*.tex
Statistics: per-trial values (one per simulated robot) -> mean, std, median, bootstrap 95% CI of the mean (10 000 resamples,
fixed seed); paired comparisons with the two-sided Wilcoxon signed-rank test, Holm-corrected within each family, plus the
fraction of trials in which the first method is better (win rate).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import wilcoxon  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
RAW, PROC, FIG = ROOT / "results" / "raw", ROOT / "results" / "processed", ROOT / "results" / "figures"
PFIG, PTAB = ROOT / "paper" / "figures", ROOT / "paper" / "tables"
for d in (PROC, FIG, PFIG, PTAB):
    d.mkdir(parents=True, exist_ok=True)

INK, INK2, GRID = "#1f1f1e", "#5f5e58", "#e4e3dd"
COL = {"nominal": "#eb6834", "B_nominal_probe": "#eb6834", "A_nominal_ideal_fixture": "#8a8983", "S2": "#2a78d6",
       "C_S2_precomp": "#2a78d6", "S3": "#1baf7a", "D_S3_precomp": "#1baf7a", "S2x2": "#eda100", "E_S2x2_precomp": "#eda100",
       "S3L": "#e87ba4", "O_oracle_precomp": "#1f1f1e"}
MARK = {"S2": "o", "S3": "s", "S2x2": "D", "S3L": "^", "nominal": "v"}
LBL = {"nominal": "Nominal", "S2": "2-socket", "S3": "3-socket (tri.)", "S2x2": "2-socket x2 pl.", "S3L": "3-socket (line)",
       "A_nominal_ideal_fixture": "A: nominal, ideal fixture", "B_nominal_probe": "B: nominal + probe",
       "C_S2_precomp": "C: 2-socket + PC", "D_S3_precomp": "D: 3-socket + PC", "E_S2x2_precomp": "E: 2-socket x2 + PC",
       "O_oracle_precomp": "O: oracle + PC"}
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"], "font.size": 8,
                     "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
                     "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False, "savefig.dpi": 300,
                     "pdf.fonttype": 42})
RNG = np.random.default_rng(12345)


def ci(x, n=10000):
    x = np.asarray(x, float)
    b = RNG.choice(x, (n, len(x)), replace=True).mean(1)
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def describe(x) -> dict:
    x = np.asarray(x, float)
    lo, hi = ci(x)
    return {"n": int(len(x)), "mean": float(x.mean()), "std": float(x.std(ddof=1)), "median": float(np.median(x)),
            "ci95_lo": lo, "ci95_hi": hi}


def holm(ps):
    order = np.argsort(ps)
    adj = np.empty(len(ps))
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = run
    return adj


def paired(df, a, b, col, key="seed", method_col="method"):
    pa = df[df[method_col] == a].set_index(key)[col]
    pb = df[df[method_col] == b].set_index(key)[col]
    j = pa.index.intersection(pb.index)
    d = pa[j] - pb[j]
    p = float(wilcoxon(pa[j], pb[j]).pvalue) if np.any(d != 0) else 1.0
    return {"a": a, "b": b, "metric": col, "n": int(len(j)), "mean_a": float(pa[j].mean()), "mean_b": float(pb[j].mean()),
            "median_diff": float(np.median(d)), "rel_change_of_means": float(pa[j].mean() / pb[j].mean() - 1.0),
            "win_rate_a": float(np.mean(d < 0)), "p_wilcoxon": p}


def family(df, pairs, col, **kw):
    res = [paired(df, a, b, col, **kw) for a, b in pairs]
    for r, p in zip(res, holm([r["p_wilcoxon"] for r in res])):
        r["p_holm"] = float(p)
    return res


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(FIG / f"{name}.png", bbox_inches="tight", dpi=200)
    shutil.copy(FIG / f"{name}.pdf", PFIG / f"{name}.pdf")
    plt.close(fig)


def fmt(v, d=3):
    return f"{v:.{d}f}"


def pval(p):
    return r"$<$0.001" if p < 1e-3 else f"{p:.3f}"


# ---------------------------------------------------------------------------------------------------------------- E1
def analyse_e1(out: dict) -> None:
    d = pd.read_csv(RAW / "e1_calibration.csv")
    out["e1_status"] = d["status"].value_counts().to_dict()
    ok = d[d.status == "ok"]
    methods = ["nominal", "S2", "S3L", "S2x2", "S3"]
    summ = {m: {c: describe(ok[ok.method == m][c]) for c in ["aligned_mean", "aligned_rmse", "aligned_p95", "aligned_max", "raw_mean",
                                                              "param_err_rel"]} for m in methods}
    out["e1_summary"] = summ
    out["e1_tests_rmse"] = family(ok, [("S2", "nominal"), ("S3", "nominal"), ("S3", "S2"), ("S3", "S2x2"), ("S3", "S3L"),
                                       ("S2x2", "S2"), ("S3L", "S2")], "aligned_rmse")
    out["e1_solver"] = {m: {"nfev_mean": float(ok[ok.method == m].nfev.mean()), "nfev_max": float(ok[ok.method == m].nfev.max()),
                            "consistency_rms_mm_mean": float(ok[ok.method == m].consistency_rms_mm.mean()),
                            "distortion_max_mm": float(ok[ok.method == m].distortion_max_mm.max()),
                            "solve_s_mean": float(ok[ok.method == m].solve_s.mean()),
                            "rejected_draws_total": int(ok[ok.method == m].rejected_draws.sum())} for m in methods[1:]}
    # Table II
    rows = []
    for m in methods:
        s = summ[m]
        rows.append(f"{LBL[m]} & {fmt(s['aligned_mean']['mean'])} & {fmt(s['aligned_rmse']['mean'])} $\\pm$ {fmt(s['aligned_rmse']['std'])}"
                    f" & [{fmt(s['aligned_rmse']['ci95_lo'])}, {fmt(s['aligned_rmse']['ci95_hi'])}] & {fmt(s['aligned_p95']['mean'])}"
                    f" & {fmt(s['aligned_max']['mean'])} \\\\")
    (PTAB / "table_e1.tex").write_text("\n".join(rows) + "\n", encoding="utf8")
    # Figure 3: per-trial RMSE strip + box
    fig, ax = plt.subplots(figsize=(3.45, 2.2))
    for i, m in enumerate(methods):
        v = ok[ok.method == m].aligned_rmse.values
        ax.boxplot(v, positions=[i], widths=0.5, showfliers=False, medianprops={"color": INK, "lw": 1.2},
                   boxprops={"color": INK2, "lw": 0.8}, whiskerprops={"color": INK2, "lw": 0.8}, capprops={"color": INK2, "lw": 0.8})
        jit = RNG.uniform(-0.17, 0.17, len(v))
        ax.scatter(i + jit, v, s=9, color=COL[m], marker=MARK[m], edgecolor="white", linewidth=0.4, zorder=3)
    ax.set_yscale("log")
    ax.set_xticks(range(len(methods)), [LBL[m].replace(" (", "\n(").replace(" x2", "\nx2") for m in methods], fontsize=7)
    ax.set_ylabel("TCP position RMSE (mm, log)")
    ax.set_title("E1: independent test set, 30 simulated robots", fontsize=8, color=INK)
    save(fig, "fig3_e1_calibration")


# ---------------------------------------------------------------------------------------------------------------- E5
E5M = ["A_nominal_ideal_fixture", "B_nominal_probe", "C_S2_precomp", "E_S2x2_precomp", "D_S3_precomp", "O_oracle_precomp"]


def analyse_e5(out: dict) -> None:
    d = pd.read_csv(RAW / "e5_handwriting.csv")
    out["e5_status"] = d["status"].value_counts().to_dict()
    out["e5_ik_fail_total"] = int(d["ik_fail"].sum())
    cols = ["mae", "rmse", "p95", "max", "chamfer", "hd95", "hausdorff", "shape_mae", "shape_p95", "h_mean", "h_absmax", "contact_0.3",
            "contact_1"]
    per_trial = d.groupby(["seed", "method"])[cols].mean().reset_index()          # average over the 10 samples, per robot
    per_trial.to_csv(PROC / "e5_per_trial.csv", index=False)
    out["e5_summary"] = {m: {c: describe(per_trial[per_trial.method == m][c]) for c in cols} for m in E5M}
    fam = [("B_nominal_probe", "A_nominal_ideal_fixture"), ("C_S2_precomp", "B_nominal_probe"), ("D_S3_precomp", "B_nominal_probe"),
           ("D_S3_precomp", "C_S2_precomp"), ("D_S3_precomp", "E_S2x2_precomp"), ("D_S3_precomp", "O_oracle_precomp")]
    out["e5_tests_mae"] = family(per_trial, fam, "mae")
    out["e5_tests_shape"] = family(per_trial, fam[1:5], "shape_mae")
    out["e5_tests_hd95"] = family(per_trial, fam[1:5], "hd95")
    # worst cases (failure analysis): largest per-sample errors per method
    worst = d.sort_values("max", ascending=False).groupby("method").head(1)[["method", "seed", "sample", "max", "mae", "h_absmax"]]
    out["e5_worst_case"] = worst.to_dict(orient="records")
    out["e5_contact_lost_rows"] = d[d["contact_0.3"] < 1.0].groupby("method").size().to_dict()
    # per-category table (mean over trials)
    cat = d.groupby(["sample", "method"])[["mae", "shape_mae", "hd95"]].mean().reset_index()
    cat.to_csv(PROC / "e5_per_sample.csv", index=False)
    # Table III
    rows = []
    for m in E5M:
        s = out["e5_summary"][m]
        rows.append(f"{LBL[m]} & {fmt(s['mae']['mean'])} & {fmt(s['p95']['mean'])} & {fmt(s['chamfer']['mean'])} & {fmt(s['hd95']['mean'])}"
                    f" & {fmt(s['shape_mae']['mean'])} & {fmt(s['h_absmax']['mean'], 2)} & {100 * s['contact_0.3']['mean']:.1f} \\\\")
    (PTAB / "table_e5.tex").write_text("\n".join(rows) + "\n", encoding="utf8")
    # per-sample shape table (supplementary, markdown)
    piv = d.pivot_table(index="sample", columns="method", values="shape_mae", aggfunc="mean")[E5M]
    piv.round(4).to_csv(PROC / "e5_shape_mae_by_sample.csv")
    piv2 = d.pivot_table(index="sample", columns="method", values="mae", aggfunc="mean")[E5M]
    piv2.round(4).to_csv(PROC / "e5_mae_by_sample.csv")
    fig_e5_paths()
    fig_e5_distribution(per_trial)


def _rigid2d(x: np.ndarray, d: np.ndarray) -> np.ndarray:
    ca, cb = x.mean(0), d.mean(0)
    U, _, Vt = np.linalg.svd((x - ca).T @ (d - cb))
    R = Vt.T @ np.diag([1.0, np.sign(np.linalg.det(Vt.T @ U.T))]) @ U.T
    return (x - ca) @ R.T + cb


def fig_e5_paths() -> None:
    """Figure 4: (a,b) absolute in-plane error along the A4 page for B and D, one simulated robot (seed 1000);
    (c) shape MAE per handwriting sample, mean over the 30 robots."""
    from vhrs_calib.pipeline import load_strokes
    z = np.load(next(RAW.glob("e5_paths_seed*.npz")))
    st = load_strokes()
    fig = plt.figure(figsize=(7.16, 2.45))
    gs = fig.add_gridspec(1, 5, width_ratios=[1, 1, 0.05, 0.42, 1.25], wspace=0.3)
    des_page = np.concatenate(st["page"]["strokes"])
    vmax = 1.2
    for k, meth in enumerate(["B_nominal_probe", "D_S3_precomp"]):
        ax = fig.add_subplot(gs[0, k])
        ex = z[f"page__{meth}"]
        e = np.linalg.norm(ex[:, :2] - des_page, axis=1)
        sc = ax.scatter(des_page[:, 0], des_page[:, 1], c=e, s=0.6, cmap="viridis", vmin=0, vmax=vmax, rasterized=True)
        ax.set_xlim(0, 210)
        ax.set_ylim(160, 0)
        ax.set_aspect("equal")
        ax.grid(False)
        ax.set_title(f"({'ab'[k]}) {LBL[meth]}\nmean {e.mean():.2f} mm, max {e.max():.2f} mm", fontsize=7, color=INK)
        ax.set_xlabel("u (mm)")
        if k == 0:
            ax.set_ylabel("v (mm)")
    cax = fig.add_subplot(gs[0, 2])
    cb = fig.colorbar(sc, cax=cax)
    cb.set_label("abs. in-plane error (mm)", fontsize=7)
    ax = fig.add_subplot(gs[0, 4])
    d = pd.read_csv(RAW / "e5_handwriting.csv")
    piv = d.pivot_table(index="sample", columns="method", values="shape_mae", aggfunc="mean")
    order = ["chars", "words", "sentence", "line_h", "line_v", "line_d", "circle_r5", "circle_r80", "corners", "page"]
    names = {"chars": "characters", "words": "words", "sentence": "sentence", "line_h": "line (horiz.)", "line_v": "line (vert.)",
             "line_d": "line (diag.)", "circle_r5": "circles r=5", "circle_r80": "circle r=80", "corners": "corners",
             "page": "full page"}
    y = np.arange(len(order))
    for meth in ["B_nominal_probe", "C_S2_precomp", "E_S2x2_precomp", "D_S3_precomp"]:
        ax.scatter(piv.loc[order, meth], y, s=14, color=COL[meth], marker={"B_nominal_probe": "v", "C_S2_precomp": "o",
                   "E_S2x2_precomp": "D", "D_S3_precomp": "s"}[meth], edgecolor="white", lw=0.4, label=LBL[meth], zorder=3)
    ax.set_yticks(y, [names[o] for o in order], fontsize=6.5)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("shape MAE (mm, log)")
    ax.set_title("(c) letter-shape distortion by sample", fontsize=7, color=INK)
    ax.legend(loc="upper center", fontsize=6, ncol=2, bbox_to_anchor=(0.4, -0.27), handletextpad=0.2, columnspacing=0.8)
    save(fig, "fig4_e5_trajectories")


def fig_e5_distribution(pt: pd.DataFrame) -> None:
    fig, axs = plt.subplots(1, 2, figsize=(3.45, 2.0), gridspec_kw={"wspace": 0.55})
    ms = E5M[1:]
    for ax, col, ttl in [(axs[0], "mae", "abs. in-plane MAE"), (axs[1], "shape_mae", "shape MAE (rigid-aligned)")]:
        for i, m in enumerate(ms):
            v = pt[pt.method == m][col].values
            ax.boxplot(v, positions=[i], widths=0.55, showfliers=False, medianprops={"color": INK, "lw": 1.0},
                       boxprops={"color": INK2, "lw": 0.7}, whiskerprops={"color": INK2, "lw": 0.7}, capprops={"color": INK2, "lw": 0.7})
            ax.scatter(i + RNG.uniform(-0.18, 0.18, len(v)), v, s=6, color=COL[m], edgecolor="white", linewidth=0.3, zorder=3)
        ax.set_xticks(range(len(ms)), [LBL[m].split(":")[0] for m in ms])
        ax.set_title(ttl, fontsize=7.5, color=INK)
        ax.set_ylabel("mm")
        if col == "shape_mae":
            ax.set_yscale("symlog", linthresh=0.01)
    save(fig, "fig5a_e5_distribution")


# ---------------------------------------------------------------------------------------------------------------- OBS
def analyse_obs(out: dict) -> None:
    d = pd.read_csv(RAW / "obs_observability.csv")
    sv = d.apply(lambda r: np.array([float(x) for x in r.sv.split(";")])[: r["rank"]], axis=1)
    d["O1"] = [float(np.exp(np.mean(np.log(s)))) for s in sv]                  # geometric mean of identifiable singular values
    d["weak6"] = [float(np.exp(np.mean(np.log(s[-6:])))) for s in sv]          # geometric mean of the 6 weakest
    g = d.groupby(["layout", "cone_deg"]).agg(rank_min=("rank", "min"), rank_max=("rank", "max"),
                                             smin_med=("sigma_min_identifiable", "median"), cond_med=("cond", "median"),
                                             O1_med=("O1", "median"), weak6_med=("weak6", "median")).reset_index()
    rows = []
    for name in ["S2", "S3L", "S2x2", "S3"]:
        r = g[(g.layout == name) & (g.cone_deg == 30.0)].iloc[0]
        rows.append(f"{LBL[name]} & {int(r.rank_min)} & {r.O1_med * 1e3:.1f} & {r.weak6_med * 1e3:.2f} & {r.smin_med * 1e3:.3f} \\\\")
    (PTAB / "table_obs.tex").write_text("\n".join(rows) + "\n", encoding="utf8")
    g.to_csv(PROC / "obs_summary.csv", index=False)
    out["obs_rank_values"] = sorted(d["rank"].unique().tolist())
    out["obs_summary"] = g.to_dict(orient="records")
    meta = json.loads((RAW / "obs_observability_meta.json").read_text())
    nf = meta["null_space_example"]["param_null_fraction"]
    out["obs_fully_unidentifiable_params"] = [k for k, v in nf.items() if v > 0.999]
    out["obs_fully_identifiable_params"] = [k for k, v in nf.items() if v < 1e-3]


# ---------------------------------------------------------------------------------------------------------------- E2-E4
def sens_curve(ax, d, tags, xs, methods, col="aligned_rmse", xlabel="", logy=True, logx=False):
    for m in methods:
        mu, lo, hi = [], [], []
        for t in tags:
            v = d[(d.tag == t) & (d.method == m) & (d.status == "ok")][col].values
            s = describe(v)
            mu.append(s["mean"])
            lo.append(s["ci95_lo"])
            hi.append(s["ci95_hi"])
        ax.plot(xs, mu, color=COL[m], marker=MARK[m], ms=4, lw=1.2, label=LBL[m])
        ax.fill_between(xs, lo, hi, color=COL[m], alpha=0.15, lw=0)
    if logy:
        ax.set_yscale("log")
    if logx:
        ax.set_xscale("log")
    ax.set_xlabel(xlabel)


def analyse_sens(out: dict) -> None:
    have = {e: (RAW / f"{e}_sensitivity.csv").exists() for e in ("e2", "e2b", "e3", "e4")}
    out["sensitivity_available"] = have
    if not all(have.values()):
        return
    e2, e2b, e3, e4 = (pd.read_csv(RAW / f"{e}_sensitivity.csv") for e in ("e2", "e2b", "e3", "e4"))
    for name, d in (("e2", e2), ("e2b", e2b), ("e3", e3), ("e4", e4)):
        out[f"{name}_status"] = d["status"].value_counts().to_dict()
        tab = d[d.status == "ok"].groupby(["tag", "method"])["aligned_rmse"].agg(["mean", "std", "median", "count"]).reset_index()
        tab.to_csv(PROC / f"{name}_summary.csv", index=False)
        out[f"{name}_summary"] = tab.to_dict(orient="records")
    # E2 handwriting under noise / error magnitude
    hp = pd.read_csv(RAW / "e2_handwriting_page.csv")
    out["e2_page_status"] = hp["status"].value_counts().to_dict()
    tabh = hp.groupby(["tag", "method"])[["mae", "shape_mae", "h_absmax", "contact_0.3"]].mean().reset_index()
    tabh.to_csv(PROC / "e2_page_summary.csv", index=False)
    out["e2_page_summary"] = tabh.to_dict(orient="records")

    fig, axs = plt.subplots(1, 4, figsize=(7.16, 1.95), gridspec_kw={"wspace": 0.42})
    ks = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0]
    sens_curve(axs[0], e2, [f"noise_x{k:g}" for k in ks], [0.25] + ks[1:], ["S2", "S2x2", "S3"], xlabel="noise scale (x default)",
               logx=True)
    axs[0].set_xticks([0.25, 0.5, 1, 2, 4, 8], ["0", "0.5", "1", "2", "4", "8"])
    axs[0].set_ylabel("TCP RMSE (mm)")
    axs[0].set_title("(a) E2 measurement noise", fontsize=7.5, color=INK)
    ns = [12, 24, 36, 60, 90, 150]
    sens_curve(axs[1], e3, [f"n{n}" for n in ns], ns, ["S2", "S2x2", "S3"], xlabel="calibration samples N", logx=True)
    axs[1].set_xticks(ns, [str(n) for n in ns])
    axs[1].minorticks_off()
    axs[1].set_title("(b) E3 sample efficiency", fontsize=7.5, color=INK)
    sp = [50, 100, 150, 200, 250]
    sens_curve(axs[2], e4, [f"spacing_{s:g}" for s in sp], sp, ["S2", "S3L", "S3"], xlabel="socket spacing (mm)")
    axs[2].set_title("(c) E4 socket spacing", fontsize=7.5, color=INK)
    cones = [5, 10, 20, 30, 45]
    sens_curve(axs[3], e4, [f"cone_{c:g}" for c in cones], cones, ["S2", "S3"], xlabel="socket cone half-angle (deg)")
    axs[3].set_title("(d) E4 orientation range", fontsize=7.5, color=INK)
    for ax in axs:
        lo, hi = ax.get_ylim()
        ticks = [v for v in (0.03, 0.04, 0.05, 0.07, 0.1, 0.15, 0.2, 0.3) if lo <= v <= hi]
        ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
        ax.set_yticks(ticks, [f"{v:g}" for v in ticks])
    h, l = [], []
    for ax in axs:
        for hh, ll in zip(*ax.get_legend_handles_labels()):
            if ll not in l:
                h.append(hh)
                l.append(ll)
    fig.legend(h, l, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.13), fontsize=7)
    save(fig, "fig5_sensitivity")


# ---------------------------------------------------------------------------------------------------------------- Fig 2
def fig_layouts() -> None:
    from vhrs_calib.workspace import PAPER_H_MM, PAPER_W_MM, Paper, PAPER_CORNERS, layout
    paper = Paper.from_corners(PAPER_CORNERS)
    fig, axs = plt.subplots(1, 4, figsize=(7.16, 2.0), gridspec_kw={"wspace": 0.08})
    for ax, name, ttl in zip(axs, ["S2", "S3L", "S2x2", "S3"], ["(a) 2-socket [MUKCa]", "(b) 3-socket, collinear",
                                                               "(c) 2-socket, two placements", "(d) 3-socket, triangle"]):
        lay = layout(name, paper)
        uv = paper.to_paper(lay.centres)[:, :2]
        ax.add_patch(plt.Rectangle((0, 0), PAPER_W_MM, PAPER_H_MM, fill=False, ec=INK2, lw=0.8))
        for k, l in lay.pairs:
            ax.plot(uv[[k, l], 0], uv[[k, l], 1], color=COL[name], lw=1.0, ls="--")
            if name != "S3L":
                mid = uv[[k, l]].mean(0)
                ax.text(mid[0], mid[1] - 7, f"{np.linalg.norm(uv[k] - uv[l]):.0f} mm", fontsize=6, ha="center", color=INK2)
        if name == "S3L":
            ax.text(uv[1, 0], uv[1, 1] - 12, "75 / 75 / 150 mm", fontsize=6, ha="center", color=INK2)
        ax.text(105, 300, "A4 sheet (paper frame)", fontsize=5.5, ha="center", va="top", color=INK2)
        ax.scatter(uv[:, 0], uv[:, 1], s=30, color=COL[name], marker=MARK[name], edgecolor="white", lw=0.6, zorder=3)
        for i, p in enumerate(uv):
            ax.text(p[0] + 6, p[1] + 9, f"s{i + 1}", fontsize=6.5, color=INK)
        ax.set_xlim(-10, 220)
        ax.set_ylim(307, -10)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_title(ttl, fontsize=7.5, color=INK)
    save(fig, "fig2_socket_layouts")


def main() -> None:
    out: dict = {}
    analyse_obs(out)
    analyse_e1(out)
    analyse_e5(out)
    analyse_sens(out)
    fig_layouts()
    for f in ("validation_controller.json", "validation_pybullet.json"):
        p = PROC / f
        if p.exists():
            out[f.replace(".json", "")] = json.loads(p.read_text())
    (PROC / "statistics.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({k: v for k, v in out.items() if k.startswith(("e1_tests", "e5_tests", "obs_rank"))}, indent=1, default=float)[:6000])


if __name__ == "__main__":
    main()
