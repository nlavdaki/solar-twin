r"""Test whether a NEW sun light WE add illuminates the scene headless.

STEP-3 proved the existing /Environment/sky/.../DistantLight does NOT light the
scene headless (bumping it 20x did nothing) — the MDL dynamic sky drives the
render and its sun doesn't fire headless. This tests the pivot: add our OWN
UsdLux.DistantLight at the stage root, point it like the summer-noon sun, and see
if real lighting + shadows appear (contrast >> 1).

If this works, the production architecture becomes: drive our own light (direction
from pvlib, fixed intensity) instead of the MDL sky's date/time. Per-location
lux=a*GHI+b absorbs the absolute scale; shadows/geometry are what matter.

Run:
    C:\isaacsim\python.bat ^
      "C:\Users\Nikos\Documents\Vz Studio\USD_Extractor_Calibrator_Package\scripts\diag_add_light.py" ^
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
from pxr import UsdLux, UsdGeom, Gf, Sdf  # noqa: E402

enable_extension("omni.kit.environment.core")
for _ in range(10):
    sim.update()

_P = (0.2126, 0.7152, 0.0722)


def stats(anno):
    rep.orchestrator.step(rt_subframes=args.rt_subframes)
    a = np.asarray(anno.get_data(), dtype=np.float64)
    img = _P[0]*a[..., 0] + _P[1]*a[..., 1] + _P[2]*a[..., 2] if a.ndim == 3 else a
    med = float(np.nanmedian(img))
    return float(np.nanmax(img)), med, (float(np.nanmax(img))/med if med > 0 else float("nan"))


def main():
    ctx = omni.usd.get_context()
    ctx.open_stage(args.stage)
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

    stage = ctx.get_stage()
    up = UsdGeom.GetStageUpAxis(stage)
    print(f"\nstage up-axis = {up}")

    rp = rep.create.render_product(args.camera, tuple(args.res))
    rep.AnnotatorRegistry.register_annotator_from_aov("PtIlluminance")
    anno = rep.AnnotatorRegistry.get_annotator("PtIlluminance")
    anno.attach(rp)

    mx0, md0, c0 = stats(anno)
    print(f"=== baseline (MDL sky only): max={mx0:.0f} median={md0:.0f} contrast={c0:.2f} ===")

    # add OUR OWN sun at stage root
    light_path = "/World/solar_twin_sun"
    sun = UsdLux.DistantLight.Define(stage, Sdf.Path(light_path))
    sun.CreateIntensityAttr(80000.0)
    sun.CreateAngleAttr(0.53)  # real solar disc angular size
    xf = UsdGeom.Xformable(sun)
    xf.ClearXformOpOrder()
    # summer noon ~75 deg elevation: tilt the light steeply downward.
    # DistantLight emits along -Z; rotate -15 deg from straight-down so shadows show.
    if up == "Y":
        xf.AddRotateXOp().Set(-105.0)   # point mostly downward (-Y), slight tilt
    else:  # Z up
        xf.AddRotateXOp().Set(-15.0)    # near-straight-down with slight tilt
    for _ in range(5):
        sim.update()

    mx1, md1, c1 = stats(anno)
    print(f"=== with OUR DistantLight (80000): max={mx1:.0f} median={md1:.0f} contrast={c1:.2f} ===")
    print(f"    ratio vs baseline: max x{mx1/mx0:.1f}  median x{md1/md0:.1f}")
    print("\nINTERPRETATION:")
    print("  - contrast jumps to >3 and max rises a lot  -> OUR light works headless;")
    print("    production pivots to driving our own sun (direction from pvlib).")
    print("  - still flat (~1.1)  -> render isn't using added lights either; report,")
    print("    we then try forcing render mode / a DomeLight / a different light type.")


try:
    main()
finally:
    sim.close()
