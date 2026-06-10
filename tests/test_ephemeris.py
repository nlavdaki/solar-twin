"""Tests for the ephemeris module: SPA solar position + Sun-Study time conversion.

The offset (current_time - UTC = longitude/15 ≈ 1.584 h for Athens) was measured
on the real scene and is confirmed by scripts/find_time_offset.py.
"""
import pandas as pd

from solar_twin import ephemeris

LAT, LON, ALT = 37.9853, 23.759, 148.0


def test_solar_noon_summer_athens():
    n = ephemeris.solar_noon_utc(LAT, LON, ALT, "2023-06-21")
    assert 10.3 < n < 10.6  # UTC solar noon ~10.45


def test_offset_is_longitude_mean_solar():
    # confirmed empirically: offset = lon/15 = 1.584 (NOT the +2 civil zone)
    assert abs(ephemeris.sunstudy_offset(LON) - 1.584) < 0.01


def test_utc_to_sunstudy_summer_noon():
    # UTC solar noon 10:27 -> Sun Study current_time ~12.03 (matches measured lux peak at 12.0)
    date, ct = ephemeris.utc_to_sunstudy("2023-06-21T10:27:00Z", LON)
    assert date == "2023-06-21"
    assert abs(ct - 12.03) < 0.05


def test_utc_to_sunstudy_day_rollover():
    date, ct = ephemeris.utc_to_sunstudy("2023-06-21T23:30:00Z", LON)
    assert date == "2023-06-22"
    assert 1.0 < ct < 1.2


def test_solar_position_elevation_positive_at_noon():
    sp = ephemeris.solar_position(LAT, LON, ALT, pd.DatetimeIndex(["2023-06-21T10:27:00Z"]))
    assert float(sp["apparent_elevation"].iloc[0]) > 70
