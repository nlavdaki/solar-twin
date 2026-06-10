# =====================================================================
# PICK A ROOF PIXEL (async, Isaac Sim Script Editor).
#
# Problem: you can choose a roof point visually but need its (x, y) PIXEL for
# sprint0_sweep.py's ROOF_PX. Three ways, easiest first — the script tries them
# and prints a ready-to-paste `ROOF_PX = (x, y)` line.
#
# METHOD 1 (simplest, no script): in the viewport, Render Settings > RTX
#   Interactive (Path Tracing) > Common > View > Illuminance, then CLICK your
#   roof. The readout shows e.g. "24872 lux at (506, 418)" — those numbers ARE
#   the pixel. Use ROOF_PX = (506, 418). Done.
#
# METHOD 2 (this script, selection-based — RECOMMENDED): in the Stage/viewport,
#   SELECT the roof prim (or a small prim you place on the roof), then run this.
#   It reads the prim's world position and PROJECTS it to a viewport pixel, so
#   you never read coordinates by hand. It introspects the viewport API so it
#   works across Kit versions.
#
# METHOD 3 (fallback): if projection isn't available, it prints the selected
#   prim's world position so we can compute the pixel offline.
#
# Setup: full Isaac Sim > Open Location_A.usd > select the roof prim >
#   Window>Script Editor > paste > Run.
# =====================================================================

import omni.usd
from pxr import UsdGeom, Gf
from omni.kit.viewport.utility import get_active_viewport


def selected_world_point():
    ctx = omni.usd.get_context()
    paths = ctx.get_selection().get_selected_prim_paths()
    if not paths:
        return None, None
    stage = ctx.get_stage()
    prim = stage.GetPrimAtPath(paths[0])
    # world-space pivot of the prim's bounding box (robust for meshes/xforms)
    bbox_cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    rng = bbox_cache.ComputeWorldBound(prim).ComputeAlignedRange()
    center = rng.GetMidpoint()
    return paths[0], Gf.Vec3d(center[0], center[1], center[2])


def world_to_pixel(vp, world_pt):
    """Try several Kit APIs to project a world point to (x, y) pixel."""
    res = tuple(vp.resolution)
    # A) viewport_api.world_to_ndc (Matrix) -> NDC in [-1,1]; map to pixels
    for attr in ("world_to_ndc", "compute_world_to_ndc"):
        m = getattr(vp, attr, None)
        if m is not None:
            try:
                ndc = m() if callable(m) and attr == "world_to_ndc" else None
            except Exception:
                ndc = None
            # world_to_ndc is usually a matrix property, not a callable; handle both
    # B) the documented helper: viewport_api.world_to_ndc is a Gf.Matrix4d property
    try:
        mtx = vp.world_to_ndc
        p = mtx.Transform(world_pt)  # Gf.Vec3d in NDC space [-1,1]
        x = (p[0] * 0.5 + 0.5) * res[0]
        y = (1.0 - (p[1] * 0.5 + 0.5)) * res[1]  # flip Y for image coords
        return int(round(x)), int(round(y)), "world_to_ndc matrix"
    except Exception as e:  # noqa: BLE001
        return None, None, f"world_to_ndc unavailable: {type(e).__name__}"


def main():
    vp = get_active_viewport()
    res = tuple(vp.resolution)
    print(f"[pick] active camera {vp.camera_path.pathString}  resolution {res}")

    path, wpt = selected_world_point()
    if wpt is None:
        print("\nNo prim selected. Either:")
        print("  - METHOD 1: click the roof in View>Illuminance and read '(x, y)' from the readout; or")
        print("  - select the roof prim in the Stage tree and re-run this.")
        return

    print(f"[pick] selected prim: {path}")
    print(f"[pick] world position (bbox center): {tuple(round(c,1) for c in wpt)}")
    x, y, how = world_to_pixel(vp, wpt)
    if x is not None and 0 <= x < res[0] and 0 <= y < res[1]:
        print(f"\n  ROOF_PX = ({x}, {y})    # via {how}")
        print("  ^ paste this into sprint0_sweep.py")
    else:
        print(f"\n[pick] projection not available on this build ({how}).")
        print("Fallback: use METHOD 1 (View>Illuminance click shows the pixel), or send me")
        print("the world position above + camera path and I'll compute the pixel offline.")


main()
