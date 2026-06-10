"""Tests for calibrate.py, validated against the REAL Sprint-0 Location_A pairs."""
import numpy as np

from solar_twin import calibrate

# real Sprint-0 Location_A (synthetic lux, CAMS clear-sky GHI)
LUX = [3376.6, 11459.7, 16243.3, 20427.6, 23959.3, 26434.0, 27649.5, 27472.0, 26173.5,
       23595.7, 20092.8, 15821.4, 10471.4, 2843.2, 4618.2, 11281.9, 13599.9, 14873.5,
       14622.9, 13309.2, 9730.8, 3806.6]
GHI = [71.2, 241.9, 437.4, 625.1, 783.3, 898.0, 961.1, 966.9, 914.9, 815.3, 671.8, 496.2,
       297.5, 108.0, 148.6, 296.2, 407.0, 467.1, 468.8, 411.9, 303.5, 157.0]


def test_behavior_match_passes_gate():
    r = calibrate.behavior_match(LUX, GHI)
    assert r >= 0.90                # the gate
    assert abs(r - 0.9879) < 0.01   # matches the offline analysis


def test_fit_location_app_direction():
    fit = calibrate.fit_location(LUX, GHI, "Location_A")
    assert fit.r2 > 0.95
    assert fit.n_obs == 22
    g = float(fit.predict_ghi(27000))     # midday lux -> plausible GHI
    assert 700 < g < 1100
    assert fit.efficacy_mean > 20         # ~33 for this tilted roof pixel


def test_passes_gate_helper():
    assert calibrate.passes_gate(LUX, GHI, min_r=0.90)
    assert not calibrate.passes_gate([1, 2, 3, 4, 5], [5, 1, 4, 2, 3])  # noise -> fail


def test_geometry_aware_not_worse():
    elev = [9.4, 20.5, 32.1, 43.9, 55.6, 66.5, 74.4, 73.8, 65.4, 54.3, 42.6, 30.8, 19.3, 8.2,
            12.4, 20.1, 25.6, 28.4, 28.0, 24.5, 18.4, 10.3]
    am = [1 / np.sin(np.radians(max(e, 1))) for e in elev]
    _, r2g = calibrate.fit_geometry_aware(LUX, GHI, elev, am)
    base = calibrate.fit_location(LUX, GHI).r2
    assert r2g >= base - 0.01            # geometry features shouldn't hurt
