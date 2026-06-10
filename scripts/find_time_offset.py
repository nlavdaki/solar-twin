# =====================================================================
# PIN THE Sun-Study TIME OFFSET (async, Isaac Sim Script Editor).
#
# WHY THIS IS CRITICAL: Sun Study `current_time` is NOT UTC. From the June-21 run,
# the lux peak (solar noon) fell at current_time ~12.03, while pvlib's UTC solar
# noon that day is 10.45 UTC -> implied offset +1.58 h, which equals longitude/15
# (mean solar time), NOT the standard Athens zone +2.00. CAMS is in UTC, so the
# sweep must convert: current_time = UTC_hour + offset. We confirm `offset` here,
# in BOTH summer and winter, so the whole 25k-40k sweep is time-correct (dossier
# 03 temporal validation, <1 deg).
#
# Method: for each test date, finely sweep current_time around local noon, capture
# photopic lux, fit a parabola to find the lux-peak current_time = Sun Study solar
# noon. The script prints it; compare to pvlib UTC solar noon to read the offset.
#
# Setup: C:\isaacsim\isaac-sim.bat > Open Location_A.usd > RTX Interactive (Path
# Tracing) > Window>Script Editor > paste > Run.
# =====================================================================

# ---- edit if needed ----
SAMPLE_PX = (640, 360)
TEST_DATES = ["2023-06-21", "2023-12-21"]        # summer & winter
TIME_SWEEP = [10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0, 13.5, 14.0]
# pvlib UTC solar noon for Athens (precomputed): summer 10.45, winter 10.38
PVLIB_UTC_NOON = {"2023-06-21": 10.45, "2023-12-21": 10.38}
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


def set_env_time(stage, date_str, hour):
    """Set time directly on the /Environment USD attrs (headless-safe, no UI player)."""
    env = stage.GetPrimAtPath("/Environment")
    ok = True
    try:
        env.GetAttribute("date").Set(date_str)
        env.GetAttribute("time:current").Set(float(hour))
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] USD set failed: {type(e).__name__}: {e}")
        ok = False
    # also try the player as a belt-and-suspenders
    try:
        from omni.kit.environment.core import get_sunstudy_player
        p = get_sunstudy_player()
        if p is not None:
            p.current_date = date_str
            p.current_time = float(hour)
    except Exception:
        pass
    return ok


async def main():
    stage = omni.usd.get_context().get_stage()
    vp = get_active_viewport()
    rp = rep.create.render_product(vp.camera_path.pathString, tuple(vp.resolution))
    rep.AnnotatorRegistry.register_annotator_from_aov("PtIlluminance")
    anno = rep.AnnotatorRegistry.get_annotator("PtIlluminance")
    anno.attach(rp)
    x, y = SAMPLE_PX

    print("=== pinning Sun-Study time offset (current_time - UTC) ===")
    for date in TEST_DATES:
        print(f"\n--- {date} ---")
        print(f"{'current_time':>12} | {'photopic lux':>13}")
        cts, luxes = [], []
        for ct in TIME_SWEEP:
            set_env_time(stage, date, ct)
            await rep.orchestrator.step_async(rt_subframes=48)
            img = photopic(np.asarray(anno.get_data(), dtype=np.float64))
            H, W = img.shape[:2]
            xi, yi = min(x, W-1), min(y, H-1)
            lux = float(np.nanmedian(img[max(0, yi-1):yi+2, max(0, xi-1):xi+2]))
            cts.append(ct); luxes.append(lux)
            print(f"{ct:>12.2f} | {lux:>13.1f}")
        cts, luxes = np.array(cts), np.array(luxes)
        # parabola peak around the max sample
        k = int(np.argmax(luxes))
        lo, hi = max(0, k-2), min(len(cts), k+3)
        c = np.polyfit(cts[lo:hi], luxes[lo:hi], 2)
        peak_ct = -c[1] / (2*c[0])
        utc_noon = PVLIB_UTC_NOON.get(date)
        offset = peak_ct - utc_noon if utc_noon else float("nan")
        print(f"  Sun-Study solar noon current_time = {peak_ct:.3f}")
        print(f"  pvlib UTC solar noon              = {utc_noon} UTC")
        print(f"  => OFFSET current_time - UTC      = {offset:.3f} h")
        print(f"     (+2.00 = std zone | +1.58 = longitude/15 mean solar)")

    print("\n--- conclusion ---")
    print("If summer offset == winter offset (within ~0.05 h), there is NO DST and the")
    print("sweep rule is: current_time = CAMS_UTC_hour + offset. Report both offsets.")
    print("\n(cleanup) anno.detach(); rp.destroy()")


asyncio.ensure_future(main())
print("[time-offset] scheduled — summer then winter sweep...")
