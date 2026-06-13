r"""Per-location luminous efficacy (lux/GHI) summary and scatter (uv, GPU-free).

Efficacy = lux / GHI (lm/W), computed per site from the monolithic dataset. Twin-scale
values are about 27-33 lm/W; a site near ~110 lm/W is approximately horizontal, which
changes the physical interpretation. Cross-site variation motivates per-location
calibration. Low-flux rows are dropped (GHI > 50 W/m^2 and solar elevation > 10 deg).

Usage:
    uv run python scripts/luminous_efficacy.py \
      --dataset "…/data/dataset/lux_ghi_monolithic.csv" \
      --out "…/data/results/luminous_efficacy.csv" \
      --plot "…/data/results/luminous_efficacy_scatter.png"
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os

import numpy as np
import pandas as pd

HW = "RTX 4070 12GB | i5-12600K | 32GB | IsaacSim 5.1.0-rc19 Kit107.3.3"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plot", default=None)
    p.add_argument("--min-ghi", type=float, default=50.0)
    p.add_argument("--min-elev", type=float, default=10.0)
    args = p.parse_args()

    sep = ";" if open(args.dataset).readline().count(";") else ","
    df = pd.read_csv(args.dataset, sep=sep)
    df = df.dropna(subset=["lux", "ghi", "solar_elevation_deg"])
    df = df[(df["ghi"] > args.min_ghi) & (df["solar_elevation_deg"] > args.min_elev)].copy()
    df["efficacy"] = df["lux"] / df["ghi"]

    rows = []
    for site in sorted(df["location_id"].unique()):
        e = df[df["location_id"] == site]["efficacy"]
        rows.append([site, len(e), float(e.mean()), float(e.std()),
                     float(e.min()), float(e.max())])
        flag = " <-- ~horizontal? (near 110)" if e.mean() > 80 else ""
        print(f"  {site}: n={len(e):5d}  mean={e.mean():6.1f}  std={e.std():5.1f}  "
              f"[{e.min():.0f},{e.max():.0f}] lm/W{flag}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(f"# hardware={HW}\n# generated={_dt.date.today()} "
                 f"filters: GHI>{args.min_ghi} elev>{args.min_elev}\n")
        fh.write("location,n_samples,mean_efficacy_lm_W,std_efficacy,min_efficacy,max_efficacy\n")
        for r in rows:
            fh.write(f"{r[0]},{r[1]},{r[2]:.3f},{r[3]:.3f},{r[4]:.3f},{r[5]:.3f}\n")
    print(f"[wrote] {args.out}")

    means = [r[2] for r in rows]
    print(f"\nacross sites: efficacy mean range {min(means):.1f}–{max(means):.1f} lm/W "
          f"(spread = evidence per-location calibration is needed)")

    if args.plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(8, 5))
            for site in sorted(df["location_id"].unique()):
                s = df[df["location_id"] == site]
                ax.scatter(s["solar_elevation_deg"], s["efficacy"], s=6, alpha=0.4, label=site)
            ax.set_xlabel("solar elevation (deg)")
            ax.set_ylabel("luminous efficacy lux/GHI (lm/W)")
            ax.set_title("Luminous efficacy vs solar elevation, per location")
            ax.legend(markerscale=2, fontsize=8, ncol=2)
            fig.tight_layout(); fig.savefig(args.plot, dpi=150)
            print(f"[wrote] {args.plot}")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] plot skipped: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
