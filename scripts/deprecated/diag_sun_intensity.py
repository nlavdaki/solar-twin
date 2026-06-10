r"""Prove the headless direct-sun problem + test the fix, at summer noon.

diag_intensity showed a FLAT ~1100-lux frame (no shadows) and DistantLight
intensity=5000 -> the direct sun isn't contributing headless, only the sky dome.
The GUI's dynamic-sky atmospheric model drove the sun to physical daylight; the
headless app doesn't. Since we already drive the sun POSITION ourselves, the
robust fix is to also drive its INTENSITY. This script tests that:

  STEP 1  baseline render -> frame max + contrast (max/median). Flat = no sun.
  STEP 2  find the sun DistantLight; print intensity, visibility, enabled flags.
  STEP 3  set DistantLight intensity high, tick, re-render -> if lux rises AND
          contrast appears (shadows), the fix is "drive intensity ourselves".

Run:
    C:\isaacsim\python.bat ^
      "C:\Users\Nikos\Documents\Vz Studio\USD_Extractor_Calibrator_Package\scripts\diag_sun_intensity.py" ^
      --stage "C:\dev\solar-digital-twin-migration\01_old_composer_export\Location_A.usd"
"""
from __future__ import annotations

import argparse

p = argparse.ArgumentParser()
p.add_argument("--stage", required=True)
p.add_argument("--camera", default="/World/Camera")
p.add_argument("--res", type=int, nargs=2, default=[1280, 720])
p.add_argument("--rt-subframes", type=int, default=48)
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
from pxr import UsdLux, UsdGeom, Sdf  # noqa: E402

enable_extension("omni.kit.environment.core")
for _ in range(10):
    sim.update()

_P = (0.2126, 0.7152, 0.0722)


def render_stats(anno):
    rep.orchestrator.step(rt_subframes=args.rt_subframes)
    a = np.asarray(anno.get_data(), dtype=np.float64)
    img = _P[0]*a[..., 0] + _P[1]*a[..., 1] + _P[2]*a[..., 2] if a.ndim == 3 else a
    med = float(np.nanmedian(img))
    mx = float(np.nanmax(img))
    contrast = mx / med if med > 0 else float("nan")
    return mx, med, contrast


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
    try:
        from omni.kit.environment.core import get_sunstudy_player
        pl = get_sunstudy_player()
        pl.current_date = "2023-06-21"; pl.current_time = 12.0
    except Exception:  # noqa: BLE001
        pass
    if env and env.IsValid():
        env.GetAttribute("date").Set("2023-06-21")
        env.GetAttribute("time:current").Set(12.0)
    for _ in range(5):
        sim.update()

    rp = rep.create.render_product(args.camera, tuple(args.res))
    rep.AnnotatorRegistry.register_annotator_from_aov("PtIlluminance")
    anno = rep.AnnotatorRegistry.get_annotator("PtIlluminance")
    anno.attach(rp)

    mx, med, c = render_stats(anno)
    print("\n=== STEP 1 baseline (summer noon) ===")
    print(f"  frame max={mx:.0f}  median={med:.0f}  contrast(max/med)={c:.2f}")
    print("  (contrast ~1 = flat = no direct sun; >3 = real sun+shadows)")

    # find the sun light
    sun = None
    for prim in stage.Traverse():
        if prim.GetTypeName() == "DistantLight":
            sun = prim
            break
    print("\n=== STEP 2 sun light ===")
    if sun is None:
        print("  no DistantLight found!")
        return
    li = UsdLux.DistantLight(sun)
    print(f"  path: {sun.GetPath()}")
    print(f"  intensity: {li.GetIntensityAttr().Get()}")
    try:
        img_ = UsdGeom.Imageable(sun)
        print(f"  visibility: {img_.GetVisibilityAttr().Get()}")
    except Exception:  # noqa: BLE001
        pass
    for an in sun.GetAttributes():
        n = an.GetName().lower()
        if any(k in n for k in ("enable", "intensity", "exposure", "angle", "color")):
            try:
                print(f"    {an.GetName()} = {an.Get()}")
            except Exception:  # noqa: BLE001
                pass

    print("\n=== STEP 3 bump DistantLight intensity x20 (5000 -> 100000), re-render ===")
    li.GetIntensityAttr().Set(100000.0)
    for _ in range(5):
        sim.update()
    mx2, med2, c2 = render_stats(anno)
    print(f"  frame max={mx2:.0f}  median={med2:.0f}  contrast={c2:.2f}")
    print(f"  ratio vs baseline: max x{mx2/mx:.1f}  median x{med2/med:.1f}")
    print("\n  INTERPRETATION:")
    print("   - if max jumped ~20x AND contrast rose (>3): FIX = drive DistantLight")
    print("     intensity ourselves (sun works, just wasn't bright headless).")
    print("   - if nothing changed: the DistantLight isn't the render's sun headless")
    print("     (deeper sky-model issue) — report and we try the sky intensity path.")


try:
    main()
finally:
    sim.close()
