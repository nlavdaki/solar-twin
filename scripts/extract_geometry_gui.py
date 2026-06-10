r"""Per-pixel STATIC geometry extractor for the physical calibration model.

Run ONCE per location (GUI Isaac, Script Editor) at the SAME ROOF_PX used for the
lux sweep. Extracts the geometry the physically-structured model needs:

  - surface NORMAL at the pixel  -> tilt_deg, azimuth_deg   (fixes the H tilted-facet case)
  - SKY-VIEW FACTOR (SVF)        -> diffuse availability     (fixes the J occlusion case)
  - HORIZON profile (36 x 10deg) -> per-azimuth max obstruction elevation (shadow flag)

Output: geometry_Location_<X>.json, consumed by solar_twin.physical_model.SiteGeometry.
This is NOT path-traced and is cheap (a normal render + hemisphere ray queries).

PROBE-STYLE (like probe_illuminance_aov.py): conventions vary per build, so this
PRINTS what it found and writes a best-effort json. Report the printed block back
so we can lock the normal-space / up-axis / north-orientation conventions, exactly
as we did for the PtIlluminance token.

Usage: open Location_<X>.usd in full Isaac, RTX Interactive, paste into Script
Editor, set CONFIG below, Run. (async; uses step_async like the sweep.)
"""
import asyncio
import json
import math

import numpy as np

# ----------------------------------------------------------------- CONFIG (edit)
LOCATION_ID = "Location_Thissio"        # -> geometry_Location_Thissio.json
ROOF_PX = (838, 402)                     # SAME pixel as the lux sweep for this scene
OUT_DIR = r"C:\Users\Nikos\Documents\Vz Studio\data\geometry"
SVF_RAYS = 512                           # hemisphere samples for sky-view factor
RAY_MAX_M = 500.0                        # max obstruction distance (metres)
N_AZ_BINS = 36                           # horizon resolution (10 deg per bin)
# -----------------------------------------------------------------------------


def _tilt_azimuth_from_normal(n, up_axis):
    """normal (stage coords) -> (tilt_deg from horizontal, azimuth_deg N=0 cw).

    azimuth is raw stage azimuth; reconcile with /Environment north_orientation
    (printed below) when locking conventions.
    """
    n = np.asarray(n, float)
    if np.linalg.norm(n) < 1e-6:
        return float("nan"), float("nan")
    n = n / np.linalg.norm(n)
    if up_axis == "Z":
        up = np.array([0, 0, 1.0]); e = np.array([1.0, 0, 0]); nth = np.array([0, 1.0, 0])
    else:  # Y-up (Omniverse default)
        up = np.array([0, 1.0, 0]); e = np.array([1.0, 0, 0]); nth = np.array([0, 0, 1.0])
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, abs(float(np.dot(n, up)))))))
    horiz = n - np.dot(n, up) * up
    if np.linalg.norm(horiz) < 1e-6:
        return tilt, 0.0
    horiz /= np.linalg.norm(horiz)
    az = math.degrees(math.atan2(float(np.dot(horiz, e)), float(np.dot(horiz, nth)))) % 360.0
    return tilt, az


async def run():
    import omni.replicator.core as rep
    from omni.kit.viewport.utility import get_active_viewport
    from pxr import UsdGeom
    import omni.usd

    stage = omni.usd.get_context().get_stage()
    up_axis = UsdGeom.GetStageUpAxis(stage)
    vp = get_active_viewport()
    rp = vp.render_product_path
    W, H = vp.resolution
    px, py = ROOF_PX
    print(f"[geom] stage up-axis={up_axis}  viewport={W}x{H}  ROOF_PX={ROOF_PX}")

    # north orientation (for azimuth reconciliation)
    north_ori = None
    for p in ("/Environment", "/World/Environment"):
        pr = stage.GetPrimAtPath(p)
        if pr and pr.IsValid():
            a = pr.GetAttribute("location:north_orientation")
            if a and a.IsValid():
                north_ori = float(a.Get())
                print(f"[geom] {p}.north_orientation = {north_ori}")

    # ---- surface normal + world position via standard annotators ----
    normal = wpos = None
    for tok in ("normals", "normal"):
        try:
            ann = rep.AnnotatorRegistry.get_annotator(tok)
            ann.attach([rp])
            await rep.orchestrator.step_async(rt_subframes=8)
            d = ann.get_data()
            arr = np.asarray(d)
            if arr.ndim == 3 and arr.shape[0] >= H and arr.shape[1] >= W:
                normal = arr[py, px, :3].astype(float)
                print(f"[geom] normal AOV '{tok}' @pixel = {normal}")
            ann.detach()
            if normal is not None:
                break
        except Exception as e:  # noqa: BLE001
            print(f"[geom] normal token '{tok}' failed: {type(e).__name__}: {e}")

    for tok in ("pointcloud_position", "position", "worldPosition"):
        try:
            ann = rep.AnnotatorRegistry.get_annotator(tok)
            ann.attach([rp]); await rep.orchestrator.step_async(rt_subframes=8)
            arr = np.asarray(ann.get_data()); ann.detach()
            if arr.ndim == 3 and arr.shape[0] >= H and arr.shape[1] >= W:
                wpos = arr[py, px, :3].astype(float)
                print(f"[geom] world-position AOV '{tok}' @pixel = {wpos}")
                break
        except Exception as e:  # noqa: BLE001
            print(f"[geom] position token '{tok}' n/a: {type(e).__name__}")

    valid_normal = normal is not None and float(np.linalg.norm(np.asarray(normal, float))) > 1e-6
    if valid_normal:
        tilt, az = _tilt_azimuth_from_normal(normal, up_axis)
        print(f"[geom] -> tilt={tilt:.1f} deg  azimuth(raw)={az:.1f} deg")
    else:
        tilt, az = None, None
        print("[geom] -> normal capture FAILED (all-zero / no AOV) -> tilt/azimuth=null; "
              "site treated as horizontal-open (geometry is OPTIONAL). Retry or nudge ROOF_PX "
              "by a few px if you need the tilt documented.")

    # ---- SVF + horizon via physx raycast (best effort; needs colliders) ----
    svf, horizon = 1.0, [0.0] * N_AZ_BINS
    try:
        from omni.physx import get_physx_scene_query_interface
        sq = get_physx_scene_query_interface()
        if wpos is None:
            raise RuntimeError("no world position AOV -> cannot place ray origin")
        up = (np.array([0, 0, 1.0]) if up_axis == "Z" else np.array([0, 1.0, 0]))
        origin = (np.asarray(wpos, float) + 0.5 * up).tolist()
        hit_count = 0
        hor = np.zeros(N_AZ_BINS)
        rng = np.random.default_rng(0)
        for _ in range(SVF_RAYS):
            u, v = rng.random(), rng.random()           # cosine-weighted upper hemisphere
            r = math.sqrt(u); theta = 2 * math.pi * v
            local = np.array([r * math.cos(theta), r * math.sin(theta), math.sqrt(1 - u)])
            d = local if up_axis == "Z" else np.array([local[0], local[2], local[1]])
            hit = sq.raycast_closest(origin, d.tolist(), RAY_MAX_M)
            if hit and hit.get("hit"):
                hit_count += 1
                elev = math.degrees(math.asin(max(0.0, min(1.0, float(d[2 if up_axis == 'Z' else 1])))))
                azr = math.degrees(math.atan2(d[0], d[1 if up_axis == 'Z' else 2])) % 360.0
                b = min(int(azr / (360.0 / N_AZ_BINS)), N_AZ_BINS - 1)
                hor[b] = max(hor[b], elev)
        svf = 1.0 - hit_count / SVF_RAYS
        horizon = hor.tolist()
        print(f"[geom] physx raycast OK: SVF={svf:.3f}  obstructed {hit_count}/{SVF_RAYS} rays")
    except Exception as e:  # noqa: BLE001
        print(f"[geom] SVF/horizon SKIPPED ({type(e).__name__}: {e}) -> SVF=1.0, horizon=0. "
              "If this site is occluded (e.g. J), report back so we wire the ray route.")

    out = dict(location_id=LOCATION_ID, roof_px=list(ROOF_PX), up_axis=up_axis,
               extraction_ok=bool(valid_normal),
               tilt_deg=(round(float(tilt), 2) if tilt is not None else None),
               azimuth_deg=(round(float(az), 2) if az is not None else None),
               azimuth_convention="raw_stage_UNVERIFIED",  # reconcile via normal_raw + north_orientation
               normal_raw=[round(float(x), 5) for x in (np.asarray(normal, float) if valid_normal else [0.0, 0.0, 0.0])],
               north_orientation=north_ori,
               svf=round(float(svf), 4), horizon_deg=[round(float(x), 1) for x in horizon],
               albedo=0.2, source="extract_geometry_gui.py")
    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"geometry_{LOCATION_ID}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"[geom] WROTE {path}")
    print("[geom] >>> report the [geom] lines above so we lock normal-space / up-axis /"
          " north conventions (probe-style, like PtIlluminance).")


asyncio.ensure_future(run())
