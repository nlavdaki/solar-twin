r"""Production per-location sweep — HEADLESS standalone (run via python.bat).

Renders every instant in a schedule CSV (from make_schedule.py), captures photopic
lux at a roof pixel, and appends to lux_<LOCATION>.csv. CHECKPOINT/RESUME: it skips
timestamps already in the output, so a crash or reboot mid-run loses nothing —
just rerun the same command. Designed for the ~9,900-render, multi-hour jobs.

Standalone (not Script Editor) so it survives for hours with no GUI and uses the
synchronous orchestrator.step (allowed in standalone).

Run (Windows, per location):
    C:\isaacsim\python.bat ^
      "C:\Users\Nikos\Documents\Vz Studio\USD_Extractor_Calibrator_Package\scripts\production_sweep.py" ^
      --stage  "C:/dev/solar-digital-twin-migration/01_old_composer_export/Location_A.usd" ^
      --schedule "C:/.../data/schedule_Location_A.csv" ^
      --out      "C:/.../data/lux_Location_A.csv" ^
      --px 506 --py 418 --camera /World/Camera --rt-subframes 64
"""
from __future__ import annotations

import argparse
import csv
import os

p = argparse.ArgumentParser()
p.add_argument("--stage", required=True)
p.add_argument("--schedule", required=True)
p.add_argument("--out", required=True)
p.add_argument("--px", type=int, required=True)
p.add_argument("--py", type=int, required=True)
p.add_argument("--camera", default="/World/Camera")
p.add_argument("--res", type=int, nargs=2, default=[1280, 720])
p.add_argument("--rt-subframes", type=int, default=64)
p.add_argument("--flush-every", type=int, default=20)
args, _ = p.parse_known_args()

# 1) boot headless FIRST (sync step allowed in standalone)
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

# The Sun Study lives in omni.kit.environment.core. In a minimal headless app it
# is NOT loaded by default, so setting /Environment.time:current would do nothing
# (the bug that produced identical lux every row). Load it explicitly.
from isaacsim.core.utils.extensions import enable_extension  # noqa: E402
enable_extension("omni.kit.environment.core")
for _ in range(10):
    sim.update()

_PHOTOPIC = (0.2126, 0.7152, 0.0722)


def read_schedule(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            rows.append(r)
    return rows


def already_done(path):
    """Resume: timestamps already written (skip them)."""
    done = set()
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                done.add(r["timestamp_utc"])
    return done


def main():
    omni.usd.get_context().open_stage(args.stage)
    for _ in range(60):
        sim.update()

    rep.settings.set_render_pathtraced(samples_per_pixel=1)
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

    stage = omni.usd.get_context().get_stage()
    env = stage.GetPrimAtPath("/Environment")

    # Try the Sun Study player too (belt-and-suspenders with the USD attrs).
    try:
        from omni.kit.environment.core import get_sunstudy_player
        player = get_sunstudy_player()
    except Exception:  # noqa: BLE001
        player = None

    def set_sun(date_str, current_time):
        """Set date+time AND tick the app so the Sun Study recomputes the sun
        BEFORE we render. The missing tick was the frozen-sun bug."""
        if env and env.IsValid():
            env.GetAttribute("date").Set(date_str)
            env.GetAttribute("time:current").Set(float(current_time))
        if player is not None:
            try:
                player.current_date = date_str
                player.current_time = float(current_time)
            except Exception:  # noqa: BLE001
                pass
        for _ in range(3):          # let the environment extension apply the sun
            sim.update()

    def sample_lux():
        rep.orchestrator.step(rt_subframes=args.rt_subframes)
        a = np.asarray(anno.get_data(), dtype=np.float64)
        img = (_PHOTOPIC[0]*a[..., 0] + _PHOTOPIC[1]*a[..., 1] + _PHOTOPIC[2]*a[..., 2]
               if a.ndim == 3 else a)
        H, W = img.shape[:2]
        xi, yi = min(args.px, W-1), min(args.py, H-1)
        return float(np.nanmedian(img[max(0, yi-1):yi+2, max(0, xi-1):xi+2]))

    # SELF-CHECK: prove the sun actually moves before committing to thousands of
    # renders. Render two very different local times; abort if lux is ~identical.
    set_sun("2023-06-21", 6.0);  lux_dawn = sample_lux()
    set_sun("2023-06-21", 12.0); lux_noon = sample_lux()
    print(f"[selfcheck] lux @06:00={lux_dawn:.1f}  @12:00={lux_noon:.1f}")
    if lux_noon <= 0 or abs(lux_noon - lux_dawn) < 0.05 * max(lux_noon, 1):
        print("[ABORT] sun is NOT moving (lux ~identical at 06:00 vs 12:00). The Sun "
              "Study didn't apply. Do NOT trust a full run. Check that "
              "omni.kit.environment.core loaded and /Environment has date/time:current.")
        return
    print("[selfcheck] OK — sun moves, proceeding with sweep.")

    sched = read_schedule(args.schedule)
    done = already_done(args.out)
    todo = [r for r in sched if r["timestamp_utc"] not in done]
    print(f"[sweep] schedule={len(sched)}  done={len(done)}  remaining={len(todo)}")

    new_file = not os.path.exists(args.out)
    fh = open(args.out, "a", newline="", encoding="utf-8")
    w = csv.writer(fh, delimiter=";")
    if new_file:
        w.writerow(["timestamp_utc", "lux"])

    for i, r in enumerate(todo, 1):
        set_sun(r["sun_study_date"], r["sun_study_current_time"])
        lux = sample_lux()
        w.writerow([r["timestamp_utc"], f"{lux:.1f}"])
        if i % args.flush_every == 0:
            fh.flush()
            os.fsync(fh.fileno())
            print(f"[sweep] {i}/{len(todo)}  {r['timestamp_utc']}  lux={lux:.0f}")

    fh.flush()
    fh.close()
    print(f"[sweep] DONE — wrote {len(todo)} new rows to {args.out}")


try:
    main()
finally:
    sim.close()
