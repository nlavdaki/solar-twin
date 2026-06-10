"""soda-pro CAMS McClear ingestion + UTC-aligned join + Parquet dataset writer.

GPU-independent. Implemented against real Location_*.csv exports (CAMS McClear
v3.6, clear-sky, 15-min, Wh/m^2, Universal Time).

Real format (verified on Location_A.csv, 119,558 lines):
  - Metadata header is '#'-prefixed; the column header is the LAST '#' line
    ("# Observation period;TOA;Clear sky GHI;..."); data begins right after.
  - Header carries Latitude / Longitude / Altitude / interval / units.
  - Body is ';'-separated with a stray trailing comma on every line.
  - Column 1 is an ISO interval "start/end"; irradiation cols are Wh/m^2
    integrated over the (15-min) interval.

Because the twin renders cloudless scenes, McClear *clear-sky* GHI is the
correct reference (clear-sky <-> clear-sky). See dossier 04 section 3 / 06 section 5.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

# Map CAMS McClear column labels -> tidy names.
_COLMAP = {
    "Observation period": "period",
    "TOA": "toa_whm2",
    "Clear sky GHI": "ghi_whm2",
    "Clear sky BHI": "bhi_whm2",
    "Clear sky DHI": "dhi_whm2",
    "Clear sky BNI": "bni_whm2",
}


@dataclass
class CamsMeta:
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    time_reference: str | None = None
    interval_minutes: float | None = None
    unit: str | None = None
    raw: dict = field(default_factory=dict)


def _parse_header(lines: list[str]) -> tuple[CamsMeta, int]:
    """Return (metadata, index of the column-header line)."""
    meta = CamsMeta()
    col_header_idx = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        # Data rows begin with a digit (ISO date) — stop only then. Some header
        # lines are quote-wrapped ('"#  basePhenomenon:..."'), so we must NOT
        # break merely because a line doesn't start with '#'.
        if s[:1].isdigit():
            break
        if not (s.startswith("#") or s.startswith('"#')):
            continue
        body = s.lstrip('"').lstrip("#").strip().strip(",").strip()
        if "Latitude" in body:
            m = re.search(r"(-?\d+\.?\d*)", body.split(":")[-1])
            if m:
                meta.latitude = float(m.group(1))
        elif "Longitude" in body:
            m = re.search(r"(-?\d+\.?\d*)", body.split(":")[-1])
            if m:
                meta.longitude = float(m.group(1))
        elif body.startswith("Altitude"):
            m = re.search(r"(-?\d+\.?\d*)", body)
            if m:
                meta.altitude_m = float(m.group(1))
        elif body.startswith("Time reference"):
            meta.time_reference = body.split(":", 1)[-1].strip()
        elif "integration) period" in body or "Summarization" in body:
            m = re.search(r"(\d+)\s*min", body)
            if m:
                meta.interval_minutes = float(m.group(1))
        elif body.startswith("uom") or "Wh m-2" in body:
            meta.unit = "Wh/m2"
        # the real column header line starts with "Observation period;"
        if body.startswith("Observation period;"):
            col_header_idx = i
    if col_header_idx is None:
        raise ValueError("CAMS column header line ('# Observation period;...') not found")
    return meta, col_header_idx


def read_cams(path: str) -> tuple[pd.DataFrame, CamsMeta]:
    """Parse a CAMS McClear CSV. Returns (df, meta).

    df columns: start_utc, end_utc (tz-aware UTC), + *_whm2 floats.
    Interval irradiation is preserved as-is (Wh/m^2); use to_instantaneous()
    for W/m^2 at the interval midpoint.
    """
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        lines = fh.readlines()

    meta, hdr_idx = _parse_header(lines)

    header_cols = [c.strip() for c in lines[hdr_idx].lstrip("#").strip().strip(",").split(";")]
    names = [_COLMAP.get(c, c) for c in header_cols]

    records = []
    for ln in lines[hdr_idx + 1:]:
        s = ln.rstrip("\n").rstrip(",").strip()
        if not s:
            continue
        parts = s.split(";")
        if len(parts) != len(names):
            continue
        records.append(parts)

    df = pd.DataFrame(records, columns=names)
    start_end = df["period"].str.split("/", expand=True)
    df["start_utc"] = pd.to_datetime(start_end[0], utc=True, format="ISO8601")
    df["end_utc"] = pd.to_datetime(start_end[1], utc=True, format="ISO8601")
    for c in names:
        if c.endswith("_whm2"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.drop(columns=["period"])
    return df, meta


def to_instantaneous(df: pd.DataFrame) -> pd.DataFrame:
    """Add W/m^2 columns + interval midpoint (UTC) from Wh/m^2 over the interval.

    avg power over the interval (W/m^2) = energy (Wh/m^2) / hours.
    Midpoint is the natural instant to compare against an instantaneous render.
    """
    out = df.copy()
    hours = (out["end_utc"] - out["start_utc"]).dt.total_seconds() / 3600.0
    for c in [c for c in out.columns if c.endswith("_whm2")]:
        out[c.replace("_whm2", "_wm2")] = out[c] / hours
    out["mid_utc"] = out["start_utc"] + (out["end_utc"] - out["start_utc"]) / 2
    return out


def ghi_at(df_inst: pd.DataFrame, utc_ts, tol_minutes: float = 8.0) -> float | None:
    """Nearest-midpoint clear-sky GHI (W/m^2) to a UTC instant, within tolerance."""
    ts = pd.Timestamp(utc_ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    diffs = (df_inst["mid_utc"] - ts).abs()
    i = diffs.idxmin()
    if diffs.loc[i] > pd.Timedelta(minutes=tol_minutes):
        return None
    return float(df_inst.loc[i, "ghi_wm2"])


def write_lux_csv(records, path: str) -> None:
    """Write extracted illuminance as 'timestamp;lux' (semicolon, like the CAMS files).

    records: iterable of (timestamp, lux). Timestamps are written as ISO-8601 UTC.
    File name convention: lux_<site>.csv (e.g. lux_Location_A.csv).
    """
    import csv
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["timestamp", "lux"])
        for ts, lux in records:
            t = pd.Timestamp(ts)
            if t.tzinfo is None:
                t = t.tz_localize("UTC")
            w.writerow([t.tz_convert("UTC").isoformat(), f"{float(lux):.1f}"])


def read_lux_csv(path: str) -> pd.DataFrame:
    """Read a 'timestamp;lux' file back into a DataFrame [timestamp_utc, lux]."""
    df = pd.read_csv(path, sep=";")
    df["timestamp_utc"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    df["lux"] = pd.to_numeric(df["lux"], errors="coerce")
    return df[["timestamp_utc", "lux"]]


def join_lux_to_cams(lux_df: pd.DataFrame, cams_inst: pd.DataFrame,
                     tol_minutes: float = 8.0) -> pd.DataFrame:
    """Pair each extracted lux row with the nearest-midpoint CAMS clear-sky GHI.

    Returns [timestamp_utc, lux, cams_ghi_wm2] — the table for validation #2
    (lux vs GHI behavior match, summer & winter).
    """
    rows = []
    for _, r in lux_df.iterrows():
        ghi = ghi_at(cams_inst, r["timestamp_utc"], tol_minutes=tol_minutes)
        rows.append({"timestamp_utc": r["timestamp_utc"], "lux": r["lux"],
                     "cams_ghi_wm2": ghi})
    return pd.DataFrame(rows)


def write_dataset(rows, out_dir: str):
    raise NotImplementedError("write_dataset (partitioned Parquet) lands with the sweep, Sprint 4.")
