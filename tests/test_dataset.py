"""Tests for the monolithic dataset assembly: expanded transfer-learning schema,
daylight filter, air mass, QA flags."""
import numpy as np
import pandas as pd

from solar_twin import dataset

LAT, LON, ALT = 37.9853, 23.759, 148.0


def _cams_inst():
    """Synthetic instantaneous CAMS: midpoints across a summer day, GHI ~ bell."""
    mid = pd.date_range("2023-06-21T04:00Z", "2023-06-21T18:00Z", freq="15min")
    h = mid.hour + mid.minute / 60
    ghi = np.clip(900 * np.cos((h - 10.45) / 6.5), 0, None)
    return pd.DataFrame({"mid_utc": mid, "ghi_wm2": ghi})


def test_schema_order_and_derived_fields():
    lux = pd.DataFrame({"timestamp_utc": pd.to_datetime(
        ["2023-06-21T02:00Z", "2023-06-21T10:30Z"], utc=True), "lux": [50.0, 27000.0]})
    out = dataset.assemble_location(lux, _cams_inst(), location_id="Location_A",
                                    longitude=LON, latitude=LAT, altitude_m=ALT, cutoff_deg=5.0)
    assert list(out.columns) == dataset.COLUMNS
    assert len(out) == 1                       # 02:00Z is night -> daylight-filtered
    row = out.iloc[0]
    assert row["location_id"] == "Location_A" and row["altitude_m"] == 148.0
    assert row["year"] == 2023 and row["month"] == 6 and row["day"] == 21
    assert row["day_of_year"] == 172           # June 21
    assert row["solar_elevation_deg"] > 60     # near noon
    assert 1.0 <= row["air_mass"] < 2.0        # high sun -> air mass near 1
    assert row["ghi"] is not None


def test_air_mass_horizon_vs_zenith():
    assert dataset._air_mass(90) < 1.01        # zenith ~ 1
    assert dataset._air_mass(5) > 10           # near horizon large
    assert dataset._air_mass(-2) is None       # below horizon


def test_qa_dropout_flag():
    lux = pd.DataFrame({"timestamp_utc": pd.to_datetime(
        ["2023-06-21T09:00Z", "2023-06-21T09:30Z"], utc=True), "lux": [27000.0, 2400.0]})
    out = dataset.assemble_location(lux, _cams_inst(), location_id="Location_A",
                                    longitude=LON, latitude=LAT, altitude_m=ALT)
    assert "lux_dropout" in out.iloc[1]["qa_flag"]


def test_write_monolithic_header(tmp_path):
    lux = pd.DataFrame({"timestamp_utc": pd.to_datetime(["2023-06-21T10:30Z"], utc=True),
                        "lux": [27000.0]})
    df = dataset.assemble_location(lux, _cams_inst(), location_id="Location_A",
                                   longitude=LON, latitude=LAT, altitude_m=ALT)
    p = str(tmp_path / "mono.csv")
    dataset.write_monolithic(df, p, parquet=False)
    assert open(p).read().splitlines()[0].startswith(
        "location_id;latitude;longitude;altitude_m;timestamp_utc")
