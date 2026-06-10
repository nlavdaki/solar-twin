"""Versioned per-location calibration export (the cross-project deliverable).

GPU-independent. Writes the JSON consumed by the separate GHI app via
ghi_model.CalibratedGhiModel. Direction is lux -> GHI (the app's predict(lux)).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0.0"

# physical default if a location is unknown to the app (K=110 lm/W horizontal):
_GLOBAL_FALLBACK = {"a_lux2ghi": 1.0 / 110.0, "b_lux2ghi": 0.0,
                    "note": "K=110 physical default (horizontal); per-location fits preferred"}


def build_export(location_fits, meta: dict | None = None) -> dict:
    """location_fits: iterable of solar_twin.calibrate.LocationFit. meta: optional
    dict merged at top level (e.g. cams_source, pipeline_version)."""
    locs = []
    for f in location_fits:
        d = f.to_dict() if hasattr(f, "to_dict") else dict(f)
        d.setdefault("units", {"input": "lux", "output": "W/m^2"})
        d["gate_passed"] = bool(d.get("r2", 0) >= 0.81)  # r>=0.9 -> r2>=0.81
        locs.append(d)
    export = {
        "schema_version": SCHEMA_VERSION,
        "model_family": "per_location_linear_lux_to_ghi",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "units": {"input": "lux", "output": "W/m^2"},
        "global_fallback": _GLOBAL_FALLBACK,
        "locations": locs,
    }
    if meta:
        export.update(meta)
    return export


def write_export(export_dict: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(export_dict, fh, indent=2)


def validate_export(export_dict: dict) -> list:
    """Return a list of problems (empty = OK)."""
    problems = []
    if export_dict.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version != {SCHEMA_VERSION}")
    if not export_dict.get("locations"):
        problems.append("no locations")
    for loc in export_dict.get("locations", []):
        if "a_lux2ghi" not in loc or "b_lux2ghi" not in loc:
            problems.append(f"{loc.get('location_id','?')}: missing a/b coefficients")
    return problems
