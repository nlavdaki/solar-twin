r"""Select ~N representative clear-sky days per month and map them to a target year.

GPU-free (uv). Input: the clear-sky-days CSV from read_pyranometer.py (a 'date'
column, pooled across years). Output: a 'date' CSV (target-year dates) for
make_schedule.py --clear-days.

Rationale: clear-sky GHI repeats annually, so we render the target year's sun
geometry on a representative ~4 clear days/month; validation later pairs each
synthetic day against the pooled measured clear days of that month-day.

Usage (uv):
  uv run python scripts/select_clear_days.py \
    --clear "…/data/pyranometer_thissio_clearsky_days.csv" \
    --year 2025 --per-month 4 \
    --out "…/data/thissio_clear_days_2025.csv"
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--clear", required=True, help="clearsky_days.csv from read_pyranometer.py")
    p.add_argument("--per-month", type=int, default=4)
    p.add_argument("--out", required=True)
    p.add_argument("--year", type=int, default=None,
                   help="remap all picked days onto this single year. OMIT to KEEP the "
                        "days' REAL years (required so synthetic timestamps match the "
                        "pyranometer for the validation join).")
    args = p.parse_args()

    cl = pd.read_csv(args.clear)
    if "clear" in cl.columns:        # LAP-format clearsky_days.csv lists ALL days + a boolean flag
        cl = cl[cl["clear"].astype(bool)].copy()
    cl["date"] = pd.to_datetime(cl["date"])
    cl["m"] = cl["date"].dt.month
    cl["d"] = cl["date"].dt.day

    sel = []
    if args.year is not None:
        # remap to one year (use only for geometry studies, NOT pyranometer validation)
        for m in range(1, 13):
            days = sorted(d for d in cl[cl["m"] == m]["d"].unique() if d <= 28)
            if not days:
                continue
            idx = np.linspace(0, len(days) - 1, args.per_month)
            for d in sorted({days[int(round(i))] for i in idx}):
                sel.append(f"{args.year}-{m:02d}-{d:02d}")
    else:
        # KEEP real years: pick `per_month` actual clear dates spread across each month
        # (pooled over all years), preserving their true (year, month, day) so the
        # validation timestamp-join finds the matching measured day.
        for m in range(1, 13):
            month_days = cl[cl["m"] == m]["date"].dt.strftime("%Y-%m-%d").sort_values().tolist()
            if not month_days:
                continue
            idx = np.linspace(0, len(month_days) - 1, args.per_month)
            for i in idx:
                sel.append(month_days[int(round(i))])
        sel = sorted(set(sel))

    valid = [s for s in sel if not pd.isna(pd.to_datetime(s, errors="coerce"))]
    out = pd.DataFrame({"date": sorted(set(valid))})
    out.to_csv(args.out, index=False)
    mode = f"remapped to {args.year}" if args.year else "REAL years (validation-aligned)"
    print(f"[select] {len(out)} clear days ({args.per_month}/mo, {mode}) -> {args.out}")
    print(out.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
