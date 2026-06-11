# solar-twin — USD Extractor & Calibrator

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20630337.svg)](https://doi.org/10.5281/zenodo.20630337)

Per-location **lux → GHI** calibration from an NVIDIA Omniverse / Isaac Sim urban
digital twin, calibrated against **CAMS** clear-sky GHI. Produces a versioned
model artifact consumed by a separate GHI-estimation app via
`GhiModel.predict(lux) → GHI`.

> The design dossier (the *why*, full methodology, validation strategy, risk
> register) lives separately at `…/Lux_GHI_extraction_manipulation_calibration/`.
> This repo is the *code* and the operational guide.

---

## 1. Goal

Turn a geometry-accurate but radiometrically-uncalibrated **synthetic** light
signal (illuminance, lux, rendered by Omniverse RTX path tracing on a rooftop in
the digital twin) into a calibrated estimate of the **real** solar resource
(**GHI**, W/m², the quantity used for PV yield). The end product is a per-location
calibration that a separate application loads to convert twin-derived lux into GHI.

Why this is worth doing: the twin captures *site-specific geometry* a satellite
product cannot — roof tilt, orientation, self-shading, and inter-building
occlusion. CAMS gives the absolute broadband resource; the twin gives the local
geometric modulation. Calibration links the two.

---

## 2. Research methodology (end to end)

1. **Author / georeference the twin** (one-time, manual, already done): each
   location is a USD scene (`Location_A.usd … Location_J.usd`) georeferenced so
   the scene latitude/longitude/altitude match the CAMS data for that site.
2. **Drive the sun deterministically.** For every timestamp, the Omniverse Sun
   Study (dynamic sky) is set to the date + time-of-day that places the sun
   physically (from the scene's lat/lon). Time is anchored to **UTC**; the Sun
   Study clock is **mean solar time = UTC + longitude/15** (measured, not assumed
   — see §4). No civil timezone, no DST.
3. **Extract absolute illuminance.** The RTX **`PtIlluminance`** render variable
   is captured per frame; the photopic lux at a fixed roof pixel is
   `0.2126·R + 0.7152·G + 0.0722·B` (verified to match the viewport's own
   "Illuminance value" to ~0.3%). Path tracing is rendered to convergence before
   sampling.
4. **Align to CAMS.** Each rendered lux is paired with the CAMS clear-sky GHI for
   the *same UTC instant* (CAMS is 15-min Wh/m² → instantaneous W/m² at the
   interval midpoint). The `:00`/hourly marks land on CAMS midpoints, so the join
   is exact.
5. **Assemble one monolithic dataset** across all locations with physical
   covariates (solar elevation, azimuth, air mass) and QA flags.
6. **Fit + validate the calibration** (per-location now; one global
   synthetic→real transfer model once all locations are extracted).

The synthetic scenes are **cloudless**, which is why the reference is CAMS
**McClear clear-sky** GHI: clear-sky ↔ clear-sky is a consistent comparison.

---

## 3. Goals of the dataset / sampling

- **Sites:** 10 rooftops (`Location_A … Location_J`).
- **Temporal coverage (current run):** 1 year (2025), 4 days/month, **hourly**,
  dawn→sunset. ~581 renders/location. Justified because the twin is clear-sky and
  deterministic — sun geometry repeats annually, so one year covers the full
  envelope without information loss. (Cadence is a config knob; denser coverage
  can be appended later via checkpoint/resume.)
- **Daylight only:** rows below the solar-elevation cutoff (pre-dawn/post-sunset)
  are filtered out.

---

## 4. Ground truth & scientific-proof actions

Each link in the chain was *validated*, not assumed:

- **Extraction is real absolute lux** — the captured `PtIlluminance` value matches
  the Isaac viewport's interactive "Illuminance value at clicked pixel" to ~0.3%
  (≈24,800 lux vs ≈24,872 lux at a sampled roof point). The photopic RGB combine,
  not a single channel, reproduces the viewport scalar (the simple mean and sum do
  not).
- **Temporal variability is physical** — driving the Sun Study across a day
  produces a textbook diurnal bell that peaks at solar noon and grows/shifts
  correctly across the calendar (proof the sun truly moves with the scene).
- **The clock is correct** — the Sun-Study time offset was *measured* in both
  summer and winter (lux-peak vs pvlib/NREL-SPA UTC solar noon) and found to be
  longitude/15 (mean solar time) in both seasons → no DST discontinuity. NREL-SPA
  (via `pvlib`) is the solar-position reference (±0.0003°).
- **Behavior match vs CAMS** — synthetic lux vs real CAMS clear-sky GHI tracks
  with **R² ≈ 0.98** across a summer and a winter day (Sprint-0), i.e. the twin's
  illuminance is a faithful proxy for the real resource. The apparent luminous
  efficacy (~33 lx·(W/m²)⁻¹ vs the ~110 of a horizontal surface) reflects the
  roof-tilt-vs-horizontal geometry — exactly the per-location transfer the
  calibration captures, not an error.

**Success metrics for the calibration:** gate on **behavior-match R² ≥ 0.90**;
report **RMSE and MBE (W/m²)** as the headline accuracy. The global transfer model
is validated **leave-location-out** (train on N−1 sites, predict an unseen site).

### 4.1 Ground-level validation against a pyranometer — **Thissio (result)**

The calibration's ultimate ground truth is an in-situ **pyranometer** at **Thissio**
(Athens; 37.972°N, 23.7181°E) — a **Kipp & Zonen CMP21** thermopile pyranometer, ISO 9060
**Secondary Standard** (top class; 285–2800 nm, 180° FOV, response < 5 s), logging 15-min
GHI for **2020–2024** (`TOTAL AVG` = global, `DIFFUSE AVG` = diffuse). Established so far:

- **Station clock = fixed UTC+2 (Greek standard, NO DST)** — determined empirically
  (clearest-day-per-month GHI peak vs pvlib solar noon = +2.0 h in every month, both
  seasons). Conversion to UTC is a constant −2 h. *(`read_pyranometer.py`.)*
- **Clear-sky filtering is mandatory** — the twin is cloudless, the pyranometer is
  all-sky. A pvlib-Ineichen ratio test classifies days; **74 % of days are clear**
  (~1 350 of 1 828, ~270/yr), with a clean gap (clear ~1.1–1.2 vs cloudy < 0.7).
- **Validation timestamps keep their real years** so synthetic-lux instants join the
  measured record exactly (`select_clear_days.py` without `--year`).

Procedure (`validate_thissio.py`): extract synthetic lux at the sensor's pixel, screen to
clear-sky/beam-dominated rows via the **measured** diffuse fraction (kd = DHI/GHI ≤ 0.25 &
GHI > 50 — measurement-intrinsic, so non-circular vs CAMS; 306/538 rows kept), and compare
held-out arms to measured GHI. **Result:** linear R² 0.867 (RMSE 85.6) → **physical model
R² 0.937** (RMSE 59.0, ~0 bias); CAMS McClear 0.972 (RMSE 39.4). The physical model with
measured kd is the independent ground-truth confirmation (§10).

Note: the Thissio pixel is ≈ 11° (near-flat), so CAMS still leads on *horizontal* GHI as
expected — this site validates model fidelity, not the tilt-superiority claim (that needs
the steep site **H**). Open item (optional): lock the surface-azimuth convention to close the H tilt
result (§10); the geometry pass is otherwise not needed for the headline.

---

## 5. Pipeline & layout

```
solar-twin/
├── pyproject.toml / uv.lock / .python-version   # uv project (see §7)
├── config/
│   ├── sites.example.yaml        # per-site lat/lon/alt + paths + AOV id
│   └── sweep.example.yaml        # cadence, cutoff, render settings
├── src/solar_twin/               # GPU-INDEPENDENT core (uv, fully tested)
│   ├── ephemeris.py              # pvlib NREL-SPA + UTC↔Sun-Study time conversion
│   ├── io_cams.py                # CAMS McClear parse, Wh/m²→W/m², UTC join, lux CSV IO
│   ├── dataset.py                # monolithic table assembly + daylight filter + QA
│   ├── calibrate.py              # lux→GHI fit, efficacy, behavior-match, season CV
│   ├── export_model.py           # versioned calibration_export.json
│   ├── ghi_model.py              # CalibratedGhiModel.predict(lux)→GHI (app drop-in)
│   ├── capture.py                # RTX PtIlluminance capture + photopic combine (GPU)
│   └── sweep.py                  # (headless orchestrator — superseded by GUI runner)
├── scripts/                      # LIVE scripts (the supported pipeline)
│   ├── make_schedule.py          # (uv) render schedule CSV — CAMS site OR --lat/--lon + --clear-days
│   ├── production_sweep_gui.py   # ← MAIN extractor: paste into Isaac GUI Script Editor
│   ├── build_dataset.py          # (uv) lux_*.csv + CAMS → monolithic dataset + fits + export
│   ├── live_check_script_editor.py  # (GUI) verify PtIlluminance vs viewport at a pixel
│   ├── set_environment_time.py   # (GUI) temporal-variability test (drives Sun Study)
│   ├── find_time_offset.py       # (uv) confirm the UTC→Sun-Study offset (no DST)
│   ├── pick_roof_pixel.py        # (GUI) selection→pixel helper
│   │   # ---- pyranometer ground-truth (Thissio) ----
│   ├── read_pyranometer.py       # (uv) Thissio .xlsx → UTC CSV + clear-sky-day classifier
│   ├── select_clear_days.py      # (uv) pick representative clear days (keeps real years)
│   ├── pyranometer_validation.py # (uv) calibrated GHI vs in-situ pyranometer (+--self-test)
│   │   # ---- paper benchmarks & validation (see §9) ----
│   ├── benchmark_convergence_gui_v2.py # (GUI) totalSpp × lux × render-time × VRAM → convergence_table_spp.csv
│   ├── scene_complexity_gui.py   # (GUI) per-scene prim/tile count, bbox → scene_complexity.csv
│   ├── loo_validation.py         # (uv) leave-location-out CV → loo_validation.csv
│   ├── luminous_efficacy.py      # (uv) per-location lux/GHI efficacy → luminous_efficacy.csv (+scatter)
│   └── deprecated/               # superseded scripts kept for provenance (see its README)
├── data/  (gitignored)           # raw_GHI, pyranometer, lux_csv, schedules, dataset, results
└── tests/                        # 34 passing; core modules validated on real data
```

> Note: the production extractor is `production_sweep_gui.py`, run from the **full
> Isaac Sim GUI Script Editor**. The headless path (`scripts/deprecated/production_sweep.py`)
> is retained for provenance but the MDL dynamic sky does not light the scene
> headlessly, so the GUI runner is the supported method. See `scripts/deprecated/README.md`
> for the full list of superseded scripts and why.

---

## 6. How to run an extraction (per location)

1. **Generate the schedule** (uv env, fast, no GPU):
   ```bash
   uv run python scripts/make_schedule.py \
     --cams "…/data/raw_GHI/Location_A.csv" --location Location_A \
     --out "…/data/extraction_schedule/schedule_Location_A.csv" \
     --start 2025-01-01 --end 2025-12-31 --freq 60min --days-per-month 4
   ```
2. **Open the scene** in the full Isaac Sim GUI (`isaac-sim.bat`), set the viewport
   renderer to **RTX – Interactive (Path Tracing)**.
3. **Configure** `scripts/production_sweep_gui.py` (schedule path, out path,
   `ROOF_PX` for this location — see §8) and paste it into **Window → Script
   Editor**, then Run. A self-check renders 06:00 vs noon and aborts if the scene
   isn't lit; otherwise it sweeps, writing `lux_<LOCATION>.csv` (`timestamp_utc;lux`)
   with checkpoint/resume (safe to stop and rerun).
4. **Assemble + calibrate** (uv env, after one or more locations land):
   ```bash
   uv run python scripts/build_dataset.py \
     --lux-dir "…/data/lux_csv" --cams-dir "…/data/raw_GHI" --out-dir "…/data/dataset"
   ```
   → `lux_ghi_monolithic.csv` (+ `.parquet`) and `calibration_export.json`.

> Windows shell note: every path with a space (e.g. `Vz Studio`) **must be quoted**.

---

## 7. Environment (uv)

This project uses [uv](https://docs.astral.sh/uv/). Python is pinned in
`.python-version`; dev tools live in the PEP 735 `[dependency-groups]` and are
installed automatically by `uv run`.

```bash
uv sync                 # create .venv, install core deps + dev group, lock to uv.lock
uv run pytest           # run the test suite (34 passing)
uv run ruff check .     # lint
```

- **Core modules** (`ephemeris`, `io_cams`, `dataset`, `calibrate`,
  `export_model`, `ghi_model`): pure Python — fully covered by `uv`.
- **Omniverse scripts** (`production_sweep_gui.py`, `capture.py`, the probes):
  require **Isaac Sim + RTX GPU**; their `omni.*` / `pxr` imports come from the
  **Isaac Sim runtime**, not uv. Run them inside Isaac (GUI Script Editor), not the
  uv venv.
- Commit `uv.lock` for reproducibility (it is *not* gitignored).

---

## 8. Extraction parameters (operational record)

```
RT_SUBFRAMES      = 24    # path-tracing convergence (Sprint-0 stable by ~16)
SKY_SETTLE_FRAMES = 3     # app-update ticks after setting time, so the sky recomputes
FLUSH_EVERY       = 10    # (the GUI runner now flushes every row for live progress)
```

Per-location roof sample pixels (chosen on a sunlit roof via View → Illuminance):

```
ROOF_PX_A = (506, 418)
ROOF_PX_B = (755, 466)
ROOF_PX_C = (277, 60)
ROOF_PX_D = (739, 437)
ROOF_PX_E = (547, 234)
ROOF_PX_F = (659, 422)
ROOF_PX_G = (875, 365)
ROOF_PX_H = (270, 222)   # re-picked 2026-06-09 (flat/sky-open); was (507, 498) tilted/shadowed
ROOF_PX_I = (635, 355)
ROOF_PX_J = (618,346) 
ROOF_PX_Thissio = (509,258)  
ROOF_PX_LAP = (589,179)
```

---

## 9. Paper benchmarks & validation

Tooling for the *Computers & Graphics* paper (extends Kosmopoulos et al. 2024,
Applied Energy 369:123516). Hardware to cite in every benchmark: **RTX 4070 12 GB,
i5-12600K, 32 GB, Isaac Sim 5.1.0-rc19 (Kit 107.3.3), Windows.** All outputs land
in `data/results/` with a `#`-comment header recording hardware + date. Each script
stamps that header itself.

| # | Script | Env | Produces | When |
|---|--------|-----|----------|------|
| P1 | `benchmark_convergence_gui_v2.py` | Isaac GUI | `convergence_table_spp.csv` — **totalSpp** {8…512} × mean/std lux × render-time × VRAM | done ✓ |
| P2 | `scene_complexity_gui.py` | Isaac GUI | `scene_complexity.csv` — prim/tile count, bbox, roof pixel (per scene) | per open scene |
| P3 | `loo_validation.py` | uv | `loo_validation.csv` — leave-location-out RMSE/MBE/R²/nRMSE + elevation strata | after all sites + `build_dataset` |
| P4 | `luminous_efficacy.py` | uv | `luminous_efficacy.csv` (+ scatter) — per-location lux/GHI | after `build_dataset` |
| P5 | `validate_thissio.py` | uv | `thissio_validation_summary.csv` (+ scatter) — linear / physical / CAMS arms vs Thissio pyranometer | done ✓ (phys R² 0.937) |
| P6 | `ablation_report.py` | uv | `ablation_loo.csv` — M0→M4 physical-model leave-location-out ablation | done ✓ (air-mass R² 0.937) |
| P7 | `extract_geometry_gui.py` | Isaac GUI | `geometry_<site>.json` — tilt/azimuth/SVF/horizon per pixel | per scene (H/J pending azimuth lock) |
| P8 | `export_physical_model.py` | uv | `physical_calibration_export.json` — deployable `PhysicalGhiModel` (global, `predict(lux, when, where)`) | after `build_dataset` |

**Status:** P1 run (valid result below). P2 is a GUI script. P3/P4/P5 are GPU-free,
run-tested on synthetic data; P5 has `--self-test`. `uv run pytest` stays at 34 passing.

### Convergence result (P1 v2, Location_A, summer noon, RTX 4070)
The convergence knob is **`/rtx/pathtracing/totalSpp`** (default 512), **not**
`rt_subframes`. Sweeping totalSpp (cold reset via `/rtx/resetPtAccumOnAnimTimeChange`)
gave a valid curve: lux converges fast — deviation vs totalSpp=512: 8→1.72%,
**16→0.60% (knee)**, 32→0.36%, 64→0.02%. Render time 1.07 s (totalSpp=8) → 54.4 s
(totalSpp=512); VRAM ~5.0–5.2 GB stable. Production used the default totalSpp=512 →
fully converged. (Implication: totalSpp≈64 would cut render time ~8× at <0.1% lux
deviation, if a faster re-run is ever needed.)

### Honesty rules baked into the tooling (do not violate in the paper)

- **Performance:** cite the v2 per-totalSpp render times from `convergence_table_spp.csv`
  (e.g. ~54 s/frame at totalSpp=512 on the RTX 4070). An earlier "~48 s/frame" figure
  was a wall-clock-derived *rate* from a partial run — consistent, but the v2 table is
  the precise source.
- **INVALID — never cite:** (a) the original rt_subframes benchmark (`deprecated/benchmark_convergence_gui.py`)
  — render time stayed flat because rt_subframes isn't the convergence knob; (b) the
  warm-viewport "lux flat across rt8–32" ladder — measured with pre-accumulated samples.
  Use only the **totalSpp** table.
- **VRAM is an end-of-render snapshot** (`nvidia-smi`), i.e. a **lower bound on peak**,
  not the true peak. Label it as such.
- **RT_SUBFRAMES ambiguity:** README documents 24; the 10-location sweep ran at **32**.
  The convergence table includes both so the paper can cite the empirically-chosen
  value. Do not silently change production scripts to reconcile this — decide, then
  document.

### Success metrics (calibration)
Gate: **behavior-match R² ≥ 0.90**. Headline accuracy: **RMSE, MBE (W/m²)**. Global
transfer model validated **leave-location-out** (train N−1 sites, predict an unseen
site). Pyranometer reference (Thissio, clear-sky, held-out): physical model **R² = 0.937**;
CAMS McClear **R² = 0.972** (CAMS leads on this near-horizontal site, as expected). *(The
old "R² = 0.97 baseline" was an in-sample HSV-pipeline figure — do not cite it.)*

---

## 10. Results obtained (10 sites A–J + Thissio pyranometer)

All numbers below are from real runs on the full A–J dataset (537–538 daylight rows
per site, 2025 hourly clear-day geometry vs CAMS McClear). Result files in
`data/results/` and `data/dataset/`.

**Per-site calibration** (`calibration_export.json`, `lux_ghi_monolithic.csv`) — fit
`GHI = a·lux + b` per location: R² **0.85–0.98**, luminous efficacy **27–35 lm/W**
(the twin's MDL sky renders ≈ 3.8–4.0× dim in absolute luminance — a *constant* the
calibration absorbs; effective efficacy × ≈3.9 ≈ 110 lm/W ≈ Perez 1990 horizontal. Roof
tilt is a **secondary** per-site modulation, not the cause). 8 of 10 sites R² ≥ 0.95.

**Leave-location-out generalization** (`loo_validation.csv`) — train on 9 sites,
predict the unseen 10th: **aggregate R² = 0.918, RMSE = 66 W/m², MBE ≈ 0, nRMSE = 11.7 %**
(10 sites A–J, after the H roof-pixel re-pick and with Thissio excluded from the pool; was
0.89 / RMSE 73). "Typical" sites (A, C, D, F) reach LOO R² ≈ 0.96, nRMSE ≈ 8.2 %; only
**J** (0.713) and **H** (0.890) fall below the 0.90 linear gate — H now only marginally.

**Physical (structured) model + ablation** (`physical_model.py`, `ablation_loo.csv`) —
inverse model `GHI = lux / (a_beam·k_beam + a_diff·k_diff + a_grnd·k_grnd)` with kernels
from solar geometry + surface (tilt/SVF/horizon) + diffuse fraction kd; coefficients are
luminous efficacies. Leave-location-out ablation (monotone, 10 sites A–J): linear **0.939 → +air-mass 0.950 → +beam/diffuse
split 0.963** (RMSE 68→53). M2 (the split) is the best, parsimonious model — M3/M4 add
nothing; kd from Erbs, fully reproducible. Per-site LOO: **9 rooftops 0.94–0.99**; only
**J (0.839)** stays weak (inter-building occlusion) — now the sole geometry case (**H** rose
to 0.943 after re-picking a flat, sky-open roof pixel). Applying *raw* geometry regresses the
tilted sites (isolation test: geometry off → 0.963), so the surface-azimuth convention must
be locked first.
*Absolute scale:* the twin sky is ≈ 3.8× dim (constant, absorbed by the fit; effective
efficacy × 3.8 ≈ 110 ≈ Perez).

**Luminous efficacy** (`luminous_efficacy.csv` + scatter) — cross-site mean range
**27.1–35.1 lm/W**; the spread is the evidence that per-location calibration is needed.

**Two sites are weak — diagnosed as real geometry, kept as documented cases**
(`diagnose_site.py`; `scene_complexity.csv` shows all sites are equal complexity, so
this is roof geometry, not scene density):
- **Location H — tilted/oriented facet:** efficacy varies ~2× with solar azimuth
  (NW 17.8 vs SE 39.7 lm/W), ~0 % shadowed; a single linear fit can't capture the
  angle-of-incidence dependence (per-site R² 0.86).
- **Location J — intermittent occlusion:** 11 % shadowed samples, efficacy down to
  4 lm/W, per-bin R² 0.74 at high sun but 0.03 at 15–30° (a fixed obstruction blocks
  low-angle sun). Per-site R² 0.85.

These are a **feature for the paper**: the twin resolves tilt- and shadow-driven
variability that horizontal-plane CAMS structurally cannot — motivating per-location
calibration.

**Convergence/performance** (`convergence_table_spp.csv`) — the knob is
`/rtx/pathtracing/totalSpp` (not rt_subframes); lux converges by totalSpp≈16–32;
production ran at the default 512 (fully converged); ~54 s/frame at 512 on the RTX 4070;
VRAM ~5 GB. See §9.

**Pyranometer ground truth (Thissio)** (`validate_thissio.py`,
`thissio_validation_summary.csv`) — held-out, clear-sky (measured kd ≤ 0.25 & GHI > 50;
non-circular, 306 rows): linear **R² 0.867** (RMSE 85.6) → **physical model R² 0.937**
(RMSE 59.0, ~0 bias); CAMS McClear **0.972** (RMSE 39.4). The physical model + measured kd
gives independent ground-truth confirmation of the calibration. CAMS still leads on
*horizontal* GHI (expected): the Thissio pixel is ≈ 11° (near-flat), so it validates model
fidelity, not the tilt-superiority claim — that is tested at the steep site **H** once the
geometry surface-azimuth convention is locked (the extractor now stores `normal_raw` +
`north_orientation` for that). The kd filter is measurement-intrinsic, so the twin-vs-CAMS
comparison is non-circular.
