"""Live check: compare the viewport 'Illuminance value' against what our package
extracts for the SAME pixel, with proper path-tracing convergence.

Run in GUI mode so you can SEE the values side by side:
    python.bat <pkg>\scripts\run_probe_standalone.py --gui ^
        --stage "C:/dev/solar-digital-twin-migration/01_old_composer_export/Location_A.usd" ^
        --then live_illuminance_check

...or simplest, run this file via the dedicated launcher below (it boots the app,
opens the stage, renders to convergence, and prints the package value). Then in the
Isaac viewport: Render Settings > Interactive (Path Tracing) > Common > View >
Illuminance, click the SAME pixel, and compare to the printed value.

WHY CONVERGENCE MATTERS: path tracing accumulates samples. The on-screen indicator
'PathTracing: x/maxx spp ... sec' must reach x == maxx (completed) before the value
is trustworthy. We force this with rep.orchestrator.step(rt_subframes=N): it renders
N subframes before reading, so the captured lux matches the settled viewport number.
This script also prints the value at increasing subframe counts so you can SEE it
converge and pick a stable floor.
"""
from __future__ import annotations

# Edit these to taste, or pass via the launcher's --px / --camera if you extend it.
PIXEL_XY = (256, 256)          # the pixel to compare (viewport: click the same spot)
RESOLUTION = (512, 512)        # keep modest so the click maps obviously
CAMERA_PATH = None             # None -> make a default camera; or "/World/your_cam"
CONVERGE_LADDER = [1, 8, 16, 32, 64, 128, 256]   # show value at each, watch it settle
TOKEN = "PtIlluminance"


def main():
    import numpy as np
    import carb
    import omni.replicator.core as rep

    settings = carb.settings.get_settings()
    rep.settings.set_render_pathtraced(samples_per_pixel=64)
    # absolute-measurement hygiene
    for k, v in {
        "/rtx/pathtracing/denoiser/enabled": False,
        "/rtx/post/tonemap/enabled": False,
        "/rtx/post/dlss/execMode": 0,
    }.items():
        try:
            settings.set(k, v)
        except Exception:  # noqa: BLE001
            pass

    cam = CAMERA_PATH or rep.create.camera(position=(300, 300, 300), look_at=(0, 0, 0))
    rp = rep.create.render_product(cam, RESOLUTION)

    rep.AnnotatorRegistry.register_annotator_from_aov(TOKEN)
    anno = rep.AnnotatorRegistry.get_annotator(TOKEN)
    anno.attach(rp)

    x, y = PIXEL_XY
    print(f"\n=== Live illuminance at pixel {PIXEL_XY} (res {RESOLUTION}) ===")
    print("Watch the value settle as path tracing converges (x/maxx -> completed):\n")
    print(f"{'rt_subframes':>12} | {'lux @ pixel':>14} | {'frame mean':>12} | {'frame max':>12}")
    print("-" * 60)

    prev = None
    for n in CONVERGE_LADDER:
        rep.orchestrator.step(rt_subframes=n)
        a = np.asarray(anno.get_data(), dtype=np.float64)
        img = a[..., 0] if a.ndim == 3 else a
        # small median patch to dodge single-pixel speckle
        patch = img[max(0, y - 1):y + 2, max(0, x - 1):x + 2]
        lux = float(np.nanmedian(patch))
        delta = "" if prev is None else f"  (Δ {lux - prev:+.1f})"
        print(f"{n:>12} | {lux:>14.1f} | {np.nanmean(img):>12.1f} | {np.nanmax(img):>12.1f}{delta}")
        prev = lux

    print("\nNow in the Isaac viewport:")
    print("  Render Settings > RTX Interactive (Path Tracing) > Common > View > Illuminance")
    print(f"  click pixel ~{PIXEL_XY} and read 'Illuminance value' — it should match the")
    print("  bottom (most-converged) row above within path-tracing noise.")
    print("\nAlso paste the per-channel report so we lock the right channel:")
    # channel report
    a = np.asarray(anno.get_data(), dtype=np.float64)
    if a.ndim == 3:
        for c in range(a.shape[-1]):
            ch = a[..., c]
            print(f"  ch{c}: min={np.nanmin(ch):.4g} max={np.nanmax(ch):.4g} mean={np.nanmean(ch):.4g}")


if __name__ == "__main__":
    main()
