# =====================================================================
# SPRINT-0 SWEEP (async, Isaac Sim Script Editor) — Location_A, summer + winter.
#
# Drives the Sun Study to each daylight CAMS instant, renders to convergence,
# captures photopic lux at a ROOF pixel, and writes lux_Location_A.csv as
# 'timestamp_utc;lux'. The CAMS join + monolithic assembly happen OUTSIDE, in the
# uv env (Isaac's python has no pandas/pvlib), via solar_twin.dataset.
#
# The instants below were precomputed with pvlib (UTC :00 marks, elevation > 5 deg,
# Sun Study current_time = UTC + longitude/15 = the verified offset). Summer
# 2023-06-21 (14) + winter 2023-12-21 (8) = 22 renders.
#
# Setup: C:\isaacsim\isaac-sim.bat > File>Open Location_A.usd > viewport renderer
#        = RTX Interactive (Path Tracing) > Window>Script Editor > paste > Run.
# =====================================================================

# ---- EDIT: pixel on a sunlit ROOF (not sky/wall). Three ways to get it: ----
#   1. EASIEST: in the viewport, Render Settings > RTX Interactive (Path Tracing)
#      > Common > View > Illuminance, then CLICK the roof. The readout shows
#      e.g. "24872 lux at (506, 418)" — those numbers ARE the pixel. Put them here.
#   2. Run scripts/pick_roof_pixel.py after SELECTING the roof prim — it prints a
#      ready-to-paste ROOF_PX line (projects the prim to a pixel for you).
#   3. Leave the default and accept frame-center (likely not a roof).
#
# loc_A = (483,405)
ROOF_PX = (483,405)            # <-- replace with your roof pixel, e.g. (506, 418)
OUT_CSV = r"C:\Users\Nikos\Documents\Vz Studio\data\raw_synthetic_sprint_0\lux_Location_A.csv"   # written here; move into the package data/ after
RT_SUBFRAMES = 64
LOCATION = "Location_A"
# ----------------------------------------------------------------------

# Precomputed daylight instants (UTC, Sun-Study date, current_time, elevation).
INSTANTS = [
    {"utc":"2023-06-21T04:00:00Z","date":"2023-06-21","ct":5.583,"elev":9.4},
    {"utc":"2023-06-21T05:00:00Z","date":"2023-06-21","ct":6.583,"elev":20.5},
    {"utc":"2023-06-21T06:00:00Z","date":"2023-06-21","ct":7.583,"elev":32.1},
    {"utc":"2023-06-21T07:00:00Z","date":"2023-06-21","ct":8.583,"elev":43.9},
    {"utc":"2023-06-21T08:00:00Z","date":"2023-06-21","ct":9.583,"elev":55.5},
    {"utc":"2023-06-21T09:00:00Z","date":"2023-06-21","ct":10.583,"elev":66.5},
    {"utc":"2023-06-21T10:00:00Z","date":"2023-06-21","ct":11.583,"elev":74.4},
    {"utc":"2023-06-21T11:00:00Z","date":"2023-06-21","ct":12.583,"elev":73.8},
    {"utc":"2023-06-21T12:00:00Z","date":"2023-06-21","ct":13.583,"elev":65.4},
    {"utc":"2023-06-21T13:00:00Z","date":"2023-06-21","ct":14.583,"elev":54.3},
    {"utc":"2023-06-21T14:00:00Z","date":"2023-06-21","ct":15.583,"elev":42.7},
    {"utc":"2023-06-21T15:00:00Z","date":"2023-06-21","ct":16.583,"elev":30.9},
    {"utc":"2023-06-21T16:00:00Z","date":"2023-06-21","ct":17.583,"elev":19.3},
    {"utc":"2023-06-21T17:00:00Z","date":"2023-06-21","ct":18.583,"elev":8.2},
    {"utc":"2023-12-21T07:00:00Z","date":"2023-12-21","ct":8.583,"elev":12.4},
    {"utc":"2023-12-21T08:00:00Z","date":"2023-12-21","ct":9.583,"elev":20.1},
    {"utc":"2023-12-21T09:00:00Z","date":"2023-12-21","ct":10.583,"elev":25.6},
    {"utc":"2023-12-21T10:00:00Z","date":"2023-12-21","ct":11.583,"elev":28.4},
    {"utc":"2023-12-21T11:00:00Z","date":"2023-12-21","ct":12.583,"elev":28.4},
    {"utc":"2023-12-21T12:00:00Z","date":"2023-12-21","ct":13.583,"elev":25.6},
    {"utc":"2023-12-21T13:00:00Z","date":"2023-12-21","ct":14.583,"elev":18.4},
    {"utc":"2023-12-21T14:00:00Z","date":"2023-12-21","ct":15.583,"elev":10.3},
]

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
    env = stage.GetPrimAtPath("/Environment")
    try:
        env.GetAttribute("date").Set(date_str)
        env.GetAttribute("time:current").Set(float(hour))
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] set time failed: {type(e).__name__}: {e}")
        return False


async def main():
    stage = omni.usd.get_context().get_stage()
    vp = get_active_viewport()
    rp = rep.create.render_product(vp.camera_path.pathString, tuple(vp.resolution))
    rep.AnnotatorRegistry.register_annotator_from_aov("PtIlluminance")
    anno = rep.AnnotatorRegistry.get_annotator("PtIlluminance")
    anno.attach(rp)

    x, y = ROOF_PX
    out = []
    print(f"=== Sprint-0 sweep: {LOCATION}, {len(INSTANTS)} instants, roof pixel {ROOF_PX} ===")
    print(f"{'utc':>22} | {'ct':>6} | {'elev':>5} | {'lux':>10}")
    for i, rec in enumerate(INSTANTS, 1):
        if not set_env_time(stage, rec["date"], rec["ct"]):
            continue
        await rep.orchestrator.step_async(rt_subframes=RT_SUBFRAMES)
        img = photopic(np.asarray(anno.get_data(), dtype=np.float64))
        H, W = img.shape[:2]
        xi, yi = min(x, W-1), min(y, H-1)
        lux = float(np.nanmedian(img[max(0, yi-1):yi+2, max(0, xi-1):xi+2]))
        out.append((rec["utc"], lux))
        print(f"{rec['utc']:>22} | {rec['ct']:>6.2f} | {rec['elev']:>5.1f} | {lux:>10.1f}")

    # write timestamp_utc;lux (semicolon, like CAMS)
    with open(OUT_CSV, "w", encoding="utf-8") as fh:
        fh.write("timestamp_utc;lux\n")
        for utc, lux in out:
            fh.write(f"{utc};{lux:.1f}\n")
    print(f"\nWROTE {len(out)} rows -> {OUT_CSV}")
    print("Next (outside Isaac, in the uv env): join to CAMS + assemble monolithic via")
    print("  solar_twin.dataset.assemble_location(read_lux_csv(...), to_instantaneous(read_cams(...)), ...)")
    print("\n(cleanup) anno.detach(); rp.destroy()")


asyncio.ensure_future(main())
print("[sprint0] scheduled — sweeping 22 instants, ~%d subframes each..." % RT_SUBFRAMES)
