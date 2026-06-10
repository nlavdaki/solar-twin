"""Headless sweep orchestrator: iterate (roof x date x time) -> capture -> rows.

REQUIRES Isaac Sim + RTX GPU (runs under SimulationApp headless). Depends on
capture.py, so also blocked on Step A. Adds checkpoint/resume and per-site/year
sharding for the 25k-40k observation campaign (dossier 01 section 5, 05 sprint 4).

Planned API
-----------
    run_sweep(config) -> None       # set sun (ephemeris) -> capture -> sample -> append Parquet
    resume(config) -> None          # idempotent restart from checkpoint

STUB: blocked on Step A + GPU.
"""
from __future__ import annotations

_BLOCKED = "solar_twin.sweep is blocked on Step A + GPU — see README / dossier 07_Sprint0_Spike.md"


def run_sweep(config) -> None:
    raise NotImplementedError(_BLOCKED)


def resume(config) -> None:
    raise NotImplementedError(_BLOCKED)
