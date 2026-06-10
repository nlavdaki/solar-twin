"""Tests for the lux export format (timestamp;lux) and the CAMS join."""
import pandas as pd

from solar_twin import io_cams


def test_lux_csv_roundtrip(tmp_path):
    p = str(tmp_path / "lux_Location_A.csv")
    recs = [("2023-06-21T09:00:00Z", 24800.8), ("2023-06-21T10:00:00Z", 31000.0)]
    io_cams.write_lux_csv(recs, p)
    # semicolon-separated, with header — matches the CAMS file style
    lines = open(p, encoding="utf-8").read().splitlines()
    assert lines[0] == "timestamp;lux"
    assert ";" in lines[1]
    back = io_cams.read_lux_csv(p)
    assert len(back) == 2
    assert abs(back["lux"].iloc[0] - 24800.8) < 0.1
    assert str(back["timestamp_utc"].dt.tz) == "UTC"


def test_lux_csv_naive_timestamp_localized(tmp_path):
    p = str(tmp_path / "lux_Location_B.csv")
    io_cams.write_lux_csv([("2023-12-21T11:00:00", 5000.0)], p)  # no tz -> assumed UTC
    back = io_cams.read_lux_csv(p)
    assert str(back["timestamp_utc"].dt.tz) == "UTC"
    assert abs(back["lux"].iloc[0] - 5000.0) < 0.1
