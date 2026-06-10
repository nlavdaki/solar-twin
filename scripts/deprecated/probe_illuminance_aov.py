"""Step A (v3) — capture the ABSOLUTE-LUX illuminance render var, headless.

CONFIRMED by the user's viewport: under Interactive Path Tracing > Common > View
> Illuminance, clicking a pixel shows /rtx/pathtracing/illuminanceVal (e.g.
~24956 lux). So the renderer DOES compute absolute lux. It is a *render variable*
(AOV), captured via omni.syntheticdata / register_annotator_from_aov — NOT a
member of the Replicator AnnotatorRegistry (that's why probe v1 missed it).

v3 is self-correcting: it introspects the real API signatures and enumerates the
renderer's render-vars on YOUR build, then tries to bind+read the illuminance one.

RUN (Windows):
    python.bat <pkg>\scripts\run_probe_standalone.py --stage "...\Location_A.usd"
"""
from __future__ import annotations

import inspect

# Candidate render-var / AOV token names for absolute illuminance (lux).
ILLUM_TOKENS = [
    "PtAovIlluminance", "Illuminance", "PtIlluminance",
    "IlluminanceAOV", "illuminance", "PtAovIlluminanceVal",
]

# carb settings that enable the PT illuminance AOV + keep values raw.
_ENABLE_AOV = {
    "/rtx/pathtracing/aov/enabled": True,
    "/rtx/aov/enabled": True,
    "rtx-transient.aov.enableRtxAovs": True,
    "rtx-transient.aov.enableRtxAovsSecondary": True,
    # the View illuminance toggle the user used, expressed as settings (best-effort):
    "/rtx/pathtracing/illuminanceEnabled": True,
    "/rtx/post/aov/enabled": True,
}


def _set(settings, kv):
    for k, v in kv.items():
        try:
            settings.set(k, v)
        except Exception:  # noqa: BLE001
            pass


def _summ(name, data):
    import numpy as np
    a = np.asarray(data, dtype=np.float64)
    fin = a[np.isfinite(a)]
    if not fin.size:
        print(f"   -> {name}: empty/all-nan  (shape={np.asarray(data).shape})")
        return False
    lo, hi, mean = float(fin.min()), float(fin.max()), float(fin.mean())
    verdict = "ABSOLUTE LUX (max in thousands)" if hi > 2000 else "not lux-scale"
    print(f"   -> {name}: shape={a.shape} dtype={np.asarray(data).dtype} "
          f"min={lo:.4g} max={hi:.4g} mean={mean:.4g}  [{verdict}]")
    return hi > 2000


def _introspect(rep):
    print("========== 0) API introspection (version-proof) ==========")
    reg = rep.AnnotatorRegistry
    for meth in ["register_annotator_from_aov", "get_annotator", "get_aov"]:
        fn = getattr(reg, meth, None)
        if fn is None:
            print(f"   {meth}: NOT PRESENT")
            continue
        try:
            print(f"   {meth}{inspect.signature(fn)}")
        except (TypeError, ValueError):
            print(f"   {meth}: present (signature unavailable)")


def _enumerate_rendervars():
    """Best-effort: list render vars the renderer exposes on this build."""
    print("========== 1) enumerate available render vars ==========")
    found = []
    try:
        import omni.syntheticdata as sd
        sdi = sd.SyntheticData.Get()
        if sdi is not None:
            for attr in ("get_registered_visualization_template_names",
                         "get_registered_annotators", "get_rendervars"):
                fn = getattr(sdi, attr, None)
                if fn:
                    try:
                        names = list(fn())
                        print(f"   via {attr}: {len(names)} entries")
                        found += names
                    except Exception:  # noqa: BLE001
                        pass
    except Exception as e:  # noqa: BLE001
        print(f"   omni.syntheticdata enumeration unavailable: {type(e).__name__}: {e}")
    hits = [n for n in found if any(k in str(n).lower() for k in ("illum", "lux", "lumin"))]
    print(f"   render vars matching illum/lux/lumin: {hits}")
    return found, hits


def main():
    import carb
    import omni.replicator.core as rep

    settings = carb.settings.get_settings()
    rep.settings.set_render_pathtraced(samples_per_pixel=128)
    _set(settings, _ENABLE_AOV)

    cam = rep.create.camera(position=(300, 300, 300), look_at=(0, 0, 0))
    rp = rep.create.render_product(cam, (512, 512))

    _introspect(rep)
    _, hits = _enumerate_rendervars()

    print("========== 2) try to bind + read the illuminance render var ==========")
    tokens = hits + [t for t in ILLUM_TOKENS if t not in hits]
    win = None
    for tok in tokens:
        tok = str(tok)
        # try register_annotator_from_aov with POSITIONAL arg (v1 failed on aov_name kwarg)
        try:
            rep.AnnotatorRegistry.register_annotator_from_aov(tok)
            anno = rep.AnnotatorRegistry.get_annotator(tok)
            anno.attach(rp)
            rep.orchestrator.step()
            if _summ(f"from_aov({tok})", anno.get_data()):
                win = tok
                break
            anno.detach()
        except Exception as e:  # noqa: BLE001
            print(f"[no] from_aov({tok!r}): {type(e).__name__}: {e}")
        # also try get_annotator directly (some builds expose it straight)
        try:
            anno = rep.AnnotatorRegistry.get_annotator(tok)
            anno.attach(rp)
            rep.orchestrator.step()
            if _summ(f"get_annotator({tok})", anno.get_data()):
                win = tok
                break
            anno.detach()
        except Exception:  # noqa: BLE001
            pass

    print("\n========== RESULT / REPORT BACK ==========")
    if win:
        print(f"WINNER render-var token: {win!r}")
        print("Record it in config/sites.example.yaml -> illuminance_aov_id, and paste")
        print("the matching shape/dtype/min/max/mean line above.")
    else:
        print("No token bound to absolute lux yet. Please paste:")
        print("  - the section-0 signature of register_annotator_from_aov")
        print("  - the section-1 'render vars matching illum/lux/lumin' list")
        print("That tells us the exact token + call form for your build, and I'll finalize it.")


if __name__ == "__main__":
    main()
