"""solar_twin — per-location lux->GHI calibration from an Omniverse twin vs CAMS.

Scaffold stage: module internals are stubs pending Sprint 0 / Step A
(resolving the RTX Illuminance AOV identifier). See README and the dossier's
07_Sprint0_Spike.md.

GPU-independent modules (implementable & testable without Omniverse):
    ephemeris, io_cams, calibrate, export_model, ghi_model
Omniverse modules (need Isaac Sim + RTX GPU + the resolved AOV id):
    capture, sweep
"""
__version__ = "0.0.1"

__all__ = [
    "ephemeris",
    "io_cams",
    "dataset",
    "calibrate",
    "export_model",
    "ghi_model",
    "capture",
    "sweep",
]
