r"""Fit the structured physical model on the A-J monolithic and export it as a
deployable PhysicalGhiModel JSON — the cross-project deliverable for the GHI app.

The app loads the JSON via solar_twin.physical_model.PhysicalGhiModel.from_export
and calls predict(lux, when, where): ONE global model, no per-roof coefficients.

Default tier = "split" (M2, the best/parsimonious model: leave-location-out R^2
~0.948). Fitted horizontal-open (no geometry), so it deploys on any pixel; pass a
SiteGeometry at predict time only for a steep facet with a reconciled azimuth.

Usage (uv):
  uv run python scripts/export_physical_model.py \
    --pooled "…/data/dataset/lux_ghi_monolithic.csv" \
    --tier split \
    --out "…/data/dataset/physical_calibration_export.json"
"""
from __future__ import annotations

import argparse
import json
import os

import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pooled", required=True, help="monolithic A-J dataset")
    p.add_argument("--tier", default="split", choices=["am", "split", "split_am", "full"])
    p.add_argument("--twin-scale", type=float, default=3.8,
                   help="twin absolute-luminance scale (informational; not applied)")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    from solar_twin import physical_model as pm

    sep = ";" if open(args.pooled).readline().count(";") else ","
    df = pd.read_csv(args.pooled, sep=sep)
    df = df.dropna(subset=["lux", "ghi", "solar_elevation_deg", "air_mass"]).copy()
    if "location_id" not in df.columns:
        df["location_id"] = "all"
    if "solar_azimuth_deg" not in df.columns:
        df["solar_azimuth_deg"] = 180.0
    if "kd" not in df.columns:
        doy = (df["day_of_year"] if "day_of_year" in df.columns
               else pd.to_datetime(df["timestamp_utc"]).dt.dayofyear)
        df["kd"] = pm.erbs_kd(df["ghi"], df["solar_elevation_deg"], doy)

    # horizontal-open fit -> deployable global model; report its generalization
    agg, _, _ = pm.leave_location_out(df, {}, args.tier)
    eff = pm.fit_physical(df, {}, args.tier).efficacies()
    model = pm.fit_ghi_model(df, {}, tier=args.tier, twin_scale=args.twin_scale, meta={
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "fit_rows": int(len(df)),
        "leave_location_out_r2": round(float(agg.get("r2", float("nan"))), 4),
        "leave_location_out_rmse_wm2": round(float(agg.get("rmse", float("nan"))), 2),
        "efficacies_lm_per_w": {k: round(v, 3) for k, v in eff.items()},
        "predict_signature": "PhysicalGhiModel.from_export(json).predict(lux, when_utc, (lat,lon,alt))",
        "note": ("Global structured lux->GHI model; clear-sky diffuse fraction computed "
                 "internally from time+location (non-circular). Coefficients embed this "
                 "twin's ~%.1fx absolute-luminance scale -> valid only for the same "
                 "Isaac/MDL sky configuration." % args.twin_scale),
    })

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(model.to_export(), fh, indent=2)
    print(f"[export] tier={args.tier}  leave-location-out R2={agg.get('r2'):.3f} "
          f"RMSE={agg.get('rmse'):.1f}  efficacies={ {k: round(v,1) for k,v in eff.items()} }")
    print(f"[wrote]  {args.out}")


if __name__ == "__main__":
    main()
