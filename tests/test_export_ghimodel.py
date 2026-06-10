"""End-to-end: fit -> export JSON -> CalibratedGhiModel.predict (the app's path)."""
from solar_twin import calibrate, export_model, ghi_model


def test_export_and_predict_roundtrip(tmp_path):
    LUX = [3376.6, 11459.7, 16243.3, 20427.6, 23959.3, 26434, 27649.5, 27472, 26173.5,
           23595.7, 20092.8, 15821.4, 10471.4, 2843.2]
    GHI = [71.2, 241.9, 437.4, 625.1, 783.3, 898, 961.1, 966.9, 914.9, 815.3, 671.8,
           496.2, 297.5, 108]
    fit = calibrate.fit_location(LUX, GHI, "Location_A")
    exp = export_model.build_export([fit])
    assert export_model.validate_export(exp) == []
    p = str(tmp_path / "export.json")
    export_model.write_export(exp, p)
    m = ghi_model.CalibratedGhiModel(p, "Location_A")
    g = m.predict(ghi_model.GhiRequest(27000))
    assert 700 < g < 1100               # midday GHI band
    assert m.predict(-5) == 0.0         # clamp negative lux
    m.select("NoSuchLoc")
    assert m.predict(11000) >= 0        # global fallback works


def test_export_gate_flag():
    fit = calibrate.fit_location([1, 2, 3, 100, 200, 300], [1, 2, 3, 100, 200, 300], "L")
    exp = export_model.build_export([fit])
    assert exp["locations"][0]["gate_passed"] is True
