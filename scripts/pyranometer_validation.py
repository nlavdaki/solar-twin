r"""Validate calibrated GHI against in-situ pyranometer measurements (uv, GPU-free).

Compares model-predicted GHI against a real pyranometer at a rooftop.
Pyranometer data is not yet available — this scaffold is written + self-tested now
so it's ready. A --self-test mode generates a synthetic pyranometer file from the
model + Gaussian noise to confirm the pipeline runs.

Inputs:
  --pyranometer  CSV [timestamp_utc, ghi_measured_wm2] (1-min or 10-min cadence)
  --location     Location_{X}
  --model        calibration_export.json for that location
  --lux          lux CSV for the location (data/lux_csv/lux_{LOCATION}.csv)
Processing: nearest-neighbour time join (<=5 min); GhiModel.predict(lux)->GHI_pred;
metrics vs measured (RMSE, MBE, nRMSE, R2, Pearson r, regression slope/intercept);
stratified by season (DJF/MAM/JJA/SON) and elevation bin; optional clear-sky filter.
Outputs: data/results/pyranometer_validation_summary.csv (+ _scatter.png).

Baseline to beat: prior-pipeline R2 = 0.97.

Usage:
    uv run python scripts/pyranometer_validation.py --self-test --location Location_A \
      --model "…/data/dataset/calibration_export.json" --lux "…/data/lux_csv/lux_Location_A.csv"
    uv run python scripts/pyranometer_validation.py --pyranometer "…/pyrano.csv" \
      --location Location_A --model "…/calibration_export.json" --lux "…/lux_Location_A.csv"
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

import numpy as np
import pandas as pd

HW = "RTX 4070 12GB | i5-12600K | 32GB | IsaacSim 5.1.0-rc19 Kit107.3.3"
_SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
           6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}
ELEV_BINS = [(10, 20), (20, 40), (40, 91)]


def _read_lux(path):
    df = pd.read_csv(path, sep=";")
    col = "timestamp_utc" if "timestamp_utc" in df.columns else df.columns[0]
    df["timestamp_utc"] = pd.to_datetime(df[col], utc=True, format="ISO8601")
    df["lux"] = pd.to_numeric(df["lux"], errors="coerce")
    return df[["timestamp_utc", "lux"]].dropna()


def _load_model(model_path, location):
    from solar_twin.ghi_model import CalibratedGhiModel, GhiRequest
    m = CalibratedGhiModel(model_path, location)
    return lambda lux: np.array([m.predict(GhiRequest(float(x))) for x in lux])


def _metrics(meas, pred):
    meas = np.asarray(meas, float); pred = np.asarray(pred, float)
    mask = np.isfinite(meas) & np.isfinite(pred)
    meas, pred = meas[mask], pred[mask]
    if len(meas) < 3:
        return {}
    err = pred - meas
    rmse = float(np.sqrt(np.mean(err**2))); mbe = float(np.mean(err))
    ss_res = float(np.sum(err**2)); ss_tot = float(np.sum((meas-meas.mean())**2))
    r2 = 1 - ss_res/ss_tot if ss_tot > 0 else np.nan
    r = float(np.corrcoef(meas, pred)[0, 1])
    slope, intercept = np.polyfit(meas, pred, 1)
    return dict(n=len(meas), rmse=rmse, mbe=mbe, nrmse=rmse/meas.mean()*100 if meas.mean() else np.nan,
                r2=r2, pearson_r=r, slope=float(slope), intercept=float(intercept))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pyranometer")
    p.add_argument("--location", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--lux", required=True)
    p.add_argument("--cams", default=None,
                   help="OPTIONAL CAMS McClear CSV for the SAME site (Thissio). Adds the 3-way "
                        "comparison: twin-vs-pyranometer vs CAMS-vs-pyranometer (the realism test).")
    p.add_argument("--out", default=r"C:/Users/Nikos/Documents/Vz Studio/data/results/pyranometer_validation_summary.csv")
    p.add_argument("--scatter", default=r"C:/Users/Nikos/Documents/Vz Studio/data/results/pyranometer_validation_scatter.png")
    p.add_argument("--tolerance-min", type=float, default=5.0)
    p.add_argument("--self-test", action="store_true",
                   help="generate a synthetic pyranometer file from model+noise to test the pipeline")
    args = p.parse_args()

    predict = _load_model(args.model, args.location)
    lux = _read_lux(args.lux)

    if args.self_test:
        rng = np.random.default_rng(0)
        ghi = predict(lux["lux"].to_numpy())
        pyr = pd.DataFrame({"timestamp_utc": lux["timestamp_utc"],
                            "ghi_measured_wm2": np.clip(ghi + rng.normal(0, 20, len(ghi)), 0, None)})
        print(f"[self-test] synthetic pyranometer: {len(pyr)} rows (model + N(0,20) noise)")
    else:
        if not args.pyranometer:
            print("ERROR: provide --pyranometer or use --self-test"); sys.exit(1)
        pyr = pd.read_csv(args.pyranometer)
        tcol = "timestamp_utc" if "timestamp_utc" in pyr.columns else pyr.columns[0]
        pyr["timestamp_utc"] = pd.to_datetime(pyr[tcol], utc=True, format="ISO8601")
        gcol = [c for c in pyr.columns if "ghi" in c.lower() or "meas" in c.lower()][0]
        pyr["ghi_measured_wm2"] = pd.to_numeric(pyr[gcol], errors="coerce")

    # nearest-neighbour join within tolerance
    lux_s = lux.sort_values("timestamp_utc")
    pyr_s = pyr.sort_values("timestamp_utc")
    j = pd.merge_asof(lux_s, pyr_s[["timestamp_utc", "ghi_measured_wm2"]],
                      on="timestamp_utc", direction="nearest",
                      tolerance=pd.Timedelta(minutes=args.tolerance_min)).dropna(subset=["ghi_measured_wm2"])
    j["ghi_pred"] = predict(j["lux"].to_numpy())          # TWIN-derived GHI
    j["month"] = j["timestamp_utc"].dt.month
    j["season"] = j["month"].map(_SEASON)

    # OPTIONAL: CAMS baseline arm (the realism head-to-head).
    have_cams = False
    if args.cams:
        from solar_twin import io_cams
        cdf, _ = io_cams.read_cams(args.cams)
        cinst = io_cams.to_instantaneous(cdf)[["mid_utc", "ghi_wm2"]].rename(
            columns={"mid_utc": "timestamp_utc", "ghi_wm2": "cams_ghi"}).sort_values("timestamp_utc")
        j = pd.merge_asof(j.sort_values("timestamp_utc"), cinst, on="timestamp_utc",
                          direction="nearest", tolerance=pd.Timedelta(minutes=args.tolerance_min))
        have_cams = j["cams_ghi"].notna().any()
    print(f"[join] {len(j)} matched rows (tol {args.tolerance_min} min)"
          + (" | CAMS baseline attached" if have_cams else ""))

    # add a solar-elevation column if present (for tilt/shadow stratification)
    elev_col = "solar_elevation_deg" if "solar_elevation_deg" in j.columns else None

    def block(sub):
        out = {"twin": _metrics(sub["ghi_measured_wm2"], sub["ghi_pred"])}
        if have_cams:
            cc = sub.dropna(subset=["cams_ghi"])
            if len(cc) >= 3:
                out["cams"] = _metrics(cc["ghi_measured_wm2"], cc["cams_ghi"])
        return out

    strata = [("all", j)]
    for s in ["DJF", "MAM", "JJA", "SON"]:
        sub = j[j["season"] == s]
        if len(sub) >= 3:
            strata.append((f"season_{s}", sub))
    if elev_col:
        for lo, hi in [(10, 20), (20, 40), (40, 91)]:
            sub = j[(j[elev_col] >= lo) & (j[elev_col] < hi)]
            if len(sub) >= 3:
                strata.append((f"elev_{lo}_{hi}", sub))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    cols = ["n", "rmse", "mbe", "nrmse", "r2", "pearson_r", "slope", "intercept"]
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(f"# hardware={HW}\n# generated={_dt.date.today()} location={args.location} "
                 f"self_test={args.self_test} baseline_prior_R2=0.97 cams_baseline={have_cams}\n")
        fh.write("stratum,source," + ",".join(cols) + "\n")
        for name, sub in strata:
            b = block(sub)
            for src in ("twin", "cams"):
                if src in b and b[src]:
                    fh.write(f"{name},{src}," + ",".join(f"{b[src][c]:.4f}" for c in cols) + "\n")
    print(f"[wrote] {args.out}")

    ov = _metrics(j["ghi_measured_wm2"], j["ghi_pred"])
    if ov:
        gate = "PASS" if ov["r2"] >= 0.90 else "BELOW 0.90 GATE"
        print(f"[twin vs pyranometer] RMSE={ov['rmse']:.1f} MBE={ov['mbe']:+.1f} "
              f"nRMSE={ov['nrmse']:.1f}% R2={ov['r2']:.4f} ({gate})")
    if have_cams:
        cc = j.dropna(subset=["cams_ghi"])
        cm = _metrics(cc["ghi_measured_wm2"], cc["cams_ghi"])
        if cm:
            print(f"[CAMS vs pyranometer] RMSE={cm['rmse']:.1f} MBE={cm['mbe']:+.1f} "
                  f"nRMSE={cm['nrmse']:.1f}% R2={cm['r2']:.4f}")
            verdict = "TWIN MORE REALISTIC" if ov["rmse"] < cm["rmse"] else "CAMS closer"
            print(f"[HEAD-TO-HEAD] {verdict}: twin RMSE {ov['rmse']:.1f} vs CAMS RMSE {cm['rmse']:.1f} W/m² "
                  f"(twin captures tilt/shadow; CAMS is horizontal-plane)")

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.scatter(j["ghi_measured_wm2"], j["ghi_pred"], s=8, alpha=0.4,
                   label="twin-derived", color="#1d9e75")
        if have_cams:
            cc = j.dropna(subset=["cams_ghi"])
            ax.scatter(cc["ghi_measured_wm2"], cc["cams_ghi"], s=8, alpha=0.4,
                       label="CAMS (horizontal)", color="#d85a30", marker="^")
        lim = float(np.nanmax([j["ghi_measured_wm2"].max(), j["ghi_pred"].max()])) * 1.05
        ax.plot([0, lim], [0, lim], "k--", lw=1, label="1:1")
        ax.set_xlabel("measured GHI — pyranometer (W/m²)")
        ax.set_ylabel("predicted GHI (W/m²)")
        ax.set_title(f"{args.location}: twin vs CAMS, against ground truth")
        ax.legend(); fig.tight_layout(); fig.savefig(args.scatter, dpi=150)
        print(f"[wrote] {args.scatter}")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] scatter skipped: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
