# =====================================================================
# SUN TIME-OF-DAY DRIVER + TEMPORAL-VARIABILITY TEST (async, Script Editor).
#
# Your sun is driven by Window > Browser > Environments > Time of Day, i.e. the
# Omniverse Sun Study / Dynamic Sky. The Python control is SunstudyPlayer
# (omni.kit.environment.core.get_sunstudy_player), which exposes:
#     current_date  -> "YYYY-MM-DD" (or year/month/day)
#     current_time  -> hours (float, 0..24)
#     latitude / longitude / north_orientation
# (Underlying USD attrs are /Environment.latitude, /Environment.longitude, etc.)
#
# This script:
#   PART A — report current player state + Environment prim attrs (exact paths).
#   PART B — set a single test day to several hours (e.g. 6,9,12,15,18), capture
#            PtIlluminance photopic lux each, and verify lux rises to noon & falls.
#
# Setup: C:\isaacsim\isaac-sim.bat > File>Open Location_A.usd > viewport renderer
#        = RTX Interactive (Path Tracing) > Window>Script Editor > paste > Run.
# =====================================================================

# ---- edit these ----
SAMPLE_PX = (640, 360)               # pixel over a sunlit ROOF (not sky)
TEST_DATE = "2023-06-21"             # a clear summer day
TEST_HOURS = [6.0, 9.0, 12.0, 15.0, 18.0]
# --------------------

import asyncio

import numpy as np
import omni.usd
import omni.replicator.core as rep
from omni.kit.viewport.utility import get_active_viewport

_PHOTOPIC = (0.2126, 0.7152, 0.0722)


def photopic(a):
    a = np.asarray(a, dtype=np.float64)
    return a if a.ndim == 2 else _PHOTOPIC[0]*a[..., 0] + _PHOTOPIC[1]*a[..., 1] + _PHOTOPIC[2]*a[..., 2]


def get_player():
    try:
        from omni.kit.environment.core import get_sunstudy_player
        return get_sunstudy_player()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] get_sunstudy_player unavailable: {type(e).__name__}: {e}")
        return None


def report_state(player):
    print("=== PART A: sun-study state ===")
    if player is not None:
        for attr in ("current_date", "current_time", "start_time", "end_time",
                     "latitude", "longitude", "north_orientation"):
            try:
                print(f"  player.{attr} = {getattr(player, attr)}")
            except Exception as e:  # noqa: BLE001
                print(f"  player.{attr} -> {type(e).__name__}")
    # USD Environment prim attrs (exact paths, for headless control)
    stage = omni.usd.get_context().get_stage()
    for path in ("/Environment", "/World/Environment"):
        prim = stage.GetPrimAtPath(path)
        if prim and prim.IsValid():
            print(f"  Environment prim: {path}  type={prim.GetTypeName()}")
            for a in prim.GetAttributes():
                n = a.GetName().lower()
                if any(k in n for k in ("lat", "lon", "time", "date", "north", "tod")):
                    print(f"      {a.GetName()} = {a.Get()}")


def set_time(player, date_str, hour):
    """Set the sun to date_str + hour via the player (preferred)."""
    ok = False
    if player is not None:
        try:
            player.current_date = date_str
            player.current_time = float(hour)
            ok = True
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] player set failed: {type(e).__name__}: {e}")
    return ok


async def main():
    player = get_player()
    report_state(player)

    print("\n=== PART B: drive one day across hours, measure lux ===")
    vp = get_active_viewport()
    rp = rep.create.render_product(vp.camera_path.pathString, tuple(vp.resolution))
    rep.AnnotatorRegistry.register_annotator_from_aov("PtIlluminance")
    anno = rep.AnnotatorRegistry.get_annotator("PtIlluminance")
    anno.attach(rp)

    x, y = SAMPLE_PX
    print(f"date {TEST_DATE}, pixel {SAMPLE_PX}")
    print(f"{'hour':>6} | {'photopic lux @ px':>18} | {'frame mean lux':>15}")
    print("-" * 48)
    results = []
    for hr in TEST_HOURS:
        if not set_time(player, TEST_DATE, hr):
            print(f"{hr:>6} | (could not set time — see PART A; report the Environment attrs)")
            continue
        await rep.orchestrator.step_async(rt_subframes=64)
        img = photopic(np.asarray(anno.get_data(), dtype=np.float64))
        H, W = img.shape[:2]
        xi, yi = min(x, W-1), min(y, H-1)
        lux = float(np.nanmedian(img[max(0, yi-1):yi+2, max(0, xi-1):xi+2]))
        results.append((hr, lux))
        print(f"{hr:>6.1f} | {lux:>18.1f} | {np.nanmean(img):>15.1f}")

    if results:
        luxes = [l for _, l in results]
        spread = max(luxes) - min(luxes)
        noon_is_peak = results[len(results)//2][1] >= 0.8 * max(luxes)
        print("\n--- verdict ---")
        if spread > 0.05 * max(luxes):
            print(f"PASS: lux varies with time of day (spread {spread:.0f} lux = "
                  f"{spread/max(luxes)*100:.0f}% of max). Temporal variability IS applied.")
            print(f"midday near peak: {noon_is_peak} (expected True for an unshaded point)")
            print("--> We can drive the sweep with player.current_date/current_time.")
        else:
            print(f"FAIL/SUSPECT: lux barely changed (spread {spread:.0f}). Either the sample")
            print("pixel is sky/shadow, or the sun didn't actually move — report PART A.")
    print("\n(cleanup) anno.detach(); rp.destroy()")


asyncio.ensure_future(main())
print("[sun-time] scheduled — PART A prints, then the hourly lux sweep...")
