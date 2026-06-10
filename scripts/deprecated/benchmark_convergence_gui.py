# =====================================================================
# CONVERGENCE + PERFORMANCE BENCHMARK (async, Isaac Sim GUI Script Editor).
#
# Produces the paper's GPU-benchmark table: RT_SUBFRAMES vs mean/std lux vs
# render time vs VRAM, at one representative location at solar noon.
#
# WHY A NEW GUI SCRIPT (not an extension of measure_convergence.py):
#   measure_convergence.py is STANDALONE HEADLESS (boots SimulationApp + sync step).
#   But (a) the MDL dynamic sky does NOT light the scene headlessly -> flat ~1100 lux
#   (invalid), and (b) sync step / SimulationApp can't run inside the GUI Script
#   Editor. Production lighting only works in the GUI, so the benchmark must too.
#   This script is async (step_async) and runs where production runs.
#
# COLD-RENDER VALIDITY (critical): a convergence measurement is only valid if each
# render starts COLD (fresh path-tracing accumulation). If accumulation persists
# between measurements, rt=8 and rt=32 read identical (the same artifact that made
# the earlier "warm viewport" ladder invalid). We force cold by perturbing the
# Sun-Study time by an imperceptible amount each render (~0.0001 h = 0.36 s of solar
# time, sun move < 0.001 deg, lux change far below path-tracing noise) so the
# renderer invalidates and re-accumulates. The script then SELF-VALIDATES:
#   - if rt8 vs rt32 deviation < 0.1%  -> accumulation NOT resetting -> table INVALID
#   - if std_lux ~ 0 at all levels     -> renderer deterministic -> std is meaningless
# Do not use the table in the paper unless the validity check passes.
#
# SETUP:
#   1. isaac-sim.bat (full GUI) > File>Open Location_A.usd
#   2. Viewport renderer -> RTX - Interactive (Path Tracing)
#   3. Window>Script Editor, set CONFIG below, paste this whole file, Run.
#
# HARDWARE (recorded in the CSV header — do not change):
#   RTX 4070 12GB | i5-12600K | 32GB | Isaac Sim 5.1.0-rc19 (Kit 107.3.3)
# =====================================================================

# ---- CONFIG ----
LOCATION   = "Location_A"
TEST_DATE  = "2025-06-21"          # summer
NOON_CT    = 13.0                  # Sun-Study current_time at/near solar noon (worst-case lux)
ROOF_PX    = (506, 418)            # Location_A roof pixel
RT_LADDER  = [8, 12, 16, 20, 24, 32]
N_REPEATS  = 5
OUT_CSV    = r"C:/Users/Nikos/Documents/Vz Studio/data/results/convergence_table.csv"
HW = "RTX 4070 12GB | i5-12600K | 32GB | IsaacSim 5.1.0-rc19 Kit107.3.3"
# ----------------

import asyncio
import csv
import os
import subprocess
import time

import numpy as np
import omni.kit.app
import omni.usd
import omni.replicator.core as rep
from omni.kit.viewport.utility import get_active_viewport

_P = (0.2126, 0.7152, 0.0722)


async def _tick(n):
    for _ in range(n):
        await omni.kit.app.get_app().next_update_async()


def _vram_mb():
    """End-of-render VRAM snapshot (MB) via nvidia-smi. Lower bound on true peak."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10)
        return int(out.stdout.strip().splitlines()[0])
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] nvidia-smi failed: {type(e).__name__}: {e}")
        return None


async def run():
    stage = omni.usd.get_context().get_stage()
    env = stage.GetPrimAtPath("/Environment")
    try:
        from omni.kit.environment.core import get_sunstudy_player
        player = get_sunstudy_player()
    except Exception:
        player = None

    vp = get_active_viewport()
    rp = rep.create.render_product(vp.camera_path.pathString, tuple(vp.resolution))
    rep.AnnotatorRegistry.register_annotator_from_aov("PtIlluminance")
    anno = rep.AnnotatorRegistry.get_annotator("PtIlluminance")
    anno.attach(rp)
    x, y = ROOF_PX

    async def set_time(ct):
        if env and env.IsValid():
            env.GetAttribute("date").Set(TEST_DATE)
            env.GetAttribute("time:current").Set(float(ct))
        if player is not None:
            try:
                player.current_date = TEST_DATE
                player.current_time = float(ct)
            except Exception:
                pass
        await _tick(3)  # SKY_SETTLE_FRAMES — let the MDL sky recompute

    def lux_at_pixel():
        a = np.asarray(anno.get_data(), dtype=np.float64)
        img = _P[0]*a[..., 0] + _P[1]*a[..., 1] + _P[2]*a[..., 2] if a.ndim == 3 else a
        H, W = img.shape[:2]
        xi, yi = min(x, W-1), min(y, H-1)
        return float(np.nanmedian(img[max(0, yi-1):yi+2, max(0, xi-1):xi+2]))

    print(f"=== convergence benchmark: {LOCATION} {TEST_DATE} ct={NOON_CT} pixel{ROOF_PX} ===")
    rows = []
    eps = 0.0  # imperceptible time perturbation accumulator -> forces COLD re-accumulation
    for n in RT_LADDER:
        luxes, times = [], []
        for rep_i in range(N_REPEATS):
            eps += 0.0001  # ~0.36 s of solar time; sun move < 0.001 deg (negligible)
            await set_time(NOON_CT + eps)
            t0 = time.perf_counter()
            await rep.orchestrator.step_async(rt_subframes=n)
            dt = time.perf_counter() - t0
            luxes.append(lux_at_pixel())
            times.append(dt)
        vram = _vram_mb()
        ml, sl = float(np.mean(luxes)), float(np.std(luxes))
        mt, st = float(np.mean(times)), float(np.std(times))
        rows.append((n, ml, sl, mt, st, vram))
        print(f"  rt={n:>2}  mean_lux={ml:8.1f}  std_lux={sl:6.2f}  "
              f"mean_s={mt:5.1f}  std_s={st:4.1f}  vram={vram}")

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# hardware={HW}\n")
        fh.write(f"# location={LOCATION} date={TEST_DATE} current_time={NOON_CT} "
                 f"pixel={ROOF_PX} n_repeats={N_REPEATS}\n")
        w = csv.writer(fh)
        w.writerow(["rt_subframes", "mean_lux_lx", "std_lux_lx",
                    "mean_render_s", "std_render_s", "vram_mb"])
        for r in rows:
            w.writerow([r[0], f"{r[1]:.2f}", f"{r[2]:.3f}", f"{r[3]:.3f}", f"{r[4]:.3f}", r[5]])
    print(f"\n[wrote] {OUT_CSV}")

    # ---- VALIDITY CHECK (protects the paper) ----
    by_n = {r[0]: r[1] for r in rows}
    ref = by_n.get(32)
    dev_8 = abs(by_n.get(8, ref) - ref) / ref * 100 if ref else float("nan")
    max_std = max(r[2] for r in rows)
    print("\n=== VALIDITY CHECK ===")
    print(f"  rt8 vs rt32 lux deviation = {dev_8:.3f}%")
    if dev_8 < 0.1:
        print("  [INVALID] rt8 ~ rt32 -> accumulation is NOT resetting between renders.")
        print("            Same artifact as the warm-viewport ladder. DO NOT use this table.")
        print("            Fix: a stronger cold-reset (camera nudge / render-product recreate).")
    else:
        print("  [OK] rt8 differs from rt32 -> renders are cold; convergence is real.")
    if max_std < 1e-6:
        print("  [NOTE] std_lux ~ 0 at all levels -> renderer is deterministic per seed;")
        print("         'std across repeats' captures no stochastic noise (report as ~0).")
    print("\nNext: deviation%(vs rt32), the convergence 'knee', and the paper table"
          " formatting are computed offline from this CSV.")
    anno.detach(); rp.destroy()


asyncio.ensure_future(run())
print("[benchmark] scheduled — ~%d renders; keep the GUI open." % (len(RT_LADDER)*N_REPEATS))
