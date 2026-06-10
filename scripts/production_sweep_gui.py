# =====================================================================
# PRODUCTION SWEEP — GUI Script-Editor version (async).
#
# WHY: the headless MDL dynamic sky doesn't light the scene (sun disk doesn't fire
# headless -> flat ~1100 lux). But in the FULL GUI it lights correctly (Sprint-0
# gave viewport-verified ~24800 lux). So we run the PROVEN GUI lighting, automated:
# the production schedule + checkpoint/resume + lux_<LOC>.csv, driven from the
# Script Editor. Combines Sprint-0's correct lighting with the production pipeline.
#
# SETUP:
#   1. C:\isaacsim\isaac-sim.bat  (full GUI)
#   2. File > Open -> Location_A.usd
#   3. Viewport renderer -> RTX - Interactive (Path Tracing)
#   4. Window > Script Editor, set the CONFIG below, paste this whole file, Run.
#
# It runs in the GUI window (viewport visible — useful to watch). Checkpoint/resume:
# rerun and it skips timestamps already in the CSV, so a crash costs nothing.
# The session must stay open while it runs (hours per location).
# =====================================================================

# ---- CONFIG (edit per location) ----
SCHEDULE_CSV = r"C:/Users/Nikos/Documents/Vz Studio/data/extraction_schedule/schedule_Location_A.csv"
OUT_CSV      = r"C:/Users/Nikos/Documents/Vz Studio/data/lux_csv/lux_Location_A.csv"
ROOF_PX      = (506, 418)     # pixel on a sunlit roof (View>Illuminance click readout)
RT_SUBFRAMES = 24             # convergence; Sprint-0 was stable by ~16
SKY_SETTLE_FRAMES = 3         # app-update ticks after setting time, so the sky recomputes
FLUSH_EVERY  = 10
# ------------------------------------

import asyncio
import csv
import os

import numpy as np
import omni.kit.app
import omni.usd
import omni.replicator.core as rep
from omni.kit.viewport.utility import get_active_viewport

_P = (0.2126, 0.7152, 0.0722)


def _read_schedule(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def _already_done(path):
    done = set()
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                done.add(r["timestamp_utc"])
    return done


async def _tick(n):
    for _ in range(n):
        await omni.kit.app.get_app().next_update_async()


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

    async def set_sun(date_str, ct):
        if env and env.IsValid():
            env.GetAttribute("date").Set(date_str)
            env.GetAttribute("time:current").Set(float(ct))
        if player is not None:
            try:
                player.current_date = date_str
                player.current_time = float(ct)
            except Exception:
                pass
        await _tick(SKY_SETTLE_FRAMES)

    async def sample_lux():
        await rep.orchestrator.step_async(rt_subframes=RT_SUBFRAMES)
        a = np.asarray(anno.get_data(), dtype=np.float64)
        img = _P[0]*a[..., 0] + _P[1]*a[..., 1] + _P[2]*a[..., 2] if a.ndim == 3 else a
        H, W = img.shape[:2]
        xi, yi = min(x, W-1), min(y, H-1)
        return float(np.nanmedian(img[max(0, yi-1):yi+2, max(0, xi-1):xi+2]))

    # SELF-CHECK: sun must move AND scene must be lit (contrast), before hours of work.
    await set_sun("2023-06-21", 6.0);  dawn = await sample_lux()
    await set_sun("2023-06-21", 12.0); noon = await sample_lux()
    print(f"[selfcheck] dawn={dawn:.0f}  noon={noon:.0f} lux")
    if noon < 5000 or abs(noon - dawn) < 0.1 * noon:
        print("[ABORT] noon lux too low or ~equal to dawn — lighting not working in this "
              "session. Confirm renderer = RTX Interactive (Path Tracing) and the sky is lit.")
        return
    print("[selfcheck] OK — lit and sun moves; starting sweep.")

    sched = _read_schedule(SCHEDULE_CSV)
    done = _already_done(OUT_CSV)
    todo = [r for r in sched if r["timestamp_utc"] not in done]
    print(f"[sweep] schedule={len(sched)} done={len(done)} remaining={len(todo)}")

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    new = not os.path.exists(OUT_CSV)
    fh = open(OUT_CSV, "a", newline="", encoding="utf-8")
    w = csv.writer(fh, delimiter=";")
    if new:
        w.writerow(["timestamp_utc", "lux"])

    for i, r in enumerate(todo, 1):
        await set_sun(r["sun_study_date"], r["sun_study_current_time"])
        lux = await sample_lux()
        w.writerow([r["timestamp_utc"], f"{lux:.1f}"])
        fh.flush(); os.fsync(fh.fileno())          # flush EVERY row: instant, crash-safe
        print(f"[sweep] {i}/{len(todo)}  {r['timestamp_utc']}  lux={lux:.0f}")
    fh.flush(); fh.close()
    print(f"[sweep] DONE — wrote {len(todo)} rows to {OUT_CSV}")
    anno.detach(); rp.destroy()


asyncio.ensure_future(run())
print("[production-gui] scheduled — runs in this GUI session; keep it open.")
