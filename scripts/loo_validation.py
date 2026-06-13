r"""Leave-location-out cross-validation of the global lux->GHI calibration (uv, GPU-free).

Tests whether a calibration trained on N-1 sites predicts GHI on a held-out site.
Requires the monolithic dataset from build_dataset.py.

Protocol (per held-out site i):
  train = rows where location_id != i; test = rows where location_id == i
  fit GHI = a*lux + b on train (OLS, as in calibrate.fit_location)
  predict on test; metrics: RMSE, MBE, R2, nRMSE (% of mean measured GHI)
  stratified by solar-elevation bin [10-20), [20-40), [40+); elev < 10 excluded
The aggregate row is the sample-count-weighted mean of the per-site metrics.

Usage:
    uv run python scripts/loo_validation.py \
      --dataset data/dataset/lux_ghi_monolithic.csv \
      --out data/results/loo_validation.csv

Hardware and date are stamped in the CSV header.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os

import numpy as np
import pandas as pd

ELEV_BINS = [(10, 20), (20, 40), (40, 91)]
HW = "RTX 4070 12GB | i5-12600K | 32GB | IsaacSim 5.1.0-rc19 Kit107.3.3"


def _metrics(meas, pred):
    meas = np.asarray(meas, float); pred = np.asarray(pred, float)
    m = np.isfinite(meas) & np.isfinite(pred)
    meas, pred = meas[m], pred[m]
    if len(meas) < 3:
        return dict(n=len(meas), rmse=np.nan, mbe=np.nan, r2=np.nan, nrmse=np.nan)
    err = pred - meas
    rmse = float(np.sqrt(np.mean(err**2)))
    mbe = float(np.mean(err))
    ss_res = float(np.sum(err**2)); ss_tot = float(np.sum((meas - meas.mean())**2))
    r2 = 1 - ss_res/ss_tot if ss_tot > 0 else np.nan
    nrmse = rmse / meas.mean() * 100 if meas.mean() else np.nan
    return dict(n=len(meas), rmse=rmse, mbe=mbe, r2=r2, nrmse=nrmse)


def _fit(train):
    """OLS GHI = a*lux + b (matches calibrate.fit_location direction)."""
    a, b = np.polyfit(train["lux"].to_numpy(float), train["ghi"].to_numpy(float), 1)
    return float(a), float(b)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--min-elev", type=float, default=10.0)
    args = p.parse_args()

    sep = ";" if open(args.dataset).readline().count(";") else ","
    df = pd.read_csv(args.dataset, sep=sep)
    df = df.dropna(subset=["lux", "ghi", "solar_elevation_deg"])
    df = df[df["solar_elevation_deg"] >= args.min_elev]
    sites = sorted(df["location_id"].unique())
    print(f"[loo] {len(df)} rows, {len(sites)} sites: {sites}")

    rows = []
    for site in sites:
        train = df[df["location_id"] != site]
        test = df[df["location_id"] == site]
        if len(train) < 3 or len(test) < 3:
            print(f"[loo] {site}: insufficient data"); continue
        a, b = _fit(train)
        pred = a * test["lux"].to_numpy(float) + b
        ov = _metrics(test["ghi"], pred)
        rows.append([site, "all", ov["n"], ov["rmse"], ov["mbe"], ov["r2"], ov["nrmse"]])
        gate = "" if (ov["r2"] is None or np.isnan(ov["r2"])) else (" *** R2<0.90 ***" if ov["r2"] < 0.90 else "")
        print(f"[loo] {site}: n={ov['n']} RMSE={ov['rmse']:.1f} MBE={ov['mbe']:+.1f} "
              f"R2={ov['r2']:.4f} nRMSE={ov['nrmse']:.1f}%{gate}")
        for lo, hi in ELEV_BINS:
            sub = test[(test["solar_elevation_deg"] >= lo) & (test["solar_elevation_deg"] < hi)]
            if len(sub) >= 3:
                mm = _metrics(sub["ghi"], a*sub["lux"].to_numpy(float)+b)
                rows.append([site, f"elev_{lo}_{hi}", mm["n"], mm["rmse"], mm["mbe"], mm["r2"], mm["nrmse"]])

    # weighted aggregate over per-site 'all' rows
    allr = [r for r in rows if r[1] == "all" and not np.isnan(r[5])]
    if allr:
        wn = np.array([r[2] for r in allr], float)
        agg = ["AGGREGATE_weighted", "all", int(wn.sum())]
        for col in (3, 4, 5, 6):  # rmse, mbe, r2, nrmse
            agg.append(float(np.average([r[col] for r in allr], weights=wn)))
        rows.append(agg)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(f"# hardware={HW}\n# generated={_dt.date.today()} dataset={os.path.basename(args.dataset)}\n")
        fh.write("held_out_site,stratum,n_samples,rmse_wm2,mbe_wm2,r2,nrmse_pct\n")
        for r in rows:
            fh.write(",".join(str(r[0]) if i == 0 else str(r[1]) if i == 1 else
                              (f"{r[i]:.4f}" if isinstance(r[i], float) else str(r[i]))
                              for i in range(len(r))) + "\n")
    print(f"\n[wrote] {args.out}")
    if allr:
        print(f"[loo] AGGREGATE weighted: RMSE={agg[3]:.1f} MBE={agg[4]:+.1f} "
              f"R2={agg[5]:.4f} nRMSE={agg[6]:.1f}%")


if __name__ == "__main__":
    main()
