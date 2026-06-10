r"""Diagnose the ~17x-low headless lux: is it sun INTENSITY, or the PIXEL/shadow?

Headless production gave a correct-SHAPE daily bell but ~17x too LOW magnitude
(winter noon 883 lux vs 14873 in the GUI Sprint-0, same roof). Position works,
brightness doesn't. This script, run headless like the sweep, distinguishes the
two causes at one bright instant (2023-06-21 12:00, summer noon):

  - frame MAX lux: if the WHOLE frame maxes ~15x below the GUI's ~35000, the sun
    INTENSITY isn't applied headless (global) -> not a pixel problem.
  - the sun DistantLight intensity + dynamic-sky settings (print them).
  - a coarse pixel grid: shows the brightest pixel + the value at (484,397) and
    (506,418), to rule out a dark/shadowed pixel.

Run:
    C:\isaacsim\python.bat ^
      "C:\Users\Nikos\Documents\Vz Studio\USD_Extractor_Calibrator_Package\scripts\diag_intensity.py" ^
      --stage "C:\dev\solar-digital-twin-migration\01_old_composer_export\Location_A.usd"
"""
from __future__ import annotations

import argparse

p = argparse.ArgumentParser()
p.add_argument("--stage", required=True)
p.add_argument("--camera", default="/World/Camera")
p.add_argument("--res", type=int, nargs=2, default=[1280, 720])
p.add_argument("--rt-subframes", type=int, default=64)
args, _ = p.parse_known_args()

from isaacsim import SimulationApp  # noqa: E402

sim = SimulationApp({"headless": True,
                     "rtx-transient.aov.enableRtxAovs": True,
                     "rtx-transient.aov.enableRtxAovsSecondary": True})

import numpy as np  # noqa: E402
import carb  # noqa: E402
import omni.usd  # noqa: E402
import omni.replicator.core as rep  # noqa: E402
from isaacsim.core.utils.extensions import enable_extension  # noqa: E402
from pxr import UsdLux  # noqa: E402

enable_extension("omni.kit.environment.core")
for _ in range(10):
    sim.update()

_P = (0.2126, 0.7152, 0.0722)


def main():
    omni.usd.get_context().open_stage(args.stage)
    for _ in range(60):
        sim.update()
    rep.settings.set_render_pathtraced(samples_per_pixel=1)
    s = carb.settings.get_settings()
    for k, v in {"/rtx/pathtracing/denoiser/enabled": False,
                 "/rtx/post/tonemap/enabled": False}.items():
        try:
            s.set(k, v)
        except Exception:  # noqa: BLE001
            pass

    stage = omni.usd.get_context().get_stage()
    env = stage.GetPrimAtPath("/Environment")

    # set summer noon (the brightest case)
    try:
        from omni.kit.environment.core import get_sunstudy_player
        pl = get_sunstudy_player()
        pl.current_date = "2023-06-21"; pl.current_time = 12.0
    except Exception:  # noqa: BLE001
        pl = None
    if env and env.IsValid():
        env.GetAttribute("date").Set("2023-06-21")
        env.GetAttribute("time:current").Set(12.0)
    for _ in range(5):
        sim.update()

    rp = rep.create.render_product(args.camera, tuple(args.res))
    rep.AnnotatorRegistry.register_annotator_from_aov("PtIlluminance")
    anno = rep.AnnotatorRegistry.get_annotator("PtIlluminance")
    anno.attach(rp)
    rep.orchestrator.step(rt_subframes=args.rt_subframes)

    a = np.asarray(anno.get_data(), dtype=np.float64)
    img = _P[0]*a[..., 0] + _P[1]*a[..., 1] + _P[2]*a[..., 2] if a.ndim == 3 else a
    print("\n=== summer-noon illuminance frame ===")
    print(f"  frame: min={np.nanmin(img):.0f}  MAX={np.nanmax(img):.0f}  mean={np.nanmean(img):.0f}")
    print(f"  GUI Sprint-0 reference: frame max was ~35000, roof pixel ~27000 lux")
    print(f"  -> if MAX here is ~2000-3000, the SUN INTENSITY is ~15x low (global), not the pixel.")
    for (px, py, tag) in [(484, 397, "this-run pixel"), (506, 418, "sprint-0 pixel"),
                          (640, 360, "frame center")]:
        H, W = img.shape[:2]
        xi, yi = min(px, W-1), min(py, H-1)
        v = float(np.nanmedian(img[max(0, yi-1):yi+2, max(0, xi-1):xi+2]))
        print(f"  pixel ({px},{py}) [{tag}]: {v:.0f} lux")

    # brightest pixel location
    yx = np.unravel_index(int(np.nanargmax(img)), img.shape[:2])
    print(f"  brightest pixel at (x={yx[1]}, y={yx[0]}) = {np.nanmax(img):.0f} lux")

    print("\n=== sun / sky settings ===")
    # DistantLight intensity, if the sky uses one
    for prim in stage.Traverse():
        if prim.GetTypeName() == "DistantLight":
            li = UsdLux.DistantLight(prim)
            try:
                print(f"  DistantLight {prim.GetPath()} intensity={li.GetIntensityAttr().Get()}")
            except Exception:  # noqa: BLE001
                pass
    for key in ["/rtx/sceneDb/ambientLightIntensity", "/rtx/post/tonemap/enabled",
                "/rtx/post/histogram/enabled", "/rtx/pathtracing/autoExposure/enabled"]:
        try:
            print(f"  {key} = {s.get(key)}")
        except Exception:  # noqa: BLE001
            pass
    print("\nReport the frame MAX + the two pixel values + DistantLight intensity.")


try:
    main()
finally:
    sim.close()
