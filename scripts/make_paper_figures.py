r"""Publication figures for the Computers & Graphics submission (uv, matplotlib).

Writes 300-dpi PNG + PDF figures from the result files; each figure skips cleanly
if its input is missing. Most derive from the monolithic dataset; convergence and
ablation read their own CSVs.

Figures:
  F1 calibration_scatter   per-site lux vs GHI (2x5 grid) + fit + R^2
  F2 loo_pred_vs_obs       leave-location-out predicted vs observed GHI (linear + physical)
  F3 luminous_efficacy     per-site efficacy, per-sample strip + physical-scale axis
  F4 site_map              the 10 rooftops on a lon/lat map, coloured by R^2
  F5 convergence           relative lux error and render time vs totalSpp
  F6 ablation              M0-M4 leave-location-out R^2 / RMSE

Usage:
  uv run python scripts/make_paper_figures.py \
    --pooled "…/data/dataset/lux_ghi_monolithic.csv" \
    --convergence "…/data/results/convergence_table_spp.csv" \
    --ablation "…/data/results/ablation_loo.csv" \
    --out-dir "…/data/results/figures"
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

# ----------------------------------------------------------------- publication style
def _style():
    import matplotlib as mpl
    mpl.use("Agg")
    mpl.rcParams.update({
        "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
        "font.size": 10, "font.family": "serif", "mathtext.fontset": "cm",
        "axes.grid": True, "grid.alpha": 0.25, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False,
    })


# Okabe-Ito colourblind-safe palette (10 sites)
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7",
           "#56B4E9", "#F0E442", "#000000", "#999999", "#8B4513"]


def _save(fig, out_dir, name):
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(out_dir, f"{name}.{ext}"))
    print(f"[fig] wrote {name}.png / .pdf")


def _read_monolithic(path):
    sep = ";" if open(path).readline().count(";") else ","
    df = pd.read_csv(path, sep=sep)
    return df.dropna(subset=["lux", "ghi"])


def _r2(y, p):
    y = np.asarray(y, float); p = np.asarray(p, float)
    ss = np.sum((y - p) ** 2); tot = np.sum((y - y.mean()) ** 2)
    return 1 - ss / tot if tot > 0 else np.nan


# ----------------------------------------------------------------- F1 calibration grid
def fig_calibration(df, out_dir):
    import matplotlib.pyplot as plt
    sites = sorted(df["location_id"].unique())
    n = len(sites)
    ncol = 5; nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(2.6 * ncol, 2.6 * nrow), squeeze=False)
    for i, s in enumerate(sites):
        ax = axes[i // ncol][i % ncol]
        g = df[df.location_id == s]
        lux = g.lux.to_numpy(float); ghi = g.ghi.to_numpy(float)
        a, b = np.polyfit(lux, ghi, 1)
        r2 = _r2(ghi, a * lux + b)
        ax.scatter(lux / 1000, ghi, s=5, alpha=0.35, color=PALETTE[i % len(PALETTE)], edgecolors="none")
        xs = np.array([lux.min(), lux.max()])
        ax.plot(xs / 1000, a * xs + b, "k-", lw=1)
        ax.set_title(f"{str(s).replace('Location_','')}  $R^2$={r2:.3f}", fontsize=9)
        if i // ncol == nrow - 1:
            ax.set_xlabel("lux (×10³)")
        if i % ncol == 0:
            ax.set_ylabel("GHI (W/m²)")
    for j in range(n, nrow * ncol):
        axes[j // ncol][j % ncol].axis("off")
    fig.suptitle("Per-site calibration: synthetic illuminance vs CAMS clear-sky GHI", y=1.0)
    fig.tight_layout()
    _save(fig, out_dir, "F1_calibration_scatter"); plt.close(fig)


# ----------------------------------------------------------------- F2 LOO pred vs obs
def fig_loo(df, out_dir):
    import matplotlib.pyplot as plt
    try:
        from solar_twin import physical_model as pm
        from solar_twin.calibrate import fit_location
    except Exception as e:  # noqa: BLE001
        print(f"[fig] LOO skipped (import): {e}"); return
    d = df.copy()
    if "solar_azimuth_deg" not in d: d["solar_azimuth_deg"] = 180.0
    if "air_mass" not in d: print("[fig] LOO skipped: no air_mass"); return
    if "kd" not in d:
        doy = d["day_of_year"] if "day_of_year" in d else pd.to_datetime(d["timestamp_utc"]).dt.dayofyear
        d["kd"] = pm.erbs_kd(d["ghi"], d["solar_elevation_deg"], doy)
    sites = d["location_id"].to_numpy()
    # linear oof
    lin = np.full(len(d), np.nan); lux = d.lux.to_numpy(float); ghi = d.ghi.to_numpy(float)
    for s in np.unique(sites):
        te = sites == s; tr = ~te
        if tr.sum() < 3: continue
        f = fit_location(lux[tr], ghi[tr]); lin[te] = f.predict_ghi(lux[te])
    _, _, phys = pm.leave_location_out(d, {}, "split")
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    for ax, pred, title in [(axes[0], lin, "Linear  $GHI=a\\,lux+b$"),
                            (axes[1], phys, "Physical (beam/diffuse split)")]:
        for i, s in enumerate(np.unique(sites)):
            m = sites == s
            ax.scatter(ghi[m], pred[m], s=6, alpha=0.4, color=PALETTE[i % len(PALETTE)],
                       edgecolors="none", label=str(s).replace("Location_", ""))
        lim = np.nanmax([ghi.max(), np.nanmax(pred)]) * 1.05
        ax.plot([0, lim], [0, lim], "k--", lw=1)
        ax.set_xlim(0, lim); ax.set_ylim(0, lim); ax.set_aspect("equal")
        ax.set_xlabel("observed GHI (W/m²)"); ax.set_ylabel("predicted GHI (W/m²)")
        ax.set_title(f"{title}\n$R^2$={_r2(ghi[np.isfinite(pred)], pred[np.isfinite(pred)]):.3f}")
    axes[1].legend(title="site", ncol=2, fontsize=7, loc="lower right")
    fig.suptitle("Leave-location-out cross-validation — all-daylight pooled "
                 f"(n={len(d)}); stricter elevation $\\geq$10° gives 0.918 / 0.952", y=1.02)
    fig.tight_layout()
    _save(fig, out_dir, "F2_loo_pred_vs_obs"); plt.close(fig)


# ----------------------------------------------------------------- F3 efficacy
def fig_efficacy(df, out_dir):
    import matplotlib.pyplot as plt
    SCALE, PEREZ = 3.8, 110.0      # twin->physical scale; Perez 1990 horizontal reference
    d = df[(df.ghi > 50) & (df.get("solar_elevation_deg", 90) > 10)].copy()
    d["eff"] = d.lux / d.ghi
    sites = sorted(d.location_id.unique())
    labels = [str(s).replace("Location_", "") for s in sites]
    x = np.arange(len(sites))
    means = np.array([d[d.location_id == s].eff.mean() for s in sites])
    stds = np.array([d[d.location_id == s].eff.std() for s in sites])
    fig, ax = plt.subplots(figsize=(9.2, 5.2)); ax.set_axisbelow(True)
    ax.bar(x, means, width=0.66, color="#0072B2", alpha=0.45, edgecolor="#0072B2", linewidth=0.8, zorder=2)
    rng = np.random.default_rng(0)                       # per-sample strip (within-site spread)
    for i, s in enumerate(sites):
        e = d[d.location_id == s].eff.to_numpy()
        jx = i + (rng.random(len(e)) - 0.5) * 0.34
        ax.scatter(jx, e, s=4, alpha=0.10, color="#0b3d63", edgecolors="none", zorder=3, rasterized=True)
    ax.errorbar(x, means, yerr=stds, fmt="o", ms=4, color="black", ecolor="black",
                elinewidth=1.2, capsize=4, capthick=1.2, zorder=5)          # mean +/- 1 SD
    ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_xlabel("rooftop site")
    ax.set_ylabel(r"effective luminous efficacy — twin scale  [lux/(W/m$^2$)]")
    ax.set_ylim(0, max(d.eff.quantile(0.999), means.max() + stds.max()) * 1.04)
    ax.set_xlim(-0.7, len(sites) - 0.3)
    ax2 = ax.twinx(); ax2.set_ylim(np.array(ax.get_ylim()) * SCALE); ax2.grid(False)
    ax2.spines["top"].set_visible(False)
    ax2.set_ylabel(r"physical luminous efficacy  [lm/W]  (= twin $\times\,3.8$)")
    ax2.axhline(PEREZ, ls="--", lw=1.3, color="#D55E00", zorder=4)
    ax2.annotate(f"Perez (1990) horizontal $\\approx$ {PEREZ:.0f} lm/W", xy=(len(sites) - 1.0, PEREZ),
                 xytext=(0, 6), textcoords="offset points", ha="right", va="bottom",
                 color="#D55E00", fontsize=9)
    ax.set_title(r"Per-site effective luminous efficacy (twin scale; $\times\,3.8 \approx 110$ lm/W physical). "
                 "\nError bars = $\\pm$1 SD of per-sample efficacy.")
    fig.tight_layout(); _save(fig, out_dir, "F3_luminous_efficacy"); plt.close(fig)


# ----------------------------------------------------------------- F4 site map
def fig_map(df, out_dir):
    import matplotlib.pyplot as plt
    if "latitude" not in df or "longitude" not in df:
        print("[fig] map skipped: no lat/lon in monolithic"); return
    rows = []
    for s in sorted(df.location_id.unique()):
        g = df[df.location_id == s]
        a, b = np.polyfit(g.lux, g.ghi, 1)
        rows.append((str(s).replace("Location_", ""), g.longitude.iloc[0], g.latitude.iloc[0],
                     _r2(g.ghi, a * g.lux + b)))
    m = pd.DataFrame(rows, columns=["site", "lon", "lat", "r2"])
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    sc = ax.scatter(m.lon, m.lat, c=m.r2, s=180, cmap="RdYlGn", vmin=0.8, vmax=1.0,
                    edgecolors="k", linewidths=0.6, zorder=3)
    for _, r in m.iterrows():
        ax.annotate(r.site, (r.lon, r.lat), fontsize=9, fontweight="bold",
                    ha="center", va="center", zorder=4)
    fig.colorbar(sc, ax=ax, label="per-site $R^2$", shrink=0.8)
    ax.set_xlabel("longitude (°E)"); ax.set_ylabel("latitude (°N)")
    ax.set_title("Rooftop sites (Athens) — calibration $R^2$")
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout(); _save(fig, out_dir, "F4_site_map"); plt.close(fig)


# ------------------------------------------------ F4b site map on a pale satellite basemap
def fig_map_satellite(df, out_dir, basemap="satellite", alpha=0.45):
    """Variant of F4: same lon/lat axes + R^2-coloured markers, over a PALE
    satellite (or light) basemap so positions read geographically. Needs
    `contextily` (uv add contextily) and network for the map tiles; skips
    cleanly otherwise so F4 is unaffected."""
    import matplotlib.pyplot as plt
    if basemap == "none":
        return
    if "latitude" not in df or "longitude" not in df:
        print("[fig] satellite map skipped: no lat/lon in monolithic"); return
    try:
        import contextily as ctx
    except ImportError:
        print("[fig] F4b skipped: contextily not installed  ->  run:  uv add contextily"); return

    rows = []
    for s in sorted(df.location_id.unique()):
        g = df[df.location_id == s]
        a, b = np.polyfit(g.lux, g.ghi, 1)
        rows.append((str(s).replace("Location_", ""), g.longitude.iloc[0], g.latitude.iloc[0],
                     _r2(g.ghi, a * g.lux + b)))
    m = pd.DataFrame(rows, columns=["site", "lon", "lat", "r2"])
    pad = max(0.004, (m.lon.max() - m.lon.min()) * 0.25, (m.lat.max() - m.lat.min()) * 0.25)
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.set_xlim(m.lon.min() - pad, m.lon.max() + pad)
    ax.set_ylim(m.lat.min() - pad, m.lat.max() + pad)
    src = (ctx.providers.Esri.WorldImagery if basemap == "satellite"
           else ctx.providers.CartoDB.Positron)
    try:  # tiles need network; keep the figure usable if unavailable
        ctx.add_basemap(ax, crs="EPSG:4326", source=src, alpha=alpha,
                        attribution_size=5, zorder=0)
    except Exception as e:  # noqa: BLE001
        print(f"[fig] F4b basemap tiles unavailable ({type(e).__name__}); rendering markers only.")
    ax.set_xlim(m.lon.min() - pad, m.lon.max() + pad)   # re-assert (add_basemap can nudge limits)
    ax.set_ylim(m.lat.min() - pad, m.lat.max() + pad)
    sc = ax.scatter(m.lon, m.lat, c=m.r2, s=240, cmap="RdYlGn", vmin=0.8, vmax=1.0,
                    edgecolors="k", linewidths=0.9, zorder=5)
    for _, r in m.iterrows():
        ax.annotate(r.site, (r.lon, r.lat), fontsize=9, fontweight="bold",
                    ha="center", va="center", zorder=6)
    fig.colorbar(sc, ax=ax, label="per-site $R^2$", shrink=0.8)
    ax.set_xlabel("longitude (°E)"); ax.set_ylabel("latitude (°N)")
    ax.set_title("Rooftop sites (Athens) — calibration $R^2$")
    ax.set_aspect(1.0 / np.cos(np.radians(m.lat.mean())))  # true geographic proportion
    fig.tight_layout(); _save(fig, out_dir, "F4b_site_map_satellite"); plt.close(fig)


# ----------------------------------------------------------------- F5 convergence
def fig_convergence(path, out_dir):
    import matplotlib.pyplot as plt
    if not path or not os.path.exists(path):
        print("[fig] convergence skipped: no CSV"); return
    df = pd.read_csv(path, comment="#")
    cols = {c.lower(): c for c in df.columns}
    spp = df[cols.get("totalspp", df.columns[0])].to_numpy(float)
    # relative deviation vs max-spp lux
    luxcol = next((cols[c] for c in cols if "lux" in c and "mean" in c), None) or \
             next((cols[c] for c in cols if "lux" in c), None)
    devcol = next((cols[c] for c in cols if "dev" in c or "rel" in c or "err" in c), None)
    # render-time column: must match the time column, NOT 'total_spp' (which also
    # contains '_s') and NOT the 'std_render_s' spread column.
    tcol = next((cols[c] for c in cols if ("render" in c or "time" in c) and "std" not in c), None)
    fig, ax = plt.subplots(figsize=(6.6, 4.1))
    if devcol:
        dev = df[devcol].to_numpy(float)
    elif luxcol:
        lux = df[luxcol].to_numpy(float); dev = np.abs(lux - lux[-1]) / lux[-1] * 100
    else:
        print("[fig] convergence skipped: no lux/dev column"); plt.close(fig); return
    l1, = ax.plot(spp, dev, "o-", color="#0072B2", label="relative lux error (%)")
    ax.axhline(0.02, color="grey", ls=":", lw=1); ax.set_xscale("log", base=2)
    ax.set_xticks(spp); ax.set_xticklabels([int(s) for s in spp])
    ax.set_xlabel("path-traced samples per pixel (totalSpp)")
    ax.set_ylabel("relative lux error (%)", color="#0072B2"); ax.tick_params(axis="y", labelcolor="#0072B2")
    handles = [l1]
    if tcol:
        ax2 = ax.twinx(); ax2.grid(False); ax2.spines["top"].set_visible(False)
        rt = df[tcol].to_numpy(float)
        l2, = ax2.plot(spp, rt, "s--", color="#D55E00", label="render time / frame (s)")
        ax2.set_ylabel("render time / frame (s)", color="#D55E00"); ax2.tick_params(axis="y", labelcolor="#D55E00")
        ax2.set_ylim(0, rt.max() * 1.12); handles.append(l2)
    for sx, tag in [(16, "knee"), (64, "converged")]:
        ax.axvline(sx, color="grey", ls="--", lw=0.8, alpha=0.6)
        ax.annotate(tag, xy=(sx, ax.get_ylim()[1] * 0.92), fontsize=8, ha="center", color="grey")
    ax.set_title("Path-tracing convergence: lux error and render time vs totalSpp")
    ax.legend(handles=handles, loc="upper center", fontsize=9, frameon=True)
    fig.tight_layout(); _save(fig, out_dir, "F5_convergence"); plt.close(fig)


# ----------------------------------------------------------------- F6 ablation
def fig_ablation(path, out_dir):
    import matplotlib.pyplot as plt
    if not path or not os.path.exists(path):
        print("[fig] ablation skipped: no CSV"); return
    df = pd.read_csv(path)
    df = df[df["model"].astype(str).str.startswith("M")]
    labels = [m.split("_", 1)[0] for m in df["model"]]
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(df))
    ax.plot(x, df["r2"], "o-", color="#009E73", label="$R^2$ (LOO)")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("leave-location-out $R^2$", color="#009E73")
    ax.set_ylim(min(0.9, df["r2"].min() - 0.02), 1.0)
    for xi, (r, m) in enumerate(zip(df["r2"], df["model"])):
        ax.annotate(f"{r:.3f}", (xi, r), textcoords="offset points", xytext=(0, 6), fontsize=8, ha="center")
    ax2 = ax.twinx(); ax2.bar(x, df["rmse"], alpha=0.18, color="#D55E00"); ax2.grid(False)
    ax2.set_ylabel("RMSE (W/m²)", color="#D55E00")
    ax.set_title("Ablation: each physical term's leave-location-out contribution")
    fig.tight_layout(); _save(fig, out_dir, "F6_ablation"); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pooled", help="lux_ghi_monolithic.csv (F1-F4)")
    ap.add_argument("--convergence", help="convergence_table_spp.csv (F5)")
    ap.add_argument("--ablation", help="ablation_loo.csv (F6)")
    ap.add_argument("--lux-map", help="lux_map_<site>.npy -> F7 false-colour illuminance map")
    ap.add_argument("--basemap", choices=["satellite", "light", "none"], default="satellite",
                    help="F4b basemap behind the site map (needs contextily); 'none' disables")
    ap.add_argument("--basemap-alpha", type=float, default=0.45, help="F4b basemap opacity (pale)")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    _style()
    os.makedirs(a.out_dir, exist_ok=True)
    if a.pooled and os.path.exists(a.pooled):
        df = _read_monolithic(a.pooled)
        for fn in (fig_calibration, fig_loo, fig_efficacy, fig_map):
            try:
                fn(df, a.out_dir)
            except Exception as e:  # noqa: BLE001
                print(f"[fig] {fn.__name__} failed: {type(e).__name__}: {e}")
        try:
            fig_map_satellite(df, a.out_dir, basemap=a.basemap, alpha=a.basemap_alpha)
        except Exception as e:  # noqa: BLE001
            print(f"[fig] fig_map_satellite failed: {type(e).__name__}: {e}")
    else:
        print("[fig] no --pooled -> skipping F1-F4")
    fig_convergence(a.convergence, a.out_dir)
    fig_ablation(a.ablation, a.out_dir)
    if a.lux_map and os.path.exists(a.lux_map):
        try:
            from solar_twin.luxmap import render_lux_map
            site = os.path.basename(a.lux_map).replace("lux_map_", "").replace(".npy", "")
            render_lux_map(a.lux_map, os.path.join(a.out_dir, "F7_lux_map.png"),
                           title=f"RTX path-traced illuminance — {site}")
            print("[fig] wrote F7_lux_map.png / .pdf")
        except Exception as e:  # noqa: BLE001
            print(f"[fig] lux map skipped: {type(e).__name__}: {e}")
    elif a.lux_map:
        print(f"[fig] F7 lux map skipped: file not found -> {a.lux_map}")
    print(f"[done] figures in {a.out_dir}")


if __name__ == "__main__":
    main()
