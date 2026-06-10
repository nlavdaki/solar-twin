r"""Measure the path-tracing convergence floor — STANDALONE (fresh render per point).

WHY standalone, not the Script Editor: the live viewport pre-accumulates samples,
so it shows the same lux at every rt_subframes (already converged) and cannot
reveal the floor. The headless sweep renders each sun position COLD, so we must
measure how many subframes a fresh render needs to stabilize. This script forces
a fresh accumulation per rt_subframes value and reports where photopic lux settles.

The result (smallest rt_subframes whose lux is within tol of the most-converged
value) sets the render cost for all 25k-40k captures — so measure it carefully.

RUN (Windows, standalone — sync step is allowed here):
    C:\isaacsim\python.bat ^
      "C:\Users\Nikos\Documents\Vz Studio\USD_Extractor_Calibrator_Package\scripts\measure_convergence.py" ^
      --stage "C:/dev/solar-digital-twin-migration/01_old_composer_export/Location_A.usd" ^
      --camera /World/Camera --px 640 --py 360
"""
from __future__ import annotations

import argparse

p = argparse.ArgumentParser()
p.add_argument("--stage", required=True)
p.add_argument("--camera", default="/World/Camera")
p.add_argument("--px", type=int, default=640)
p.add_argument("--py", type=int, default=360)
p.add_argument("--res", type=int, nargs=2, default=[1280, 720])
p.add_argument("--ladder", type=int, nargs="+",
               default=[1, 2, 4, 8, 16, 32, 64, 128, 256, 512])
p.add_argument("--tol", type=float, default=0.01, help="relative tolerance for 'converged'")
args, _ = p.parse_known_args()

# 1) Boot standalone app FIRST (sync orchestrator.step is allowed in this workflow).
from isaacsim import SimulationApp  # noqa: E402

sim = SimulationApp({
    "headless": True,
    "rtx-transient.aov.enableRtxAovs": True,
    "rtx-transient.aov.enableRtxAovsSecondary": True,
})

import numpy as np  # noqa: E402
import carb  # noqa: E402
import omni.usd  # noqa: E402
import omni.replicator.core as rep  # noqa: E402

_PHOTOPIC = (0.2126, 0.7152, 0.0722)


def photopic(a):
    a = np.asarray(a, dtype=np.float64)
    if a.ndim == 2:
        return a
    return _PHOTOPIC[0] * a[..., 0] + _PHOTOPIC[1] * a[..., 1] + _PHOTOPIC[2] * a[..., 2]


def main():
    omni.usd.get_context().open_stage(args.stage)
    for _ in range(60):
        sim.update()

    rep.settings.set_render_pathtraced(samples_per_pixel=1)  # 1 spp/frame -> subframes drive accumulation
    s = carb.settings.get_settings()
    for k, v in {"/rtx/pathtracing/denoiser/enabled": False,
                 "/rtx/post/tonemap/enabled": False,
                 "/rtx/post/dlss/execMode": 0}.items():
        try:
            s.set(k, v)
        except Exception:  # noqa: BLE001
            pass

    rp = rep.create.render_product(args.camera, tuple(args.res))
    rep.AnnotatorRegistry.register_annotator_from_aov("PtIlluminance")
    anno = rep.AnnotatorRegistry.get_annotator("PtIlluminance")
    anno.attach(rp)

    x, y = args.px, args.py
    print(f"\n=== convergence @ pixel ({x},{y}), fresh render each row ===")
    print(f"{'rt_subframes':>12} | {'photopic lux':>13} | {'Δ vs prev':>10} | {'sec':>6}")
    print("-" * 52)

    import time
    results = []
    prev = None
    for n in args.ladder:
        # Force a COLD render: detach+reattach resets accumulation for a fair test.
        anno.detach()
        anno.attach(rp)
        t0 = time.time()
        rep.orchestrator.step(rt_subframes=n)
        a = np.asarray(anno.get_data(), dtype=np.float64)
        img = photopic(a)
        H, W = img.shape[:2]
        xi, yi = min(x, W - 1), min(y, H - 1)
        lux = float(np.nanmedian(img[max(0, yi - 1):yi + 2, max(0, xi - 1):xi + 2]))
        dt = time.time() - t0
        d = "" if prev is None else f"{(lux - prev) / prev * 100:+.2f}%"
        print(f"{n:>12} | {lux:>13.1f} | {d:>10} | {dt:>6.1f}")
        results.append((n, lux, dt))
        prev = lux

    # floor = smallest n within tol of the most-converged (last) value
    final = results[-1][1]
    floor = next((n for n, lux, _ in results if abs(lux - final) / final <= args.tol), results[-1][0])
    print(f"\nMost-converged lux ≈ {final:.1f}")
    print(f"CONVERGENCE FLOOR (within {args.tol*100:.0f}%): rt_subframes = {floor}")
    print("Use this (or a small safety margin above it) for the sweep's rt_subframes.")
    print("Record it in config/sweep.yaml -> render.samples_per_pixel / rt_subframes.")


try:
    main()
finally:
    sim.close()
