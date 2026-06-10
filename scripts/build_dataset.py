r"""Assemble the monolithic dataset + per-location calibration models (uv env).

GPU-free. Run AFTER the per-location extractions land. Scans the lux CSVs, joins
each to its CAMS file on UTC instants, builds the one monolithic table (full
transfer-learning schema, daylight-filtered, QA-flagged), fits per-location
lux->GHI models, scores the >=0.90 behavior-match gate, and writes the export JSON.

Handles PARTIAL data: only locations that have BOTH a lux CSV and a CAMS file are
processed, so you can run it after the first extraction and re-run as more land.

Pairing by name: data/lux_csv/lux_Location_A.csv  <->  data/raw_GHI/Location_A.csv

Usage (uv env):
    uv run python scripts/build_dataset.py ^
        --lux-dir  "C:/Users/Nikos/Documents/Vz Studio/data/lux_csv" ^
        --cams-dir "C:/Users/Nikos/Documents/Vz Studio/data/raw_GHI" ^
        --out-dir  "C:/Users/Nikos/Documents/Vz Studio/data/dataset"
"""
from __future__ import annotations

import argparse
import glob
import os
import re

import pandas as pd

from solar_twin import io_cams, dataset, calibrate, export_model


def _read_lux(path: str) -> pd.DataFrame:
    """Read lux_<LOC>.csv whether its header is 'timestamp_utc' or 'timestamp'."""
    df = pd.read_csv(path, sep=";")
    col = "timestamp_utc" if "timestamp_utc" in df.columns else "timestamp"
    df["timestamp_utc"] = pd.to_datetime(df[col], utc=True, format="ISO8601")
    df["lux"] = pd.to_numeric(df["lux"], errors="coerce")
    return df[["timestamp_utc", "lux"]]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lux-dir", required=True)
    p.add_argument("--cams-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--cutoff-deg", type=float, default=5.0)
    args = p.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    lux_files = sorted(glob.glob(os.path.join(args.lux_dir, "lux_*.csv")))
    print(f"[build] found {len(lux_files)} lux file(s)")

    frames, fits = [], []
    for lf in lux_files:
        m = re.search(r"lux_(.+)\.csv$", os.path.basename(lf))
        loc = m.group(1)
        camsf = os.path.join(args.cams_dir, f"{loc}.csv")
        if not os.path.exists(camsf):
            print(f"[skip] {loc}: no CAMS file at {camsf}")
            continue

        cams_df, meta = io_cams.read_cams(camsf)
        cams = io_cams.to_instantaneous(cams_df)
        lux = _read_lux(lf)

        frame = dataset.assemble_location(
            lux, cams, location_id=loc,
            longitude=meta.longitude, latitude=meta.latitude,
            altitude_m=meta.altitude_m or 0.0, cutoff_deg=args.cutoff_deg)
        frames.append(frame)

        paired = frame.dropna(subset=["lux", "ghi"])
        if len(paired) >= 3:
            fit = calibrate.fit_location(paired["lux"], paired["ghi"], location_id=loc)
            r = calibrate.behavior_match(paired["lux"], paired["ghi"])
            xval = calibrate.cross_validate_seasons(paired)
            fits.append(fit)
            gate = "PASS" if r >= 0.90 else "CHECK"
            print(f"[fit] {loc}: n={fit.n_obs} r={r:.4f} R2={fit.r2:.4f} "
                  f"eff={fit.efficacy_mean:.1f} GHI={fit.a_lux2ghi:.5f}*lux{fit.b_lux2ghi:+.1f} "
                  f"[{gate}] xval={xval}")
        else:
            print(f"[fit] {loc}: only {len(paired)} paired rows — skipped fit")

    # monolithic dataset
    mono = dataset.combine(frames)
    mono_csv = os.path.join(args.out_dir, "lux_ghi_monolithic.csv")
    dataset.write_monolithic(mono, mono_csv, parquet=True)
    print(f"\n[build] monolithic dataset: {len(mono)} rows -> {mono_csv} (+ .parquet)")

    # calibration export
    if fits:
        exp = export_model.build_export(
            fits, meta={"cams_source": "soda-pro CAMS McClear clear-sky",
                        "pipeline_version": "solar-twin 0.1.0"})
        problems = export_model.validate_export(exp)
        exp_path = os.path.join(args.out_dir, "calibration_export.json")
        export_model.write_export(exp, exp_path)
        print(f"[build] calibration export: {len(fits)} location(s) -> {exp_path}"
              + (f"  PROBLEMS: {problems}" if problems else "  (valid)"))


if __name__ == "__main__":
    main()
