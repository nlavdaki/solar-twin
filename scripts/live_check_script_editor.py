# =====================================================================
# LIVE ILLUMINANCE CHECK (async, for Isaac Sim Script Editor).
#
# Setup (full Isaac Sim, not USD Composer):
#   1. C:\isaacsim\isaac-sim.bat   (or isaac-sim.selector.bat -> "Isaac Sim Full")
#   2. File > Open -> Location_A.usd
#   3. Viewport renderer -> RTX - Interactive (Path Tracing)
#   4. Window > Script Editor, paste this whole file, press Run.
#
# Captures PtIlluminance from the ACTIVE viewport camera and reports, at one pixel:
#   - all 4 raw channels (R/G/B illuminance + alpha)
#   - the PHOTOPIC lux = 0.2126R + 0.7152G + 0.0722B  <-- what a lux meter reads
#   - the renderer's own scalar /rtx/pathtracing/illuminanceVal (viewport value)
# so we can confirm which combination matches the viewport's "Illuminance value".
#
# NOTE on convergence: if the viewport has been rendering this static scene for a
# while it is ALREADY converged, so rt_subframes rows will look identical. That is
# expected here. The real convergence floor must be measured STANDALONE (fresh
# render per frame) — see scripts/measure_convergence.py (headless).
#
# NOTE on the picker showing pixel (-2147483648, ...): that INT_MIN is "no valid
# pixel". Creating a second render product can disturb viewport picking; if the
# viewport picker misbehaves, just restart Isaac and click BEFORE running this,
# or rely on the printed photopic value (it is the same quantity).
# =====================================================================

# ---- edit these ----
PIXEL_XY = (640, 360)          # pixel to read; click the SAME spot in the viewport
TOKEN = "PtIlluminance"
# --------------------

import asyncio

import numpy as np
import carb
import omni.replicator.core as rep
from omni.kit.viewport.utility import get_active_viewport

_PHOTOPIC = (0.2126, 0.7152, 0.0722)


async def run_live_check():
    settings = carb.settings.get_settings()
    for k, v in {
        "/rtx/pathtracing/denoiser/enabled": False,
        "/rtx/post/tonemap/enabled": False,
        "/rtx/post/dlss/execMode": 0,
    }.items():
        try:
            settings.set(k, v)
        except Exception:
            pass

    vp = get_active_viewport()
    cam_path = vp.camera_path.pathString
    res = tuple(vp.resolution)
    print(f"[live] active camera: {cam_path}  | viewport resolution: {res}")

    rp = rep.create.render_product(cam_path, res)
    rep.AnnotatorRegistry.register_annotator_from_aov(TOKEN)
    anno = rep.AnnotatorRegistry.get_annotator(TOKEN)
    anno.attach(rp)

    # one converged render is enough on a static, already-accumulating viewport
    await rep.orchestrator.step_async(rt_subframes=64)
    a = np.asarray(anno.get_data(), dtype=np.float64)

    x, y = PIXEL_XY
    H, W = a.shape[:2]
    xi, yi = min(x, W - 1), min(y, H - 1)
    px = a[yi, xi]   # the 4 channels at the exact pixel

    print(f"\n=== values at pixel {PIXEL_XY} ===")
    if a.ndim == 3 and a.shape[-1] >= 3:
        r, g, b = float(px[0]), float(px[1]), float(px[2])
        alpha = float(px[3]) if a.shape[-1] > 3 else float("nan")
        photopic = _PHOTOPIC[0] * r + _PHOTOPIC[1] * g + _PHOTOPIC[2] * b
        print(f"  ch0 (R illuminance): {r:.1f}")
        print(f"  ch1 (G illuminance): {g:.1f}")
        print(f"  ch2 (B illuminance): {b:.1f}")
        print(f"  ch3 (alpha):         {alpha:.3f}")
        print(f"  --> PHOTOPIC lux (0.2126R+0.7152G+0.0722B): {photopic:.1f}")
        print(f"  (for reference) simple mean R,G,B:          {(r + g + b) / 3:.1f}")
        print(f"  (for reference) sum R+G+B:                  {r + g + b:.1f}")

    # the renderer's own scalar illuminance (what the viewport View>Illuminance shows)
    for key in ("/rtx/pathtracing/illuminanceVal", "/rtx/pathtracing/illuminance"):
        try:
            v = settings.get(key)
            if v is not None:
                print(f"  renderer scalar {key} = {v}")
        except Exception:
            pass

    print("\nCompare the PHOTOPIC value above to the viewport's")
    print("  Render Settings > RTX Interactive (Path Tracing) > Common > View > Illuminance")
    print("  'value at last clicked position' (click the SAME pixel).")
    print("Tell me which printed line matches the viewport — that locks our formula.")
    print("\n(cleanup) anno.detach(); rp.destroy()")


asyncio.ensure_future(run_live_check())
print("[live] scheduled — results will stream into this console...")
