"""Monolithic Lux<->GHI dataset assembly (all locations, one table).

GPU-independent. Schema is tuned for the synthetic->real transfer-learning
calibration model. Columns, in order:

  location_id, latitude, longitude, altitude_m, timestamp_utc      # identity + place + time
  year, month, day, hour, day_of_year                             # calendar (derived from timestamp)
  solar_elevation_deg, solar_azimuth_deg, air_mass                # SOLAR GEOMETRY — the strong
                                                                   #   physical features for efficacy
  sun_study_current_time, qa_flag                                 # provenance / quality
  lux, ghi                                                        # the calibrated pair (lm/m2 ; W/m2)

Why solar geometry, not just hour/month: the lux<->GHI ratio is luminous efficacy,
which varies physically with solar elevation + air mass (and seasonally). Giving
the model elevation/air_mass directly beats making it learn them from hour/month.

Time is anchored to UTC throughout. Daylight filter drops elevation <= cutoff
(pre-dawn / post-sunset), per the user's request to skip low-sun hours.
"""
from __future__ import annotations

import pandas as pd

from . import ephemeris, io_cams

COLUMNS = [
    "location_id", "latitude", "longitude", "altitude_m", "timestamp_utc",
    "year", "month", "day", "hour", "day_of_year",
    "solar_elevation_deg", "solar_azimuth_deg", "air_mass",
    "sun_study_current_time", "qa_flag",
    "lux", "ghi",
]


def _air_mass(elev_deg: float):
    """Kasten-Young (1989) relative air mass from apparent elevation (deg).
    Returns None below the horizon. AM=1 at zenith, ~38 at horizon.
    """
    import math
    if elev_deg <= 0:
        return None
    z = 90.0 - elev_deg  # zenith angle
    denom = math.cos(math.radians(z)) + 0.50572 * (96.07995 - z) ** (-1.6364)
    return round(1.0 / denom, 4) if denom > 0 else None


def _qa_flag(lux, ghi, lux_prev) -> str:
    flags = []
    if lux is None or pd.isna(lux):
        flags.append("lux_missing")
    if ghi is None or pd.isna(ghi):
        flags.append("ghi_missing")
    if lux is not None and not pd.isna(lux):
        if lux < 0:
            flags.append("lux_negative")
        if lux_prev is not None and lux_prev > 0 and lux < 0.25 * lux_prev:
            flags.append("lux_dropout")
        if lux > 200000:
            flags.append("lux_too_high")
    return "|".join(flags)


def assemble_location(lux_df: pd.DataFrame, cams_inst: pd.DataFrame, *,
                      location_id: str, longitude: float, latitude: float,
                      altitude_m: float = 0.0, cutoff_deg: float = 5.0,
                      offset_hours: float | None = None,
                      tol_minutes: float = 8.0) -> pd.DataFrame:
    """Build monolithic rows for ONE location. lux_df: [timestamp_utc, lux];
    cams_inst: io_cams.to_instantaneous(read_cams(...)). Daylight-filtered, sorted.
    """
    rows = []
    prev_lux = None
    for _, r in lux_df.sort_values("timestamp_utc").iterrows():
        ts = pd.Timestamp(r["timestamp_utc"])
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        ts = ts.tz_convert("UTC")
        sp = ephemeris.solar_position(latitude, longitude, altitude_m,
                                      pd.DatetimeIndex([ts]))
        elev = float(sp["apparent_elevation"].iloc[0])
        azim = float(sp["azimuth"].iloc[0])
        if elev <= cutoff_deg:                       # daylight filter
            prev_lux = r["lux"]
            continue
        ghi = io_cams.ghi_at(cams_inst, ts, tol_minutes=tol_minutes)
        _, ct = ephemeris.utc_to_sunstudy(ts, longitude, offset_hours=offset_hours)
        rows.append({
            "location_id": location_id,
            "latitude": round(float(latitude), 4),
            "longitude": round(float(longitude), 4),
            "altitude_m": round(float(altitude_m), 1),
            "timestamp_utc": ts.isoformat(),
            "year": ts.year, "month": ts.month, "day": ts.day,
            "hour": ts.hour, "day_of_year": int(ts.dayofyear),
            "solar_elevation_deg": round(elev, 2),
            "solar_azimuth_deg": round(azim, 2),
            "air_mass": _air_mass(elev),
            "sun_study_current_time": round(ct, 3),
            "qa_flag": _qa_flag(r["lux"], ghi, prev_lux),
            "lux": None if pd.isna(r["lux"]) else round(float(r["lux"]), 1),
            "ghi": None if ghi is None else round(float(ghi), 1),
        })
        prev_lux = r["lux"]
    return pd.DataFrame(rows, columns=COLUMNS)


def combine(location_frames) -> pd.DataFrame:
    frames = [f for f in location_frames if f is not None and len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def write_monolithic(df: pd.DataFrame, csv_path: str, parquet: bool = True) -> None:
    """';'-separated CSV (like the CAMS files) + optional typed Parquet twin."""
    df.to_csv(csv_path, sep=";", index=False)
    if parquet:
        pq = csv_path.rsplit(".", 1)[0] + ".parquet"
        try:
            df.to_parquet(pq, index=False)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] parquet write skipped ({type(e).__name__}: {e}); CSV written.")
