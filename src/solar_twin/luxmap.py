r"""Publication-quality false-colour illuminance map from a numeric lux buffer.

GPU-independent (matplotlib). Renders a QUANTITATIVE map (true lux colorbar) from
the captured PtIlluminance array — NOT a colorized viewport screenshot, whose
range-normalized colours are not quantitative. This is the deliberate advantage
of capturing the numeric AOV: the colorbar is in physical lux.

Typical use:
    from solar_twin.luxmap import render_lux_map
    render_lux_map("lux_map_Location_A.npy", "F7_lux_map.png", title="Location A")

`render_lux_map_gui.py` (Isaac) only needs to write the .npy; call this in the uv
env to make the figure. Default: inferno colormap, 2-98th-percentile clip (so
sun/shadow contrast is strongest), 300 dpi, PNG + PDF.
"""
from __future__ import annotations

import os


def load_lux_map(src):
    """Accept a 2D numpy array or a path to a .npy and return a float 2D array."""
    import numpy as np
    a = np.load(src) if isinstance(src, str) else np.asarray(src)
    a = np.asarray(a, dtype=float)
    if a.ndim != 2:
        raise ValueError(f"expected a 2D lux map, got shape {a.shape}")
    return a


def render_lux_map(src, out_path, cmap="inferno", clip_percentile=(2.0, 98.0),
                   vmin=None, vmax=None, title=None, colorbar_label="illuminance (lux)",
                   dpi=300, show_axes=False, also_pdf=True):
    """Render a false-colour lux map. Returns the (vmin, vmax) actually used.

    src             : 2D lux array OR path to a .npy (from render_lux_map_gui.py)
    cmap            : matplotlib colormap ('inferno' default; 'turbo'/'viridis'/'jet' ok)
    clip_percentile : (lo, hi) percentiles for the colour range; ignored if vmin/vmax given
    vmin, vmax      : explicit colour limits (override the percentile clip)
    title           : optional title; show_axes keeps the pixel axes (default off)
    also_pdf        : also write a vector .pdf alongside the .png
    """
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    a = load_lux_map(src)
    if vmin is None or vmax is None:
        lo, hi = np.percentile(a, clip_percentile[0]), np.percentile(a, clip_percentile[1])
        vmin = lo if vmin is None else vmin
        vmax = hi if vmax is None else vmax
    if vmax <= vmin:
        vmin, vmax = float(a.min()), float(a.max() or 1.0)

    h, w = a.shape
    fig, ax = plt.subplots(figsize=(9, 9 * h / w))
    im = ax.imshow(a, cmap=cmap, vmin=vmin, vmax=vmax, origin="upper")
    if not show_axes:
        ax.set_axis_off()
    else:
        ax.set_xlabel("pixel x"); ax.set_ylabel("pixel y")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cb.set_label(colorbar_label)
    if title:
        ax.set_title(title)
    fig.tight_layout()
    base, _ = os.path.splitext(out_path)
    fig.savefig(base + ".png", dpi=dpi, bbox_inches="tight")
    if also_pdf:
        fig.savefig(base + ".pdf", bbox_inches="tight")
    plt.close(fig)
    return float(vmin), float(vmax)
