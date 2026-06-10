"""Tests for the CAMS McClear reader, using a tiny synthetic fixture that
reproduces the real Location_*.csv structure (quoted '#' header lines, ';'
body with trailing comma, ISO start/end interval, Wh/m^2).
"""
import textwrap

import pandas as pd
import pytest

from solar_twin import io_cams

FIXTURE = textwrap.dedent('''\
    # Coding: utf-8,
    # Title: CAMS McClear v3.6 model of clear-sky irradiation.,
    # Latitude (positive North, ISO 19115): 37.9853
    # Longitude (positive East, ISO 19115): 23.7590
    # Altitude (m): 148.00,
    # Time reference: Universal time (UT),
    "#     basePhenomenon:""integral_of_surface_downwelling_shortwave_flux""",
    "#     uom:""Wh m-2"" [unit]",
    # Summarization (integration) period: 0 year 0 month 0 day 0 h 15 min 0 s,
    # Columns:,
    # Observation period;TOA;Clear sky GHI;Clear sky BHI;Clear sky DHI;Clear sky BNI,
    2023-06-21T08:00:00.0/2023-06-21T08:15:00.0;220.0;200.0;150.0;50.0;180.0,
    2023-06-21T08:15:00.0/2023-06-21T08:30:00.0;230.0;210.0;158.0;52.0;185.0,
    2023-06-21T08:30:00.0/2023-06-21T08:45:00.0;240.0;220.0;165.0;55.0;190.0,
''')


@pytest.fixture
def cams_csv(tmp_path):
    p = tmp_path / "Location_X.csv"
    p.write_text(FIXTURE, encoding="utf-8")
    return str(p)


def test_header_metadata(cams_csv):
    _, meta = io_cams.read_cams(cams_csv)
    assert meta.latitude == pytest.approx(37.9853)
    assert meta.longitude == pytest.approx(23.7590)
    assert meta.altitude_m == pytest.approx(148.0)
    assert meta.interval_minutes == 15.0
    assert "Universal" in meta.time_reference


def test_body_parsed_and_utc(cams_csv):
    df, _ = io_cams.read_cams(cams_csv)
    assert len(df) == 3
    assert str(df["start_utc"].dt.tz) == "UTC"
    assert df["ghi_whm2"].tolist() == [200.0, 210.0, 220.0]


def test_to_instantaneous_wm2(cams_csv):
    df, _ = io_cams.read_cams(cams_csv)
    inst = io_cams.to_instantaneous(df)
    # 200 Wh/m^2 over a 0.25 h interval = 800 W/m^2
    assert inst["ghi_wm2"].iloc[0] == pytest.approx(800.0)
    assert "mid_utc" in inst.columns


def test_ghi_at_nearest(cams_csv):
    df, _ = io_cams.read_cams(cams_csv)
    inst = io_cams.to_instantaneous(df)
    # midpoint of first interval is 08:07:30; 840 W/m^2 = 210/0.25 for the 2nd
    g = io_cams.ghi_at(inst, pd.Timestamp("2023-06-21T08:22:30Z"))
    assert g == pytest.approx(840.0)
    # far away -> None
    assert io_cams.ghi_at(inst, pd.Timestamp("2023-06-21T20:00:00Z")) is None
