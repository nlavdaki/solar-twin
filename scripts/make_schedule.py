"""Generate the per-location render SCHEDULE (run in the uv env — needs pvlib).

Emits a CSV the headless production_sweep.py consumes (Isaac's Python has no
pvlib, so we precompute here). Half-hourly (:00/:30 UTC) dawn->sunset instants,
10 days/month across the CAMS range, with the Sun-Study current_time already
converted (UTC + longitude/15, the verified offset — no DST).

The :00/:30 marks land exactly on the 15-min CAMS interval midpoints, so the
later lux<->GHI join is exact (no interpolation).

Usage (uv env):
    uv run python scripts/make_schedule.py --cams data/cams/Location_A.csv \
        --location Location_A --out data/schedule_Location_A.csv
    # cadence/cutoff/days knobs let you dial down the render count later.
"""
from __future__ import annotations

import argparse
import calendar

import numpy as np
import pandas as pd
import pvlib

from solar_twin import io_cams


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cams", default=None, help="CAMS Location_*.csv → lat/lon/alt + date range (CAMS sites)")
    p.add_argument("--lat", type=float, default=None, help="latitude (use instead of --cams, e.g. pyranometer site)")
    p.add_argument("--lon", type=float, default=None, help="longitude")
    p.add_argument("--alt", type=float, default=0.0, help="altitude m")
    p.add_argument("--location", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--freq", default="60min", help="sampling cadence (default 60min = hourly)")
    p.add_argument("--days-per-month", type=int, default=4)
    p.add_argument("--cutoff-deg", type=float, default=0.0, help="min solar elevation (0 = dawn->sunset)")
    p.add_argument("--start", default=None, help="restrict start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="restrict end date YYYY-MM-DD")
    p.add_argument("--clear-days", default=None,
                   help="CSV with a 'date' column (YYYY-MM-DD); build the schedule from THESE days "
                        "only (e.g. pyranometer clear-sky days), ignoring the days-per-month grid")
    args = p.parse_args()

    # coordinates: from --cams header, or explicit --lat/--lon
    if args.cams:
        cams_df, meta = io_cams.read_cams(args.cams)
        lat, lon, alt = meta.latitude, meta.longitude, meta.altitude_m
    elif args.lat is not None and args.lon is not None:
        lat, lon, alt = args.lat, args.lon, args.alt
        cams_df = None
    else:
        p.error("provide either --cams or both --lat and --lon")
    offset = lon / 15.0
    print(f"[schedule] {args.location}: lat={lat} lon={lon} alt={alt} | offset=+{offset:.3f}h")

    # ---- determine the list of days to render ----
    if args.clear_days:
        cd = pd.read_csv(args.clear_days)
        day_list = [pd.Timestamp(d, tz="UTC") for d in cd["date"].astype(str)]
        if args.start:
            day_list = [d for d in day_list if d >= pd.Timestamp(args.start, tz="UTC")]
        if args.end:
            day_list = [d for d in day_list if d <= pd.Timestamp(args.end, tz="UTC")]
        print(f"[schedule] clear-days mode: {len(day_list)} days from {args.clear_days}")
    else:
        start = (cams_df["start_utc"].min().normalize() if cams_df is not None
                 else pd.Timestamp(args.start or "2025-01-01", tz="UTC"))
        end = (cams_df["end_utc"].max().normalize() if cams_df is not None
               else pd.Timestamp(args.end or "2025-12-31", tz="UTC"))
        if args.start:
            start = max(start, pd.Timestamp(args.start, tz="UTC"))
        if args.end:
            end = min(end, pd.Timestamp(args.end, tz="UTC"))

        def days_for_month(y, m):
            dim = calendar.monthrange(y, m)[1]
            return sorted(set(np.linspace(1, dim, args.days_per_month).round().astype(int)))

        day_list = []
        for per in pd.period_range(start, end, freq="M"):
            for d in days_for_month(per.year, per.month):
                day = pd.Timestamp(per.year, per.month, d, tz="UTC")
                if start <= day <= end:
                    day_list.append(day)
        print(f"[schedule] grid mode: {start.date()}..{end.date()} freq={args.freq} days/mo={args.days_per_month}")

    rows = []
    for day in day_list:
        t = pd.date_range(day, day + pd.Timedelta(hours=23, minutes=30), freq=args.freq, tz="UTC")
        sp = pvlib.solarposition.spa_python(t, lat, lon, altitude=alt)
        for ts, el in zip(t, sp["apparent_elevation"]):
            if el > args.cutoff_deg:
                local = ts + pd.Timedelta(hours=offset)
                rows.append({
                    "timestamp_utc": ts.isoformat(),
                    "sun_study_date": local.strftime("%Y-%m-%d"),
                    "sun_study_current_time": round(local.hour + local.minute / 60, 4),
                    "solar_elevation_deg": round(float(el), 2),
                })

    out = pd.DataFrame(rows)
    out.to_csv(args.out, sep=";", index=False)
    hrs = lambda s: len(out) * s / 3600
    print(f"[schedule] {len(out)} renders -> {args.out}")
    print(f"[schedule] est time: {hrs(6):.1f}h @6s | {hrs(10):.1f}h @10s | {hrs(15):.1f}h @15s")


if __name__ == "__main__":
    main()
