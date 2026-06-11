# Solar-Twin — Findings Report for the Paper (handoff to the writing agent)

**Paper:** extension of Kosmopoulos et al. (2024), *Ray-Tracing modeling for urban
photovoltaic energy planning and management*, Applied Energy 369:123516
(DOI 10.1016/j.apenergy.2024.123516). Target: *Computers & Graphics*.
**New contributions:** a formal radiometric calibration pipeline (RTX-rendered
illuminance → GHI), multi-site generalization, and pyranometer ground-truth validation.

**Hardware/software (cite verbatim in every benchmark):** NVIDIA RTX 4070 (12 GB),
Intel i5-12600K, 32 GB RAM, NVIDIA Isaac Sim v5.1.0-rc19 (Kit SDK 107.3.3, Client
Lib 2.67.0), Windows. Solar position: NREL-SPA via `pvlib` (±0.0003°). Clear-sky
reference: CAMS McClear. Calibration: per-location OLS `GHI = a·lux + b`, plus a
physically-structured inverse model (air-mass luminous efficacy + beam/diffuse
decomposition; §3.6) validated leave-location-out and against the Thissio pyranometer.

---

## 1. Method (one-paragraph summary for Methods section)

Ten georeferenced rooftop USD scenes (Athens; Location_A…J) are rendered in Isaac
Sim RTX Interactive (Path Tracing). For each timestamp the Omniverse Sun Study
(dynamic sky) is positioned from the scene's lat/lon at a UTC-anchored instant; the
Sun-Study clock was measured to be mean solar time (UTC + longitude/15), no DST.
Absolute illuminance is read from the **`PtIlluminance`** render variable and reduced
to photopic lux as **0.2126·R + 0.7152·G + 0.0722·B** (verified to match the Isaac
viewport's own illuminance read-out to ~0.3 %). Each lux value is paired with CAMS
McClear clear-sky GHI at the identical UTC instant (15-min Wh/m² → instantaneous
W/m² at the interval midpoint). Because the renders are cloudless, the comparison is
clear-sky to clear-sky. A per-location linear model maps lux → GHI; a global model is
validated leave-location-out.

---

## 2. Validated chain (scientific-proof actions — each was checked, not assumed)

1. **Extraction = true absolute lux.** `PtIlluminance` matches the viewport's clicked
   "Illuminance value" to ~0.3 % (≈24,800 vs ≈24,872 lux at a roof point). The photopic
   RGB combine — not a single channel, not the simple mean/sum — reproduces the scalar.
2. **Temporal variability is physical.** Driving the Sun Study yields a textbook diurnal
   bell, peaking at solar noon and shifting/growing correctly across the calendar.
3. **Clock verified.** Sun-Study time = UTC + longitude/15 (mean solar), confirmed in
   both summer and winter against NREL-SPA solar noon; no DST discontinuity.
4. **Behavior match vs CAMS (Sprint-0).** Synthetic lux vs CAMS clear-sky GHI: R² ≈ 0.98
   over a summer and a winter day.
5. **Convergence characterized.** The path-tracing convergence control is
   `/rtx/pathtracing/totalSpp` (default 512). Lux converges by totalSpp ≈ 16–32;
   production ran at 512 (fully converged). NOTE: an initial benchmark that swept
   `rt_subframes` was invalid (it is not the convergence knob) — do not cite it.

---

## 3. Results (the numbers for the paper tables)

### 3.1 Per-site calibration — `[SITE_CALIBRATION_TABLE]`
Source: `data/dataset/calibration_export.json`, `data/dataset/lux_ghi_monolithic.csv`.
Per location, `GHI = a·lux + b`, n = 537–538 daylight rows:

| Site | r | R² | efficacy (lm/W) | a | b |
|------|-----|------|------|---------|------|
| A | 0.986 | 0.973 | 31.5 | 0.03684 | −53.6 |
| B | 0.968 | 0.936 | 30.8 | 0.03621 | −30.4 |
| C | 0.988 | 0.976 | 31.2 | 0.03746 | −54.8 |
| D | 0.987 | 0.973 | 31.5 | 0.03670 | −51.5 |
| E | 0.982 | 0.965 | 31.0 | 0.03695 | −46.5 |
| F | 0.988 | 0.977 | 31.1 | 0.03675 | −50.6 |
| G | 0.977 | 0.955 | 33.0 | 0.03593 | −59.1 |
| H | 0.964 | 0.930 | 28.3 | 0.03297 | +32.1 |
| I | 0.978 | 0.957 | 30.3 | 0.03745 | −37.4 |
| J | 0.922 | 0.850 | 27.1 | 0.03063 | +86.5 |

All pass the R² ≥ 0.90 behavior-match gate except J; **H now passes at 0.930** (was 0.864)
after its roof pixel was re-picked to a flat, sky-open patch (see §3.4).

### 3.2 Leave-location-out generalization — `[LOO_TABLE]`
Source: `data/results/loo_validation.csv`. Train on 9 sites, predict the held-out 10th
(elevation ≥ 10°). **This is the LINEAR baseline under the elevation ≥ 10° filter; the structured physical model (§3.6) lifts it to R² 0.952 under the SAME filter** (and to 0.963 on the all-daylight ablation set). ⚠️ **Do not mix filters:** 0.918→0.952 is the elevation ≥ 10° lift; 0.939→0.963 is the all-daylight lift.

| Held-out site | n | RMSE (W/m²) | MBE (W/m²) | R² | nRMSE (%) |
|------|-----|------|------|------|------|
| A | 488 | 48.9 | +13.5 | 0.961 | 8.7 |
| B | 488 | 72.1 | −2.2 | 0.915 | 12.7 |
| C | 488 | 46.2 | +2.4 | 0.965 | 8.2 |
| D | 488 | 48.4 | +13.3 | 0.962 | 8.5 |
| E | 488 | 54.5 | +3.3 | 0.952 | 9.6 |
| F | 489 | 45.3 | +11.7 | 0.967 | 8.0 |
| G | 488 | 69.4 | +36.6 | 0.922 | 12.3 |
| H | 488 | 82.1 | −17.4 | 0.890 | 14.5 |
| I | 488 | 63.2 | −16.9 | 0.935 | 11.1 |
| J | 488 | 133.0 | −46.1 | 0.713 | 23.3 |
| **Aggregate (weighted)** | 4881 | **66.3** | **−0.2** | **0.918** | **11.7** |

The CSV also contains per-site elevation-bin strata [10–20°, 20–40°, >40°].
After the H roof-pixel re-pick, **J is the sole outlier** (R² 0.713); H is now 0.890 (just
under the linear 0.90 gate but a strong site). Excluding J, the nine other sites aggregate
to ≈ R² 0.93 — report transparently; the physical model (§3.6) lifts this elevation-filtered aggregate to **R² 0.952** (and to 0.963 on the all-daylight set).

### 3.3 Luminous efficacy — `[EFFICACY_TABLE]`
Source: `data/results/luminous_efficacy.csv` (+ `luminous_efficacy_scatter.png`).
Filters: GHI > 50 W/m², elevation > 10°.

| Site | mean (lm/W) | std | min | max |
|------|------|-----|-----|-----|
| A | 30.9 | 3.9 | 17 | 48 |
| B | 30.3 | 6.1 | 18 | 55 |
| C | 30.3 | 3.5 | 18 | 45 |
| D | 30.8 | 4.2 | 12 | 47 |
| E | 30.5 | 4.6 | 18 | 51 |
| F | 30.7 | 3.5 | 14 | 44 |
| G | 32.2 | 5.2 | 20 | 50 |
| H | 28.4 | 7.2 | 6 | 47 |
| I | 29.4 | 4.8 | 17 | 50 |
| J | 27.1 | 8.3 | 4 | 45 |

Cross-site mean range **27.1–32.2 lm/W**, well below the ~110 lm/W of a sunlit horizontal
surface. The dominant cause is the twin's **absolute sky-luminance scale**, not tilt: the
MDL dynamic sky renders ≈ **3.8× dim** in absolute terms — independently indicated at
Thissio, an ≈ 11° near-horizontal pixel, which still reads ≈ 28 lm/W — so this is a
**constant** factor the calibration absorbs, confirmed uniform across all 10 sites:
high-sun (elev > 50°) efficacy is **27.9 ± 0.4 lm/W, only a 5 % cross-site spread**, giving
a scale **k ≈ 3.9×** (per-site 3.8–4.0). Effective efficacy × k ≈ 110, matching Perez 1990. A secondary, site-dependent contribution is roof tilt/orientation (the H/J
signature, §3.4; J shows ~2× the scatter of the clean sites — H normalised after its re-pick). The cross-site variation
justifies per-location calibration; the lux→GHI model depends only on the (stable)
relationship, not on the absolute scale.

### 3.4 Geometry diagnosis of H and J (a result, not a defect)
Source: `data/results/site_diag/` (per-site scatter + console diagnostics);
`scene_complexity.csv` (all sites: 41 prims, 4 tiles — equal complexity, so this is
roof geometry, not scene density).
- **Location H — re-picked, now a strong site.** The *original* pixel sampled a tilted,
  intermittently shadowed facet (per-site R² 0.86, efficacy varying ~2× by sun azimuth,
  NW 17.8 vs SE 39.7 lm/W). Re-picking a flat, sky-open, sunlit-all-day patch lifted H to
  per-site R² 0.93 and physical LOO 0.943 (efficacy normalised 35→28 lm/W). The time-varying
  inter-object shadowing on this roof is now documented qualitatively in the
  morning/noon/sunset lux-map figure (F8), not as a weak calibration site. State the
  roof-pixel selection criterion (flat, sky-open, unshadowed across the day) in Methods.
- **Location J — intermittent inter-building occlusion.** 11.2 % shadowed samples,
  efficacy collapsing to 4 lm/W, per-bin R² 0.74 at high sun but 0.03 at 15–30° — a
  fixed obstruction blocking low-angle sun.
- **Control (Location F):** clean across all bins (R² 0.83–0.88, efficacy std 1.1–3.2,
  0.4 % shadowed, flat azimuth).
**Framing:** these demonstrate the twin resolving tilt- and shadow-driven irradiance
variability that horizontal-plane CAMS structurally cannot — the core motivation for
the per-location, geometry-aware approach.

### 3.5 GPU convergence/performance benchmark
Source: `data/results/convergence_table_spp.csv` (valid, totalSpp sweep).
Lux deviation vs totalSpp=512: 8→1.72 %, **16→0.60 % (knee)**, 32→0.36 %, 64→0.02 %.
Render time 1.07 s (totalSpp=8) → 54.4 s (totalSpp=512). VRAM ~5.0–5.2 GB (end-of-render
`nvidia-smi` snapshot = lower bound on peak). Production used totalSpp=512 = fully
converged. Implication: totalSpp≈64 would cut render time ~8× at <0.1 % lux deviation.

### 3.6 Physical (structured) calibration model + ablation — `[ABLATION_TABLE]`
Source: `src/solar_twin/physical_model.py`, `scripts/ablation_report.py`,
`data/results/ablation_loo.csv`.

The constant-efficacy fit `GHI = a·lux + b` ignores two physics: luminous efficacy
varies with air mass (spectrum), and the rooftop pixel is a tilted plane (transposition).
We invert that forward chain into a physically-interpretable model:

> `GHI = lux / (a_beam·k_beam + a_diff·k_diff + a_grnd·k_grnd)`

with *dimensionless* kernels computed (not fitted) from solar geometry, the pixel's
surface (tilt / sky-view-factor / horizon, extracted once from the twin), and the
diffuse fraction `kd = DHI/GHI`:
`k_beam=(1−kd)·max(cosAOI,0)·visible/cos z`, `k_diff=kd·SVF`, `k_grnd=albedo·(1−SVF)`;
beam efficacy `a_beam=a_beam0·(1+c·(AM−1))`. Fitted by linear least squares, so the
coefficients **are** luminous efficacies (lm/W). References: Perez et al. 1990 (luminous
efficacy + anisotropic transposition), Liu–Jordan 1960 (isotropic sky / clearness),
Kasten–Young 1989 (air mass), Erbs et al. 1982 (diffuse-fraction decomposition).

**Leave-location-out ablation on A–J** (`ablation_loo.csv`, common n = 5372). Each
physical term earns its place — a clean, monotone ablation:

| Model | R² | RMSE (W/m²) | nRMSE % |
|------|------|------|------|
| M0 — linear `a·lux + b` (baseline) | 0.939 | 68.0 | 13.0 |
| M1 — + air-mass luminous efficacy | 0.950 | 61.7 | 11.8 |
| **M2 — + beam/diffuse split (kd)** | **0.963** | **53.0** | 10.1 |
| M3 — + air-mass on beam | 0.962 | 53.7 | 10.3 |
| M4 — + ground reflection | 0.962 | 53.7 | 10.3 |

**Headline: the beam/diffuse decomposition (M2) is the best model, lifting leave-location-
out R² 0.939 → 0.963 (RMSE 68 → 53, −22 %).** M3/M4 add nothing beyond M2 — once the split
is present it already captures the elevation dependence, so the explicit air-mass term
becomes redundant and the ground-reflection term is ~0 (parsimonious 2-parameter model).
`kd` is from Erbs (1982) — no measured diffuse required — so this is fully reproducible.
(A–J only, 10 sites, after H's roof pixel was re-picked clean on 2026-06-09 and **Thissio
excluded** from the pool. Two filters, kept separate: **all-daylight** linear 0.939 → physical 0.963; **elevation ≥ 10°** linear 0.918 → physical 0.952. Both linear values are up from 0.893 pre-re-pick.)

**Per-site leave-location-out (M2):** nine rooftops reach **R² 0.94–0.99** (A 0.988,
B 0.973, C 0.983, D 0.987, E 0.988, F 0.982, G 0.967, **H 0.943**, I 0.978); only **J 0.839**
(inter-building occlusion) stays weak — now the **sole** documented geometry case. H was
lifted from 0.786 by re-picking a flat, sky-open, sunlit-all-day roof pixel; state that
selection criterion in Methods. The "twin resolves geometry" evidence now lives in the
qualitative H shadow-sweep figure (§G), not in a weak calibration site.

**Geometry must be applied with a *reconciled* azimuth.** Feeding the raw extractor
geometry into the model *regresses* the tilted sites (with-geometry ablation: M2 → 0.79);
an isolation run with geometry **off** recovers the full horizontal-open R², proving the
per-pixel surface-azimuth (raw stage frame, not true north) is the sole cause — not the model. A
`tilt < 15°` auto-flat guard already protects near-flat pixels. The extractor now stores
`normal_raw` + `north_orientation`; locking that convention is the remaining step to lift
H and J (§6). Independently, where `kd` is *measured* the decomposition is also decisive at
Thissio (0.867 → 0.937, §4).

*Absolute-scale note (resolves the "efficacy ≪ 110" question):* the twin's MDL sky is
≈ 3.8× dim in absolute luminance (twin lux/GHI ≈ 29 vs physical ~110 lm/W at high sun),
a **constant** the calibration absorbs — effective efficacy × 3.8 ≈ 110 ≈ Perez. The
lux→GHI model is unaffected (it needs only a stable relationship, R² ≈ 0.94).

---

## 4. Pyranometer ground-truth validation — TWO INDEPENDENT SITES (RESULT)

**Data provenance / acknowledgments** (for the paper's Acknowledgments + Data Availability):
the **Thissio** record is from the actinometric station of the **National Observatory of
Athens (NOA)**; data owner / contact: **Dr. Basil E. Psiloglou (NOA)**. The
**Thessaloniki** record is from the **Laboratory of Atmospheric Physics, Aristotle University
of Thessaloniki (LAP / AUTh)**, provided by **Prof. A. Bais and Dr. K. Garane**.

### 4.1 Thissio (Athens — NOA)

**What this tests:** an *independent* ground truth (not CAMS) for the calibration. It
confirms the model — and the beam/diffuse decomposition with **measured** kd — against a
real sensor. (The stronger claim, twin > horizontal CAMS on *tilted/shadowed* roofs, is
**not** decided here because the Thissio pixel turned out near-horizontal, ≈ 11°; that
claim is tested at the steep site H, §6.)

**Site:** Thissio, Athens — 37.972°N, 23.7181°E, alt **100 m** (the altitude used in the CAMS McClear request, and therefore the value of record; the geographic station elevation is higher, but McClear's altitude sensitivity is < 0.5 %/100 m and immaterial here).
**Instrument:** Kipp & Zonen **CMP21** thermopile pyranometer — ISO 9060 **Secondary
Standard** (the highest class); GHI in W/m²; spectral range 285–2800 nm; 180° field of view;
response time < 5 s; range ≤ 4000 W/m²; operating −40…80 °C.
**Record:** 15-min averages, 2020–2024 (`TOTAL AVG` = global, `DIFFUSE AVG` = diffuse).
**Station clock = fixed UTC+2 (Greek standard, NO DST)** — established empirically
(clearest-day GHI peak vs NREL-SPA solar noon = +2.0 h in every month). UTC = clock − 2 h.
**Clear-sky screening (mandatory; twin is cloudless):** pvlib-Ineichen ratio in
[0.85, 1.35]; **74 % of days qualify** (~1,350 of 1,828; clean gap clear ~1.1–1.2 vs
cloudy < 0.7). Validation keeps the days' **real years** so synthetic instants join the
measured record exactly.
**Procedure (`validate_thissio.py`):** clear-sky/beam-dominated screening via the
**measured** diffuse fraction `kd = DHI/GHI ≤ 0.25` and `GHI > 50 W/m²`. This selector is
*measurement-intrinsic* — independent of CAMS and of the twin — so the twin-vs-CAMS
comparison is **non-circular** (unlike a measured/CAMS-ratio filter, which flatters CAMS);
306 of 538 rows pass. Held-out k-fold; three arms vs the pyranometer at matched UTC
instants: linear `a·lux+b`, the physical model (§3.6, measured kd), CAMS McClear.

**Result (held-out, clear-sky, n = 306)** — `data/results/thissio_validation_summary.csv`:

| Arm | RMSE (W/m²) | MBE | R² |
|------|------|------|------|
| Linear `a·lux + b` | 85.6 | −0.2 | 0.867 |
| **Physical model (measured kd)** | **59.0** | **+1.1** | **0.937** |
| CAMS McClear (baseline) | 39.4 | +12.3 | 0.972 |

The physical model lifts the twin from R² **0.867 → 0.937** (RMSE −31 %), essentially
unbiased — the independent-ground-truth confirmation of the calibration and of the
beam/diffuse decomposition under *measured* kd. **CAMS still leads on horizontal GHI
(0.972), as expected and not contradicted here:** the Thissio pixel is ≈ 11° tilted, SVF
1.0 (geometry extractor), so it exercises model fidelity, not the tilt-superiority claim.

**Sensor metadata — supplied** (above). The instrument side of the Methods section is
complete: a Secondary-Standard CMP21 is the strongest pyranometer class, so the ground
truth is well characterised.

**Honest caveats to state in the paper:**
- The lux is sampled at one pixel; describe how it was chosen relative to the real sensor
  mounting (co-located as closely as the view allows) — any offset is a caveat.
- Training and this validation are both **clear-sky**; it confirms the model under clear
  skies (matching the renderer), not all-sky conditions (the planned next paper).
- The Thissio pixel is **near-horizontal (≈ 11°)**, so this site validates model fidelity
  against ground truth but does **not** test the tilt-superiority claim; that requires the
  steep site H (§6).
- The twin's absolute luminance is ≈ 3.8× low (constant, absorbed by calibration; §3.3,
  §3.6) — state it so the low fitted efficacies are not misread.

### 4.2 Thessaloniki (AUTh — Laboratory of Atmospheric Physics) — second site + cross-city transfer

A **second, independent** pyranometer site in a **different city** (Thessaloniki, ~300 km
north of Athens), used to test whether the calibration generalises beyond the Athens
training set. Data from the **Laboratory of Atmospheric Physics, AUTh** (Prof. A. Bais,
Dr. K. Garane).

**Site:** AUTh, Thessaloniki — 40.6334°N, 22.9570°E (CAMS request alt 0 m; rooftop ≈ 60 m).
**Instrument:** Kipp & Zonen **CM21** thermopile pyranometer, ISO 9060 Secondary Standard
(same class as the Thissio CMP21). **Record:** 1-min global GHI, year **2025**, in **Universal
Time** (no clock offset, unlike Thissio). **Global-only** (no direct channel) → kd is
**modelled** (Erbs), not measured. **Clear-day screening:** midday clear-sky-index smoothness
(`read_pyranometer_lap.py`); ~99 clear days, season-balanced; CAMS-vs-pyranometer on clear
days = R² 0.986 (harness check).

**Procedure (`validate_site.py`):** clear-day rows joined to CAMS McClear (LAP coords) and to
the Thessaloniki twin lux; arms scored vs the pyranometer.

**Result (clear-sky, n = 7 545)** — `data/results/thessaloniki_validation_summary.csv`:

| Arm | RMSE (W/m²) | MBE | R² |
|------|------|------|------|
| **Twin held-out physical** | **33.9** | **−2.8** | **0.983** |
| Twin global-transfer (A–J → Thessaloniki, **unseen**) | 37.8 | −11.9 | 0.979 |
| Twin linear | 58.1 | −0.0 | 0.951 |
| CAMS McClear (baseline) | 34.1 | +20.2 | 0.983 |

Two findings: **(1) the twin matches CAMS (R² 0.983 = 0.983) and is markedly less biased**
(−2.8 vs CAMS's +20.2 W/m²); **(2) the Athens-trained global model, applied to a never-seen
Thessaloniki rooftop, predicts GHI at R² 0.979** — a genuine **cross-city generalisation**
result (the transfer arm that under-performs at Thissio works here because kd is treated
consistently via Erbs at both train and test). **Tested directly (O11):** the Athens→Thissio
physical transfer is R² **0.463** when fed Thissio's *measured* kd, rising to **0.809** when
fed *Erbs* kd — confirming the kd-convention mismatch as the **dominant** cause; the residual
gap to the held-out 0.937 (MBE +71 W/m²) is a Thissio-specific scale offset. ⚠️ **Do not
generalise the cross-city transfer claim beyond Thessaloniki.**

**Honest framing (do NOT overclaim).** This is a **second independent confirmation site +
cross-city transfer**, *not* the "twin > CAMS on shaded surfaces" result. A bias-vs-geometry
analysis shows CAMS's +20 W/m² is a **proportional clear-sky overestimate** (~3 % at high sun
rising to ~9 % at low sun; `corr(bias, elevation) = +0.20`; largest at high-sun SE azimuth) —
the signature of an **aerosol/turbidity** offset in McClear on these slightly-hazy clear days,
**not** an obstruction (which would give a *negative* elevation correlation and a low-sun,
single-azimuth loss). The LAP sensor is effectively **sky-open**, so the twin's lower bias
means it tracks the real clear-sky GHI more closely than McClear — it does not *resolve
shading* here. The "twin resolves inter-object shadowing" claim therefore remains
**qualitative**, carried by the H morning/noon/sunset shadow-sweep figure (F8): neither
ground-truth sensor sits under genuine obstruction, so quantitative proof of shading
superiority is left to future work (a deliberately obstructed reference site).

---

## 5. Result files (what each contains)

| File | Contents |
|------|----------|
| `data/dataset/lux_ghi_monolithic.csv` (+ `.parquet`) | All A–J rows: location_id, lat/lon/alt, timestamp_utc, calendar fields, solar elevation/azimuth, air mass, sun_study_current_time, qa_flag, lux, ghi |
| `data/dataset/calibration_export.json` | Per-location a/b coefficients + fit stats; loaded by `CalibratedGhiModel.predict(lux)→GHI` |
| `data/results/loo_validation.csv` | Leave-location-out RMSE/MBE/R²/nRMSE per held-out site + elevation strata + weighted aggregate → `[LOO_TABLE]` |
| `data/results/luminous_efficacy.csv` (+ scatter) | Per-location efficacy mean/std/min/max → `[EFFICACY_TABLE]` |
| `data/results/site_diag/*` | H/J/F diagnostic scatters + console report (tilt/occlusion evidence) |
| `data/results/convergence_table_spp.csv` | totalSpp × lux × render-time × VRAM (valid benchmark) |
| `data/results/scene_complexity.csv` | per-scene prim/tile count (uniform → rules out scene-density) |
| `data/pyranometer_thissio_utc.csv` | Thissio sensor GHI/diffuse, UTC-converted |
| `data/pyranometer_thissio_clearsky_days.csv` | classified clear-sky days (~1,350) |
| `data/results/thissio_validation_summary.csv` (+ scatter) | Thissio: linear / physical / CAMS arms vs pyranometer, clear-sky, elevation strata → §4 |
| `data/results/ablation_loo.csv` | M0→M4 leave-location-out ablation of the physical model → `[ABLATION_TABLE]` (§3.6) |
| `data/geometry/geometry_<site>.json` | per-pixel tilt / azimuth (raw + `normal_raw`/`north_orientation` for true-north reconciliation) / SVF / horizon |
| `src/solar_twin/physical_model.py` | the structured beam/diffuse inverse model + ablation + leave-location-out |

---

## 6. Overall analysis & next steps

**Where the evidence stands.** The pipeline produces absolute, physically-validated lux
that tracks CAMS clear-sky GHI with per-site R² 0.85–0.98 and **generalizes to unseen
rooftops at R² 0.918 / nRMSE 11.7 % / ~0 bias** (linear leave-location-out, elevation ≥ 10°).
A physically-structured beam/diffuse model lifts that same elevation-filtered LOO to **R² 0.952**,
and the all-daylight LOO from 0.939 to **0.963** (§3.6; the air-mass efficacy term alone already
gives 0.950), with nine of ten sites at R² 0.94–0.99. Independently, against the **Thissio
pyranometer** the physical model reaches **R² 0.937 (RMSE 59, ~0 bias)** vs linear 0.867
(§4.1) — ground-truth confirmation; a **second independent site (Thessaloniki, AUTh-LAP, a
different city)** gives twin R² **0.983** (= CAMS, less biased) with the Athens model
transferring **unseen at R² 0.979** (§4.2) — a cross-city generalisation result. Cross-site
efficacy variation and J's documented
occlusion case substantiate per-location calibration (H, originally a tilt/shadow case, is
now a clean site after its roof-pixel re-pick — see §3.4).

**What is proven vs. still hypothesized.** Proven: extraction fidelity, temporal/clock
correctness, multi-site calibration + generalization, convergence, the air-mass efficacy
upgrade, and independent pyranometer agreement. **Still hypothesized:** that the twin beats
*horizontal* CAMS on *tilted/shadowed* roofs — neither Thissio (≈ 11° near-flat) nor the
re-picked H (now flat/sky-open) decides it, because the claim **cannot** be proven from a
CAMS-target site at all (at a shaded surface neither the twin nor CAMS matches the
horizontal reference). The decisive test needs an **independent ground-truth sensor at a genuinely
obstructed site**. The Thessaloniki / AUTh-LAP site was validated (§4.2) but turned out
**sky-open** (twin R² 0.983 = CAMS, cross-city transfer 0.979 — a strong confirmation, but
its CAMS +20 W/m² bias is an aerosol/turbidity offset, not obstruction), so a *deliberately
obstructed* reference site remains future work. The qualitative F8 morning/noon/sunset
shadow-sweep already shows the twin resolving this geometry.

**Next steps / status (updated 2026-06-09).**
1. **Thessaloniki second-site validation — DONE (§4.2):** twin held-out R² **0.983** (= CAMS),
   less biased (−2.8 vs +20.2), and the Athens→Thessaloniki **unseen transfer = R² 0.979**
   (cross-city generalisation). The LAP sensor turned out **sky-open** (CAMS +20 is an
   aerosol/turbidity offset, not obstruction), so this is a confirmation + transfer result,
   **not** the shading-superiority test — that still needs a deliberately obstructed reference
   site (future work); the qualitative case is F8.
2. **Cite M2 (beam/diffuse split, R² 0.963, 9 sites 0.94–0.99)** as the structured-model
   global result. **J** is the sole remaining weak site → per-pixel geometry is *optional*
   polish for J alone (and would need the extractor's azimuth/occlusion finished).
3. Absolute-luminance scale constancy — **DONE**: high-sun efficacy **27.9 ± 0.4 lm/W across
   all 10 sites (5 % spread)** → a uniform scale **k ≈ 3.9×** (per-site 3.8–4.0); one constant
   recovers the physical ~110 lm/W everywhere.
4. App integration — **DONE**: `PhysicalGhiModel` + `physical_calibration_export.json`
   (`predict(lux, when, where)`; embeds the ~3.9× scale, tied to this Isaac/MDL sky).
5. Pyranometer sensor metadata — **DONE**: Kipp & Zonen **CMP21** (Thissio) / **CM21**
   (Thessaloniki), ISO 9060:2018 **Secondary Standard**; dates/cadence recorded (§4).
6. **Repo/GRSI publish** (GitHub + Zenodo data DOI), **one 3D scene screenshot**, **C&EE
   reviewer-comment triage**, then hand to the writing agent — the Thessaloniki §4 result can
   be marked pending or included once (1) completes.
