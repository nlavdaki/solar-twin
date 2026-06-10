r"""Capture a full-frame false-colour ILLUMINANCE MAP for the C&G hero figure.

Run in full Isaac (GUI Script Editor) with Location_<X>.usd open, RTX Interactive
Path Tracing, and the viewport framed how you want the figure (top-down or
oblique). It captures the whole-frame PtIlluminance (absolute photopic lux),
saves the raw array as .npy (always) and a quick false-colour PNG if matplotlib
is present. Render the publication PNG from the .npy with make_paper_figures-style
styling in your uv env if Isaac lacks matplotlib.

Output: lux_map_<LOCATION_ID>.npy  (+ _preview.png if matplotlib available)
"""
import asyncio
import os

import numpy as np

# ----------------------------------------------------------------- CONFIG (edit)
LOCATION_ID = "Location_A"
OUT_DIR = r"C:\Users\Nikos\Documents\Vz Studio\data\results\figures"
RT_SUBFRAMES = 96          # high quality for a hero figure (slow but one frame)
# -----------------------------------------------------------------------------

_LUM = np.array([0.2126, 0.7152, 0.0722])  # photopic RGB -> lux (matches capture.py)


async def run():
    import omni.replicator.core as rep
    from omni.kit.viewport.utility import get_active_viewport

    vp = get_active_viewport()
    rp = vp.render_product_path
    W, H = vp.resolution
    print(f"[luxmap] viewport {W}x{H}  rt_subframes={RT_SUBFRAMES}")

    # PtIlluminance is a RENDER AOV, not a default annotator -> register it first
    # (same pattern as capture.py / production_sweep_gui.py).
    try:
        rep.AnnotatorRegistry.register_annotator_from_aov("PtIlluminance")
    except Exception as e:  # noqa: BLE001  (harmless if already registered on re-run)
        print(f"[luxmap] register PtIlluminance: {type(e).__name__} (ok if already registered)")
    ann = rep.AnnotatorRegistry.get_annotator("PtIlluminance")
    ann.attach([rp])
    await rep.orchestrator.step_async(rt_subframes=RT_SUBFRAMES)
    data = np.asarray(ann.get_data())
    ann.detach()
    if data.ndim != 3 or data.shape[2] < 3:
        print(f"[luxmap] unexpected AOV shape {data.shape}; aborting"); return
    lux = (data[:, :, :3].astype(np.float64) * _LUM).sum(axis=2)  # photopic lux (H,W)
    print(f"[luxmap] lux min={lux.min():.0f} max={lux.max():.0f} mean={lux.mean():.0f}")

    os.makedirs(OUT_DIR, exist_ok=True)
    npy = os.path.join(OUT_DIR, f"lux_map_{LOCATION_ID}.npy")
    np.save(npy, lux.astype(np.float32))
    print(f"[luxmap] WROTE {npy}  (render the figure from this in uv if needed)")

    try:  # quick preview if Isaac's python has matplotlib
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 8 * H / W))
        im = ax.imshow(lux, cmap="turbo", origin="upper")
        ax.set_axis_off()
        cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
        cb.set_label("illuminance (lux)")
        ax.set_title(f"RTX path-traced illuminance — {LOCATION_ID}")
        png = os.path.join(OUT_DIR, f"lux_map_{LOCATION_ID}_preview.png")
        fig.savefig(png, dpi=200, bbox_inches="tight"); plt.close(fig)
        print(f"[luxmap] preview {png}")
    except Exception as e:  # noqa: BLE001
        print(f"[luxmap] no matplotlib in Isaac ({type(e).__name__}); render from the .npy in uv:")
        print("         python -c \"import numpy as np,matplotlib.pyplot as plt;"
              "a=np.load('lux_map_%s.npy');plt.imshow(a,cmap='turbo');"
              "plt.colorbar(label='lux');plt.axis('off');plt.savefig('luxmap.png',dpi=300)\"" % LOCATION_ID)


asyncio.ensure_future(run())
