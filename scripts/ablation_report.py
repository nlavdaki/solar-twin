r"""Ablation and leave-location-out report for the physical calibration model.

Reports the change in leave-location-out error as physical terms are added, from
the constant-efficacy baseline to the full beam/diffuse model:

  M0  GHI = a*lux + b                 (constant efficacy)
  M1  + air-mass luminous efficacy
  M2  + beam/diffuse split (kd, AOI, SVF)
  M3  + air-mass on the beam stream
  M4  + ground reflection

kd is read from a measured 'kd' column if present, otherwise derived from GHI and
geometry via Erbs (1982). Per-site geometry (tilt/SVF/horizon) is loaded from
geometry_<site>.json when available; missing sites default to horizontal-open.

Usage:
  uv run python scripts/ablation_report.py \
    --pooled "…/data/dataset/lux_ghi_monolithic.csv" \
    --geometry-dir "…/data/geometry" \
    --out "…/data/results/ablation_loo.csv"
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import numpy as np
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pooled", required=True, help="monolithic A-J dataset")
    p.add_argument("--geometry-dir", default=None, help="dir of geometry_<site>.json")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    from solar_twin import physical_model as pm

    sep = ";" if open(args.pooled).readline().count(";") else ","
    df = pd.read_csv(args.pooled, sep=sep)
    df = df.dropna(subset=["lux", "ghi", "solar_elevation_deg", "air_mass"]).copy()
    if "location_id" not in df.columns:
        df["location_id"] = "all"
    if "kd" not in df.columns:
        doy = df["day_of_year"] if "day_of_year" in df.columns else \
            pd.to_datetime(df["timestamp_utc"]).dt.dayofyear
        df["kd"] = pm.erbs_kd(df["ghi"], df["solar_elevation_deg"], doy)
        print("[ablation] kd derived via Erbs (no measured kd column)")
    if "solar_azimuth_deg" not in df.columns:
        df["solar_azimuth_deg"] = 180.0

    geom = {}
    if args.geometry_dir and os.path.isdir(args.geometry_dir):
        for f in glob.glob(os.path.join(args.geometry_dir, "geometry_*.json")):
            d = json.load(open(f))
            geom[d["location_id"]] = pm.SiteGeometry.from_dict(d)
        print(f"[ablation] loaded geometry for: {sorted(geom)}")
    else:
        print("[ablation] no geometry dir -> all sites horizontal-open")

    n_sites = df["location_id"].nunique()
    print(f"[ablation] {len(df)} rows, {n_sites} sites\n")
    rows = pm.ablation(df, geom)
    print(f"{'model':<26}{'n':>6}{'R2':>8}{'RMSE':>8}{'MBE':>8}{'nRMSE%':>8}")
    for label, m in rows:
        if m:
            print(f"{label:<26}{m['n']:>6}{m['r2']:>8.3f}{m['rmse']:>8.1f}{m['mbe']:>+8.1f}{m['nrmse']:>8.1f}")
        else:
            print(f"{label:<26}{'-- skipped (need >=2 sites / valid rows) --':>40}")

    # full-model per-site detail
    best = "full"
    agg, per, _ = pm.leave_location_out(df, geom, best)
    print(f"\n[full model: per-site leave-location-out]")
    for s, m in sorted(per.items()):
        if m:
            print(f"  {s:<16} R2={m['r2']:>6.3f} RMSE={m['rmse']:>6.1f} MBE={m['mbe']:>+6.1f} n={m['n']}")
    try:
        eff = pm.fit_physical(df, geom, best).efficacies()
        print(f"\n[fitted efficacies, lm/W] " + "  ".join(f"{k}={v:.1f}" for k, v in eff.items()))
        print("  (physical sanity: a_beam ~95-115, a_diff ~120-130 after geometry correction)")
    except Exception as e:  # noqa: BLE001
        print(f"[efficacies] {type(e).__name__}: {e}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("model,n,r2,rmse,mbe,nrmse\n")
        for label, m in rows:
            if m:
                fh.write(f"{label},{m['n']},{m['r2']:.4f},{m['rmse']:.3f},{m['mbe']:.3f},{m['nrmse']:.3f}\n")
    print(f"\n[wrote] {args.out}")


if __name__ == "__main__":
    main()
