r"""Read AUTh / Lab of Atmospheric Physics (LAP) Thessaloniki pyranometer .dat files.

Daily ASCII files ``TOT<DDD><YY>.dat`` (TOT = total/global; DDD = day-of-year;
YY = year). Header ``TIME_UT  SZA  [W.m-2]  st.dev``; 1440 rows (one per minute).
``TIME_UT`` is decimal hours **Universal Time** (already UTC -> no clock offset,
unlike the Thissio record). ``st.dev = -9`` marks a missing/invalid sample.
Sensor: Kipp & Zonen **CM21** (ISO 9060 Secondary Standard).

This is GLOBAL irradiance only (no direct/DNI files), so the diffuse fraction for
the clear-sky filter is modelled (pvlib clear-sky), exactly as the A-J pipeline
already does -- not computed from a direct beam channel.

Vectorised over all files -> one tidy UTC table + clear-sky-day classification +
sanity plots, the same shape the validation expects.

Usage (uv):
  uv run python scripts/read_pyranometer_lap.py \
    --dir ".../pyranometer_GHI_ground_level/2025_pyranometer_Thessaloniki" \
    --lat 40.634 --lon 22.956 --alt 60 \
    --out ".../data/pyranometer_thessaloniki_utc.csv" \
    --clear-out ".../data/pyranometer_thessaloniki_clearsky_days.csv" \
    --plot-dir ".../data/results/figures"
"""
from __future__ import annotations

import argparse
import glob
import os
import re

import numpy as np
import pandas as pd

_FNAME = re.compile(r"TOT(\d{3})(\d{2})\.dat$", re.IGNORECASE)


def read_lap_dir(folder: str) -> pd.DataFrame:
    """Parse every TOT<DDD><YY>.dat into one UTC frame: timestamp_utc, sza_deg,
    ghi_wm2, ghi_std. Keeps only valid samples (st.dev != -9, finite GHI)."""
    frames = []
    files = sorted(glob.glob(os.path.join(folder, "*.dat")) +
                   glob.glob(os.path.join(folder, "*.DAT")))
    for f in files:
        m = _FNAME.search(os.path.basename(f))
        if not m:
            continue
        doy, yy = int(m.group(1)), int(m.group(2))
        year = 2000 + yy
        try:
            a = pd.read_csv(f, sep=r"\s+", skiprows=1,
                            names=["t_ut", "sza", "ghi", "std"], engine="c").to_numpy(float)
        except Exception as e:  # noqa: BLE001
            print(f"[lap] skip {os.path.basename(f)}: {type(e).__name__}")
            continue
        base = pd.Timestamp(year=year, month=1, day=1, tz="UTC") + pd.Timedelta(days=doy - 1)
        ts = base + pd.to_timedelta(a[:, 0], unit="h")
        df = pd.DataFrame({"timestamp_utc": ts, "sza_deg": a[:, 1],
                           "ghi_wm2": a[:, 2], "ghi_std": a[:, 3]})
        df = df[(df.ghi_std > -9) & np.isfinite(df.ghi_wm2)]
        frames.append(df)
    if not frames:
        raise SystemExit(f"[lap] no TOT*.dat files parsed in {folder}")
    out = pd.concat(frames, ignore_index=True).sort_values("timestamp_utc").reset_index(drop=True)
    return out


def classify_clear_days(df, lat, lon, alt, sza_mid=60.0, std_max=0.05, dip_max=0.02, n_min=40):
    """Clear-sky-day classification by MIDDAY clear-sky-index smoothness.

    A clear day has a smooth, dip-free GHI through the central hours (sza <=
    sza_mid), where the pvlib Ineichen model-shape mismatch is smallest. The
    discriminator is the NORMALISED clear-sky index (ratio / its daily median),
    so the ~8% absolute offset between the measured GHI and the model does NOT
    bias detection. This gives a season-balanced clear set (~33% for Thessaloniki
    2025; pvlib Reno-Hansen detect_clearsky needs per-day resampling and runs
    over-strict here). Returns (per-day table with 'clear' flag, daytime rows for
    plotting)."""
    import pvlib
    loc = pvlib.location.Location(lat, lon, altitude=alt)
    cs = loc.get_clearsky(pd.DatetimeIndex(df.timestamp_utc))  # ineichen
    d = df.copy()
    d["cs_ghi"] = cs["ghi"].to_numpy()
    d["date"] = d.timestamp_utc.dt.date
    mid = d[(d.sza_deg <= sza_mid) & (d.cs_ghi > 50)].copy()
    mid["ratio"] = mid.ghi_wm2 / mid.cs_ghi
    mid["rn"] = mid.ratio / mid.groupby("date").ratio.transform("median")  # offset-robust
    g = mid.groupby("date")
    tab = pd.DataFrame({
        "n_mid": g.size(),
        "median_ratio": g.ratio.median(),                    # absolute offset (info only)
        "csi_std": g.rn.std(),                               # midday smoothness (discriminator)
        "frac_dip": g.rn.apply(lambda x: (x < 0.8).mean()),  # cloud dips
        "ghi_max": g.ghi_wm2.max(),
    }).reset_index()
    tab["clear"] = (tab.n_mid >= n_min) & (tab.csi_std < std_max) & (tab.frac_dip < dip_max)
    day = d[(d.sza_deg <= 85) & (d.cs_ghi > 50)].copy()      # full daytime, for plotting
    return tab, day


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", required=True)
    p.add_argument("--lat", type=float, default=40.634)   # AUTh LAP, Thessaloniki
    p.add_argument("--lon", type=float, default=22.956)
    p.add_argument("--alt", type=float, default=60.0)
    p.add_argument("--out", required=True)
    p.add_argument("--clear-out", default=None)
    p.add_argument("--plot-dir", default=None)
    args = p.parse_args()

    df = read_lap_dir(args.dir)
    days = df.timestamp_utc.dt.date.nunique()
    print(f"[lap] parsed {len(df):,} valid samples over {days} days "
          f"({df.timestamp_utc.min()} .. {df.timestamp_utc.max()})")
    print(f"[lap] GHI: max {df.ghi_wm2.max():.0f}  daytime(sza<80) mean "
          f"{df[df.sza_deg < 80].ghi_wm2.mean():.0f} W/m^2")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"[wrote] {args.out}")

    tab, day = classify_clear_days(df, args.lat, args.lon, args.alt)
    n_clear = int(tab.clear.sum())
    print(f"[lap] clear-sky days: {n_clear}/{len(tab)} ({n_clear/len(tab)*100:.0f}%)")
    if args.clear_out:
        tab.to_csv(args.clear_out, index=False)
        print(f"[wrote] {args.clear_out}")

    if args.plot_dir:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        os.makedirs(args.plot_dir, exist_ok=True)
        # (1) a clear day: measured vs clear-sky model
        clear_dates = tab[tab.clear].sort_values("ghi_max", ascending=False)
        if len(clear_dates):
            dsel = clear_dates.iloc[len(clear_dates) // 2]["date"]
            s = day[day.date == dsel]
            fig, ax = plt.subplots(figsize=(7, 4))
            ax.plot(s.timestamp_utc, s.ghi_wm2, ".", ms=2, label="measured GHI")
            ax.plot(s.timestamp_utc, s.cs_ghi, "-", lw=1, color="orange", label="clear-sky (Ineichen)")
            ax.set_title(f"Thessaloniki (LAP CM21) — clear day {dsel}")
            ax.set_xlabel("UTC"); ax.set_ylabel("GHI (W/m²)"); ax.legend()
            fig.autofmt_xdate(); fig.tight_layout()
            fig.savefig(os.path.join(args.plot_dir, "lap_clear_day.png"), dpi=150); plt.close(fig)
        # (2) annual coverage: daily max GHI, clear vs cloudy
        fig, ax = plt.subplots(figsize=(9, 3.5))
        t2 = tab.copy(); t2["date"] = pd.to_datetime(t2["date"])
        ax.scatter(t2[~t2.clear].date, t2[~t2.clear].ghi_max, s=8, c="#999", label="cloudy/mixed")
        ax.scatter(t2[t2.clear].date, t2[t2.clear].ghi_max, s=10, c="#D55E00", label="clear")
        ax.set_title("Thessaloniki 2025 — daily max GHI (clear-sky days highlighted)")
        ax.set_ylabel("daily max GHI (W/m²)"); ax.legend()
        fig.tight_layout(); fig.savefig(os.path.join(args.plot_dir, "lap_annual_coverage.png"), dpi=150); plt.close(fig)
        print(f"[wrote] plots in {args.plot_dir}")


if __name__ == "__main__":
    main()
