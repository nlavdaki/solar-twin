"""Solar position (NREL-SPA via pvlib) + Sun-Study time conversion.

GPU-independent. Two jobs:
  1. Reference solar position (apparent elevation/azimuth) for any UTC instant —
     used to validate the rendered sun and to find solar noon.
  2. Convert a CAMS UTC timestamp to the Omniverse Sun-Study `current_time`
     (hours) + date string that drive the sun.

KEY EMPIRICAL FACT (measured on the real scene, 2026-05-31): Sun-Study
`current_time` is **mean solar time at the scene longitude**, i.e.
    current_time = UTC_hour + longitude / 15
NOT the civil timezone and NOT DST-adjusted. (Athens summer solar-noon landed at
current_time ~12.03 while UTC solar noon was 10.45 -> offset +1.58 = 23.759/15.)
The exact offset is confirmed per scene by scripts/find_time_offset.py; this
module defaults to longitude/15 and lets you override.
"""
from __future__ import annotations

import pandas as pd
import pvlib


def solar_position(lat: float, lon: float, alt: float, times_utc):
    """Apparent elevation + azimuth (deg) via NREL-SPA. times_utc: tz-aware index."""
    idx = pd.DatetimeIndex(times_utc)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    sp = pvlib.solarposition.spa_python(idx, lat, lon, altitude=alt)
    return sp[["apparent_elevation", "azimuth"]]


def solar_noon_utc(lat: float, lon: float, alt: float, date: str) -> float:
    """UTC hour (float) of maximum solar elevation on `date` (YYYY-MM-DD)."""
    t = pd.date_range(f"{date} 00:00", f"{date} 23:59", freq="1min", tz="UTC")
    sp = pvlib.solarposition.spa_python(t, lat, lon, altitude=alt)
    i = sp["apparent_elevation"].idxmax()
    return i.hour + i.minute / 60 + i.second / 3600


def sunstudy_offset(lon: float) -> float:
    """Default Sun-Study offset (hours) = mean solar time at longitude = lon/15.

    Confirm per scene with scripts/find_time_offset.py; override if it differs.
    """
    return lon / 15.0


def utc_to_sunstudy(ts_utc, lon: float, offset_hours: float | None = None):
    """Convert a UTC timestamp to (date_str, current_time_hours) for Sun Study.

    current_time = UTC_hour_of_day + offset, where offset defaults to lon/15.
    Returns the date of the *converted local* instant (handles day rollover).
    """
    ts = pd.Timestamp(ts_utc)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    ts = ts.tz_convert("UTC")
    off = sunstudy_offset(lon) if offset_hours is None else offset_hours
    local = ts + pd.Timedelta(hours=off)
    current_time = local.hour + local.minute / 60 + local.second / 3600
    return local.strftime("%Y-%m-%d"), float(current_time)


def daylight_mask(lat: float, lon: float, alt: float, times_utc, cutoff_deg: float = 5.0):
    """Boolean Series: True where apparent elevation > cutoff (daylight filter)."""
    sp = solar_position(lat, lon, alt, times_utc)
    return sp["apparent_elevation"] > cutoff_deg
