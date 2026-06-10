# =====================================================================
# TEMPORAL-VARIABILITY GATE (async, Isaac Sim Script Editor).
#
# Question this answers: when we change the time of day, does the extracted
# illuminance actually change? If not, every timestamp would yield identical lux
# and the dataset would be worthless. We must prove this BEFORE calibration.
#
# What it does:
#   PART A — inspect: walk the stage and report every light (DistantLight/DomeLight),
#            the Dynamic-Sky / Environment prim, and any time/date/lat/lon/north
#            attributes, with their exact prim paths + current values.
#   PART B — test: drive the sun to several elevations (by rotating the DistantLight
#            it finds, the most deterministic method) and capture PtIlluminance
#            photopic lux each time. Expect lux LOW at low sun, HIGH near noon.
#
# Setup: full Isaac Sim (C:\isaacsim\isaac-sim.bat) > File>Open Location_A.usd >
# viewport renderer = RTX Interactive (Path Tracing) > Window>Script Editor >
# paste this > Run.
# =====================================================================

# ---- edit if needed ----
SAMPLE_PX = (640, 360)     # pixel to watch; pick one over a sunlit ROOF, not sky
TEST_ELEVATIONS = [5, 20, 45, 70]   # degrees above horizon to drive the sun to
# ------------------------

import asyncio

import numpy as np
import omni.usd
import omni.replicator.core as rep
from pxr import Usd, UsdGeom, UsdLux, Gf
from omni.kit.viewport.utility import get_active_viewport

_PHOTOPIC = (0.2126, 0.7152, 0.0722)
_TIME_KEYS = ("time", "date", "tod", "latitude", "longitude", "north",
              "sunposition", "sunintensity", "azimuth", "elevation")


def photopic(a):
    a = np.asarray(a, dtype=np.float64)
    return a if a.ndim == 2 else _PHOTOPIC[0]*a[..., 0] + _PHOTOPIC[1]*a[..., 1] + _PHOTOPIC[2]*a[..., 2]


def inspect_stage():
    stage = omni.usd.get_context().get_stage()
    lights, sky_like = [], []
    for prim in stage.Traverse():
        tname = prim.GetTypeName()
        if tname in ("DistantLight", "DomeLight", "SphereLight", "RectLight"):
            lights.append(prim)
        # Dynamic Sky / Environment prims often carry time/date attrs
        attrs = [a.GetName() for a in prim.GetAttributes()]
        if any(any(k in a.lower() for k in _TIME_KEYS) for a in attrs):
            sky_like.append(prim)

    print("=== PART A: stage inspection ===")
    print(f"\nLights ({len(lights)}):")
    for p in lights:
        print(f"  {p.GetTypeName():12} {p.GetPath()}")
        if p.GetTypeName() == "DistantLight":
            li = UsdLux.DistantLight(p)
            try:
                inten = li.GetIntensityAttr().Get()
                print(f"               intensity={inten}")
            except Exception:
                pass

    print(f"\nPrims with time/date/geo-like attributes ({len(sky_like)}):")
    for p in sky_like:
        hits = [a.GetName() for a in p.GetAttributes()
                if any(k in a.GetName().lower() for k in _TIME_KEYS)]
        print(f"  {p.GetPath()}  ({p.GetTypeName()})")
        for h in hits:
            try:
                val = p.GetAttribute(h).Get()
            except Exception:
                val = "?"
            print(f"      {h} = {val}")
    return stage, lights


def set_distant_light_elevation(stage, light_prim, elev_deg, azimuth_deg=180.0):
    """Point a DistantLight so the sun sits at (elevation, azimuth).
    DistantLight emits along its local -Z (default points down +? ) so we set the
    prim's xform rotation. We rotate: first elevation about X, then azimuth about Y.
    """
    xform = UsdGeom.Xformable(light_prim)
    # clear existing rotate ops we add, keep translate
    xform.ClearXformOpOrder()
    rotX = xform.AddRotateXOp()
    rotY = xform.AddRotateYOp()
    # elevation: 90 = straight down (noon-ish); we map elev so 90deg sun -> light points down
    rotX.Set(-(90.0 - elev_deg))   # tilt from horizon
    rotY.Set(azimuth_deg)


async def test_variability(stage, lights):
    print("\n=== PART B: temporal-variability test ===")
    distants = [p for p in lights if p.GetTypeName() == "DistantLight"]
    if not distants:
        print("No DistantLight found to rotate. Inspect PART A for a Dynamic-Sky time")
        print("attribute instead, and tell me its path — I'll drive that directly.")
        return
    sun = distants[0]
    print(f"Driving sun: {sun.GetPath()}  (rotating to elevations {TEST_ELEVATIONS})")

    vp = get_active_viewport()
    rp = rep.create.render_product(vp.camera_path.pathString, tuple(vp.resolution))
    rep.AnnotatorRegistry.register_annotator_from_aov("PtIlluminance")
    anno = rep.AnnotatorRegistry.get_annotator("PtIlluminance")
    anno.attach(rp)

    x, y = SAMPLE_PX
    print(f"\n{'elevation(deg)':>14} | {'photopic lux @ pixel':>20} | {'frame mean lux':>15}")
    print("-" * 56)
    results = []
    for elev in TEST_ELEVATIONS:
        set_distant_light_elevation(stage, sun, elev)
        await rep.orchestrator.step_async(rt_subframes=64)
        img = photopic(np.asarray(anno.get_data(), dtype=np.float64))
        H, W = img.shape[:2]
        xi, yi = min(x, W-1), min(y, H-1)
        lux = float(np.nanmedian(img[max(0, yi-1):yi+2, max(0, xi-1):xi+2]))
        results.append((elev, lux))
        print(f"{elev:>14} | {lux:>20.1f} | {np.nanmean(img):>15.1f}")

    luxes = [l for _, l in results]
    spread = max(luxes) - min(luxes)
    rising = all(luxes[i] <= luxes[i+1] + 1 for i in range(len(luxes)-1))
    print("\n--- verdict ---")
    if spread > 0.05 * max(luxes):
        print(f"PASS: lux changes with sun elevation (spread {spread:.0f} lux, "
              f"{spread/max(luxes)*100:.0f}% of max). Temporal variability IS applied.")
        print("monotonic-rising with elevation:" , rising,
              "(expected True for an unshaded point)")
    else:
        print(f"FAIL/SUSPECT: lux barely changed (spread {spread:.0f} lux). Either the")
        print("sample pixel is sky/shadow, or the DistantLight isn't the active sun")
        print("(a Dynamic Sky may override it). Send PART A output and we adjust.")
    print("\n(cleanup) anno.detach(); rp.destroy()")


async def main():
    stage, lights = inspect_stage()
    await test_variability(stage, lights)


asyncio.ensure_future(main())
print("[temporal-test] scheduled — inspection prints first, then the elevation sweep...")
