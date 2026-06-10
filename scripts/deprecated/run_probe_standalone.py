"""Standalone launcher for the Illuminance-AOV probe (Step A), for Windows/Linux terminal.

Why a separate launcher: a standalone Isaac Sim script MUST create SimulationApp
*before* importing anything under `omni.*` / `pxr`. This file does the boot (with
the path-traced AOV carb flags enabled), optionally opens your stage, then runs the
probe logic and exits.

USAGE (Windows, from your Isaac Sim install dir):
    python.bat <pkg>\scripts\run_probe_standalone.py
    python.bat <pkg>\scripts\run_probe_standalone.py --stage "C:/dev/solar-digital-twin-migration/01_old_composer_export/Location_A.usd"

USAGE (Linux):
    ./python.sh <pkg>/scripts/run_probe_standalone.py --stage /path/Location_A.usd

--headless is ON by default; pass --gui to see the viewport.
"""
from __future__ import annotations

import argparse
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--stage", default=None, help="optional .usd to open before probing")
parser.add_argument("--gui", action="store_true", help="show the app window (default headless)")
parser.add_argument("--then", default="probe_illuminance_aov",
                    choices=["probe_illuminance_aov", "live_illuminance_check"],
                    help="which script's main() to run after boot")
parser.add_argument("--keep-open", action="store_true",
                    help="don't close the app at the end (so you can click in the viewport)")
args, _ = parser.parse_known_args()

# 1) Boot the app FIRST, with path-traced AOVs enabled. Nothing omni.* before this.
from isaacsim import SimulationApp  # noqa: E402  (Isaac Sim 4.x/5.x entry point)

sim = SimulationApp({
    "headless": not args.gui,
    "rtx-transient.aov.enableRtxAovs": True,
    "rtx-transient.aov.enableRtxAovsSecondary": True,
})

# 2) Now it is safe to import omni.* and open a stage.
import omni.usd  # noqa: E402

if args.stage:
    print(f"[probe] opening stage: {args.stage}")
    omni.usd.get_context().open_stage(args.stage)
    # let the stage settle / assets load
    for _ in range(60):
        sim.update()

# 3) Dispatch to the chosen script's main() (its omni.* imports happen inside main()).
import importlib  # noqa: E402
import os  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
mod = importlib.import_module(args.then)

try:
    mod.main()
    if args.keep_open:
        print("\n[--keep-open] App staying open. Click the pixel in the viewport to compare, "
              "then close the window to exit.")
        while sim.is_running():
            sim.update()
finally:
    sim.close()
