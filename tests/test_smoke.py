"""Smoke tests for the scaffold: imports work and stubs honor their contracts.

These pass now (scaffold stage). As each core module is implemented after
Step A, replace the corresponding NotImplementedError assertion with real
behavior tests (e.g. fit_location against the 4-day data).
"""
import importlib

import pytest

CORE = ["ephemeris", "io_cams", "calibrate", "export_model", "ghi_model"]
OMNIVERSE = ["capture", "sweep"]


@pytest.mark.parametrize("mod", CORE + OMNIVERSE)
def test_module_imports(mod):
    importlib.import_module(f"solar_twin.{mod}")


def test_calibrate_is_implemented():
    from solar_twin import calibrate
    assert hasattr(calibrate, "fit_location") and hasattr(calibrate, "behavior_match")


def test_ghi_model_is_implemented():
    from solar_twin import ghi_model
    assert hasattr(ghi_model, "CalibratedGhiModel") and hasattr(ghi_model, "GhiRequest")


def test_export_schema_version_constant():
    from solar_twin import export_model
    assert export_model.SCHEMA_VERSION == "1.0.0"


def test_capture_blocked_on_step_a():
    from solar_twin import capture
    # Step A resolved the token (2026-05-31).
    assert capture.ILLUMINANCE_AOV_TOKEN == "PtIlluminance"


def test_capture_sample_points_lux_is_gpu_independent():
    """sample_points_lux is pure numpy — testable without Omniverse."""
    import numpy as np

    from solar_twin import capture
    lux = np.zeros((10, 10), dtype=float)
    lux[5, 5] = 1000.0  # bright pixel
    out = capture.sample_points_lux(lux, {"p": (5, 5), "dark": (0, 0)}, kernel=0)
    assert out["p"] == 1000.0
    assert out["dark"] == 0.0


def test_to_photopic_lux_rgb_weighting():
    """PtIlluminance is RGB illuminance; lux = 0.2126R + 0.7152G + 0.0722B."""
    import numpy as np

    from solar_twin import capture
    px = np.array([[[1000.0, 2000.0, 3000.0, 1.0]]])  # (1,1,4): R,G,B,alpha
    lux = capture.to_photopic_lux(px)
    expected = 0.2126 * 1000 + 0.7152 * 2000 + 0.0722 * 3000
    assert abs(float(lux[0, 0]) - expected) < 1e-6
    # already-scalar passthrough
    flat = np.array([[500.0, 600.0]])
    assert capture.to_photopic_lux(flat).shape == (1, 2)
