# =====================================================================
# SCENE COMPLEXITY METRICS (Isaac Sim GUI Script Editor; run once per scene).
#
# Supports the paper's scalability claim: records prim count, approx Cesium tile
# count, world bounding box, and the roof pixel, for the CURRENTLY OPEN scene.
# APPENDS one row per run to data/results/scene_complexity.csv.
#
# SETUP: open Location_{X}.usd in the GUI, set LOCATION + ROOF_PX below, paste, Run.
# Re-run for each location (it appends; safe to re-run, see de-dup note).
#
# HARDWARE: RTX 4070 12GB | i5-12600K | 32GB | IsaacSim 5.1.0-rc19 Kit107.3.3
# =====================================================================

# ---- CONFIG (set per scene before running) ----
LOCATION = "Location_A"
ROOF_PX  = (506, 418)
OUT_CSV  = r"C:/Users/Nikos/Documents/Vz Studio/data/results/scene_complexity.csv"
HW = "RTX 4070 12GB | i5-12600K | 32GB | IsaacSim 5.1.0-rc19 Kit107.3.3"
# -----------------------------------------------

import csv
import os

import omni.usd
from pxr import Usd, UsdGeom


def main():
    stage = omni.usd.get_context().get_stage()
    prims = list(stage.Traverse())
    prim_count = len(prims)

    # approx Cesium tile count: prims whose type or path looks like a Cesium tile/tileset
    tile_count = 0
    for p in prims:
        t = p.GetTypeName()
        path_l = str(p.GetPath()).lower()
        if "cesium" in str(t).lower() or "tileset" in path_l or "/tiles/" in path_l \
                or path_l.endswith("/tile") or "tile_" in path_l.rsplit("/", 1)[-1]:
            tile_count += 1

    # world bounding box (meters) over default + render purposes
    try:
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                                  [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
        rng = cache.ComputeWorldBound(stage.GetPseudoRoot()).ComputeAlignedRange()
        mn, mx = rng.GetMin(), rng.GetMax()
        bx = float(mx[0] - mn[0]); by = float(mx[1] - mn[1]); bz = float(mx[2] - mn[2])
    except Exception as e:  # noqa: BLE001
        print(f"[warn] bbox failed: {type(e).__name__}: {e}")
        bx = by = bz = float("nan")

    up = UsdGeom.GetStageUpAxis(stage)
    print(f"=== {LOCATION} ===")
    print(f"  prim_count       = {prim_count}")
    print(f"  tile_count_approx= {tile_count}  (heuristic; verify against CesiumTileset)")
    print(f"  bbox (m)         = x:{bx:.1f}  y:{by:.1f}  z:{bz:.1f}   up-axis={up}")
    print(f"  roof_px          = {ROOF_PX}")

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    new = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", newline="", encoding="utf-8") as fh:
        if new:
            fh.write(f"# hardware={HW}\n")
            w = csv.writer(fh)
            w.writerow(["location", "prim_count", "tile_count_approx",
                        "bbox_x_m", "bbox_y_m", "bbox_z_m", "roof_px_x", "roof_px_y"])
        else:
            w = csv.writer(fh)
        w.writerow([LOCATION, prim_count, tile_count,
                    f"{bx:.2f}", f"{by:.2f}", f"{bz:.2f}", ROOF_PX[0], ROOF_PX[1]])
    print(f"[appended] {LOCATION} -> {OUT_CSV}")
    print("  (if you re-run a location, de-dup the CSV later — keep the last row per location)")


main()
