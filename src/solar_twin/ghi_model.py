"""CalibratedGhiModel — drop-in lux -> GHI predictor loaded from the export JSON.

GPU-independent. The separate GHI app loads this and calls predict(lux) -> GHI;
its build_legend(model) works unchanged because it only calls predict(). Full
contract in dossier 06.
"""
from __future__ import annotations

import json


class GhiRequest:
    """Minimal stand-in for the app's request object (carries .lux)."""
    def __init__(self, lux: float):
        self.lux = lux


class CalibratedGhiModel:
    """Per-location lux->GHI from the exported JSON. select() switches location."""

    def __init__(self, export_path: str, location_id: str | None = None):
        with open(export_path, encoding="utf-8") as fh:
            data = json.load(fh)
        self._fallback = data["global_fallback"]
        self._by_loc = {loc["location_id"]: loc for loc in data["locations"]}
        self.select(location_id)

    def select(self, location_id: str | None) -> None:
        loc = self._by_loc.get(location_id) if location_id else None
        p = loc or self._fallback
        self._a = float(p["a_lux2ghi"])
        self._b = float(p["b_lux2ghi"])
        self._loc = location_id

    def predict(self, req) -> float:
        """req may be a GhiRequest, an object with .lux, or a bare float."""
        lux = getattr(req, "lux", req)
        lux = max(0.0, float(lux))
        return max(0.0, self._a * lux + self._b)  # GHI can't be negative
