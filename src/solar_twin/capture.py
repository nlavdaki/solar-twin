"""Omniverse RTX absolute-illuminance (lux) capture.

REQUIRES Isaac Sim / USD Composer + RTX GPU. This module's functions only run
inside a live Isaac Sim app (launched via scripts/run_probe_standalone.py-style
boot, or USD Composer). They are import-safe without Omniverse (the omni imports
are deferred into the functions), so the rest of the package and its tests do not
need a GPU.

CONFIRMED on the real machine (Step A / probe v3, 2026-05-31):
  - The viewport "Illuminance value" (Interactive PT > Common > View > Illuminance)
    is render var token 'PtIlluminance'.
  - Captured via register_annotator_from_aov('PtIlluminance') then get_annotator(...).
  - get_data() -> np.float32 array, shape (H, W, 4), values in ABSOLUTE LUX
    (probe read min=1, max=2927, mean=1136 on a test frame).
  - It is NOT in the Replicator AnnotatorRegistry by default; the from_aov call
    registers it. PtAovIlluminance / Illuminance tokens returned empty on this build.

Measurement rules: Path Tracing mode; denoiser OFF for absolute values; sample to
an SPP convergence floor; values are float32 (no float16 precision concern).
"""
from __future__ import annotations

ILLUMINANCE_AOV_TOKEN: str = "PtIlluminance"   # resolved by Step A
RADIANCE_ANNOTATOR: str = "HdrColor"           # linear-radiance fallback only

# carb settings for a clean absolute-lux measurement.
_MEASUREMENT_SETTINGS = {
    "/rtx/rendermode": "PathTracing",
    "/rtx/pathtracing/denoiser/enabled": False,   # denoiser biases absolute AOV values
    "/rtx/post/dlss/execMode": 0,
    "/rtx/post/tonemap/enabled": False,
}


def _settings():
    import carb
    return carb.settings.get_settings()


def _apply(settings, kv):
    for k, v in kv.items():
        try:
            settings.set(k, v)
        except Exception:  # noqa: BLE001
            pass


def open_stage(usd_path: str) -> None:
    """Open a USD stage and let it settle. Call inside a live app."""
    import omni.usd
    omni.usd.get_context().open_stage(usd_path)


def configure_measurement(samples_per_pixel: int = 256) -> None:
    """Path Tracing, denoiser off, tonemap off — for absolute lux."""
    import omni.replicator.core as rep
    rep.settings.set_render_pathtraced(samples_per_pixel=samples_per_pixel)
    _apply(_settings(), _MEASUREMENT_SETTINGS)


def make_render_product(camera_path: str, resolution=(1024, 1024)):
    """Create a render product for an existing camera prim (or a Replicator camera)."""
    import omni.replicator.core as rep
    return rep.create.render_product(camera_path, tuple(resolution))


def attach_illuminance(render_product, token: str = ILLUMINANCE_AOV_TOKEN):
    """Register + attach the illuminance render-var annotator. Returns the annotator."""
    import omni.replicator.core as rep
    # Idempotent: register the AOV-backed annotator, then fetch + attach it.
    try:
        rep.AnnotatorRegistry.register_annotator_from_aov(token)
    except Exception:  # noqa: BLE001
        pass  # already registered on a prior call
    anno = rep.AnnotatorRegistry.get_annotator(token)
    anno.attach(render_product)
    return anno


# Rec.709 / CIE photopic luminance weights — the same weighting a lux meter applies.
_PHOTOPIC = (0.2126, 0.7152, 0.0722)


def to_photopic_lux(arr):
    """Combine PtIlluminance's RGB illuminance channels into scalar photopic lux.

    CONFIRMED on the real machine (2026-05-31): PtIlluminance is (H, W, 4) float32
    where ch0/ch1/ch2 are R/G/B illuminance (DISTINCT — e.g. means 1156/1383/2002
    for a daylight sky) and ch3 is alpha (=1). A lux meter measures the photopic
    (luminance-weighted) sum, so lux = 0.2126*R + 0.7152*G + 0.0722*B. Using a
    single channel (e.g. ch0=red) would be physically wrong. GPU-independent.
    """
    import numpy as np
    a = np.asarray(arr, dtype=np.float64)
    if a.ndim == 2:
        return a  # already scalar
    wr, wg, wb = _PHOTOPIC
    return wr * a[..., 0] + wg * a[..., 1] + wb * a[..., 2]


def capture_lux(annotator, rt_subframes: int = 64, step: bool = True, channel=None):
    """Render to convergence, then return a 2-D (H, W) array of absolute photopic lux.

    CONVERGENCE (critical for path tracing): a single step returns a noisy,
    half-accumulated frame. `step(rt_subframes=N)` renders N subframes BEFORE
    collecting data, so the value is converged. In the HEADLESS SWEEP each sun
    position is a fresh render (no pre-accumulation), so N must exceed the SPP at
    which the reference probe stabilizes — measure that floor standalone (the live
    viewport pre-converges and will mislead you). Default 64.

    By default returns PHOTOPIC lux (0.2126R+0.7152G+0.0722B) — see to_photopic_lux.
    Pass channel=<int> to extract a single raw channel instead (diagnostics only).
    """
    import numpy as np
    import omni.replicator.core as rep
    if step:
        rep.orchestrator.step(rt_subframes=rt_subframes)
    arr = np.asarray(annotator.get_data(), dtype=np.float64)
    if channel is not None and arr.ndim == 3:
        return arr[..., channel]
    return to_photopic_lux(arr)


def channel_report(annotator, step: bool = True) -> str:
    """One-time diagnostic: per-channel min/max/mean, to confirm which channel is lux."""
    import numpy as np
    import omni.replicator.core as rep
    if step:
        rep.orchestrator.step()
    a = np.asarray(annotator.get_data(), dtype=np.float64)
    if a.ndim != 3:
        return f"shape={a.shape} (not HxWxC); min={np.nanmin(a):.3g} max={np.nanmax(a):.3g}"
    lines = [f"shape={a.shape} dtype=float32"]
    for c in range(a.shape[-1]):
        ch = a[..., c]
        lines.append(f"  ch{c}: min={np.nanmin(ch):.4g} max={np.nanmax(ch):.4g} "
                     f"mean={np.nanmean(ch):.4g}")
    return "\n".join(lines)


def sample_points_lux(lux_img, points_px, kernel: int = 2):
    """Sample lux at integer pixel coords {name: (x, y)} with a small median patch
    (kills path-tracing speckle). Returns {name: lux}. GPU-independent helper.
    """
    import numpy as np
    out = {}
    H, W = lux_img.shape[:2]
    for name, (x, y) in points_px.items():
        x0, x1 = max(0, x - kernel), min(W, x + kernel + 1)
        y0, y1 = max(0, y - kernel), min(H, y + kernel + 1)
        patch = lux_img[y0:y1, x0:x1]
        out[name] = float(np.nanmedian(patch))
    return out
