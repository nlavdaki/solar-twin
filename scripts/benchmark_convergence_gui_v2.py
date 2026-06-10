# =====================================================================
# CONVERGENCE + PERFORMANCE BENCHMARK v2 (async, Isaac Sim GUI Script Editor).
#
# v1 was INVALID: it swept rt_subframes, but in interactive Path Tracing the
# convergence knob is TOTAL SAMPLES PER PIXEL (/rtx/pathtracing/totalSpp, default
# 512). rt_subframes barely changed render time (flat ~54.5 s) because each frame
# already runs to totalSpp. v2 sweeps totalSpp — the real variable — and forces a
# COLD restart each level via /rtx/resetPtAccumOnAnimTimeChange + a time nudge.
#
# What v1 DID establish (kept for the paper): VRAM ~5.2 GB stable; converged lux
# ~27,130 lx with std < 0.3% (production renders are clean & repeatable). Production
# uses the default totalSpp=512 -> fully converged.
#
# VALIDITY (v2): render time MUST increase monotonically with totalSpp. If it's
# flat, the cold reset isn't taking and the table is invalid (script flags it).
#
# SETUP: separate Isaac GUI session (NOT during an active sweep) >
#   File>Open Location_A.usd > RTX Interactive (Path Tracing) >
#   Window>Script Editor > paste > Run.  ~10-15 min.
#
# HARDWARE: RTX 4070 12GB | i5-12600K | 32GB | IsaacSim 5.1.0-rc19 Kit107.3.3
# =====================================================================

# ---- CONFIG ----
LOCATION   = "Location_A"
TEST_DATE  = "2025-06-21"
NOON_CT    = 13.0
ROOF_PX    = (506, 418)
SPP_LADDER = [8, 16, 32, 64, 128, 256, 512]   # totalSpp values to benchmark
N_REPEATS  = 3
OUT_CSV    = r"C:/Users/Nikos/Documents/Vz Studio/data/results/convergence_table_spp.csv"
HW = "RTX 4070 12GB | i5-12600K | 32GB | IsaacSim 5.1.0-rc19 Kit107.3.3"
# ----------------

import asyncio
import csv
import os
import subprocess
import time

import numpy as np
import carb
import omni.kit.app
import omni.usd
import omni.replicator.core as rep
from omni.kit.viewport.utility import get_active_viewport

_P = (0.2126, 0.7152, 0.0722)


async def _tick(n):
    for _ in range(n):
        await omni.kit.app.get_app().next_update_async()


def _vram_mb():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10)
        return int(out.stdout.strip().splitlines()[0])
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] nvidia-smi: {type(e).__name__}: {e}")
        return None


async def run():
    s = carb.settings.get_settings()
    # cold-reset on time change is the key to a valid per-level measurement
    try:
        s.set("/rtx/resetPtAccumOnAnimTimeChange", True)
    except Exception:
        pass

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
    eps = 0.0

    async def cold_render(total_spp):
        nonlocal eps
        s.set("/rtx/pathtracing/totalSpp", int(total_spp))
        eps += 0.001                       # nudge time -> triggers PT accum reset
        ct = NOON_CT + eps
        if env and env.IsValid():
            env.GetAttribute("date").Set(TEST_DATE)
            env.GetAttribute("time:current").Set(float(ct))
        if player is not None:
            try:
                player.current_date = TEST_DATE
                player.current_time = float(ct)
            except Exception:
                pass
        await _tick(3)
        t0 = time.perf_counter()
        await rep.orchestrator.step_async(rt_subframes=0)  # render to totalSpp
        dt = time.perf_counter() - t0
        a = np.asarray(anno.get_data(), dtype=np.float64)
        img = _P[0]*a[..., 0] + _P[1]*a[..., 1] + _P[2]*a[..., 2] if a.ndim == 3 else a
        H, W = img.shape[:2]
        xi, yi = min(x, W-1), min(y, H-1)
        lux = float(np.nanmedian(img[max(0, yi-1):yi+2, max(0, xi-1):xi+2]))
        return lux, dt

    print(f"=== convergence v2 (totalSpp sweep): {LOCATION} {TEST_DATE} pixel{ROOF_PX} ===")
    rows = []
    for spp in SPP_LADDER:
        luxes, times = [], []
        for _ in range(N_REPEATS):
            lux, dt = await cold_render(spp)
            luxes.append(lux); times.append(dt)
        vram = _vram_mb()
        ml, sl = float(np.mean(luxes)), float(np.std(luxes))
        mt, st = float(np.mean(times)), float(np.std(times))
        rows.append((spp, ml, sl, mt, st, vram))
        print(f"  totalSpp={spp:>4}  lux={ml:8.1f}±{sl:5.1f}  render={mt:6.2f}±{st:4.2f}s  vram={vram}")

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# hardware={HW}\n")
        fh.write(f"# location={LOCATION} date={TEST_DATE} pixel={ROOF_PX} "
                 f"n_repeats={N_REPEATS} knob=totalSpp\n")
        w = csv.writer(fh)
        w.writerow(["total_spp", "mean_lux_lx", "std_lux_lx",
                    "mean_render_s", "std_render_s", "vram_mb"])
        for r in rows:
            w.writerow([r[0], f"{r[1]:.2f}", f"{r[2]:.3f}", f"{r[3]:.3f}", f"{r[4]:.3f}", r[5]])
    print(f"\n[wrote] {OUT_CSV}")

    # validity: render time must rise with totalSpp
    times = [r[3] for r in rows]
    ratio = times[-1] / times[0] if times[0] else float("nan")
    print("\n=== VALIDITY CHECK ===")
    print(f"  render time totalSpp={SPP_LADDER[0]} -> {SPP_LADDER[-1]}: {times[0]:.2f}s -> {times[-1]:.2f}s "
          f"(x{ratio:.1f})")
    if ratio < 1.5:
        print("  [INVALID] render time not scaling with totalSpp -> cold reset not taking.")
        print("            Try increasing the time nudge or app ticks; report back.")
    else:
        print("  [OK] render time scales with totalSpp -> valid convergence curve.")
    ref = rows[-1][1]  # lux at totalSpp=512
    print("\n  deviation vs totalSpp=512 (knee = lowest within 1%):")
    for r in rows:
        dev = abs(r[1]-ref)/ref*100 if ref else float("nan")
        knee = " <-- within 1%" if dev < 1.0 else ""
        print(f"    totalSpp={r[0]:>4}: {dev:5.2f}%{knee}")
    anno.detach(); rp.destroy()


asyncio.ensure_future(run())
print("[benchmark v2] scheduled — totalSpp sweep; keep the GUI open.")
