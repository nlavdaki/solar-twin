r"""Diagnose why a site's lux->GHI fit is weak (e.g. shaded/edge roof pixel).

GPU-free (uv). Reads the monolithic dataset and profiles one or more sites:
  - lux/GHI efficacy vs solar elevation (shading shows as efficacy collapsing at
    specific elevations/azimuths, not a clean ~33 band)
  - residual vs azimuth (a fixed occluder shows as a bias in one azimuth range)
  - fraction of "dark" points (lux far below the site's elevation-expected lux)
  - elevation-binned R² (does the fit fail at low sun = grazing/occlusion, or
    everywhere = wrong pixel?)
Prints a compact report; optionally writes per-site scatter PNGs.

Usage (uv):
  uv run python scripts/diagnose_site.py \
    --dataset "…/data/dataset/lux_ghi_monolithic.csv" \
    --sites Location_H Location_J Location_F \
    --plot-dir "…/data/results/site_diag"
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd


def _r2(x, y):
    if len(x) < 3:
        return float("nan")
    a, b = np.polyfit(x, y, 1)
    pred = a * x + b
    ss = np.sum((y - pred) ** 2)
    tot = np.sum((y - y.mean()) ** 2)
    return 1 - ss / tot if tot > 0 else float("nan")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True)
    p.add_argument("--sites", nargs="+", required=True)
    p.add_argument("--plot-dir", default=None)
    args = p.parse_args()

    sep = ";" if open(args.dataset).readline().count(";") else ","
    df = pd.read_csv(args.dataset, sep=sep)
    df = df.dropna(subset=["lux", "ghi", "solar_elevation_deg"])
    df["eff"] = df["lux"] / df["ghi"].where(df["ghi"] > 0)

    for site in args.sites:
        s = df[df["location_id"] == site].copy()
        if s.empty:
            print(f"\n=== {site}: NOT in dataset ==="); continue
        print(f"\n=== {site}  (n={len(s)}) ===")
        # overall fit
        print(f"  overall R2={_r2(s['lux'].to_numpy(), s['ghi'].to_numpy()):.3f}  "
              f"efficacy mean={s['eff'].mean():.1f} std={s['eff'].std():.1f} "
              f"range[{s['eff'].min():.0f},{s['eff'].max():.0f}]")

        # elevation-binned R2 + efficacy -> is failure low-sun (occlusion/grazing) or global (wrong pixel)?
        print("  elevation bin |  n  | R2    | eff_mean | eff_std")
        for lo, hi in [(5, 15), (15, 30), (30, 45), (45, 90)]:
            b = s[(s.solar_elevation_deg >= lo) & (s.solar_elevation_deg < hi)]
            if len(b) >= 5:
                print(f"   {lo:>2}-{hi:<3}deg   | {len(b):>3} | {_r2(b['lux'].to_numpy(),b['ghi'].to_numpy()):.3f} | "
                      f"{b['eff'].mean():>7.1f}  | {b['eff'].std():>6.1f}")

        # azimuth profile -> a fixed occluder biases one azimuth sector
        print("  azimuth sector | n | eff_mean (low = occluded there?)")
        for lo, hi, lab in [(0,90,"NE"),(90,180,"SE"),(180,270,"SW"),(270,360,"NW")]:
            b = s[(s.solar_azimuth_deg >= lo) & (s.solar_azimuth_deg < hi)]
            if len(b) >= 5:
                print(f"   {lab} {lo:>3}-{hi:<3} | {len(b):>3} | {b['eff'].mean():>6.1f}")

        # 'dark' fraction: points whose efficacy is < 50% of the site median (shadow hits)
        med = s["eff"].median()
        dark = (s["eff"] < 0.5 * med).mean() * 100
        print(f"  shadow-suspect points (eff < 50% of median {med:.0f}): {dark:.1f}%")

        if args.plot_dir:
            try:
                import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
                os.makedirs(args.plot_dir, exist_ok=True)
                fig, ax = plt.subplots(1, 2, figsize=(11, 4))
                ax[0].scatter(s.ghi, s.lux, s=6, alpha=0.4); ax[0].set_xlabel("GHI W/m2"); ax[0].set_ylabel("lux"); ax[0].set_title(f"{site} lux vs GHI")
                ax[1].scatter(s.solar_elevation_deg, s.eff, s=6, alpha=0.4); ax[1].set_xlabel("solar elevation deg"); ax[1].set_ylabel("efficacy lux/GHI"); ax[1].set_title(f"{site} efficacy vs elevation")
                fig.tight_layout(); fig.savefig(f"{args.plot_dir}/{site}_diag.png", dpi=140); plt.close(fig)
                print(f"  [plot] {args.plot_dir}/{site}_diag.png")
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] plot skipped: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
