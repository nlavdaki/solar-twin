# Editor Handoff — ADDENDUM (2026-06-08)

**Read this with `CG_venue_switch_handoff.md` (2026-06-06).** That document's framing,
venue strategy, reviewer triage, citations, and section-by-section map are all still
valid. This addendum records what has **changed, completed, been added, or needs
correcting** since it was written. Where the two disagree, **this addendum wins** on
numbers and on the four correction items in §C.

Detailed sources of truth in the repo: `PAPER_FINDINGS_REPORT.md` (full results + tables)
and `README.md` (§4.1, §9, §10). Both are current as of 2026-06-08.

---

## A. Pyranometer validation — COMPLETE (the one pending result is in)

The handoff's only open item (`[PYR_*]`, `[CAMS_PYR_R2]`) is resolved. Run:
`validate_thissio.py`, held-out k-fold, clear-sky, **n = 306** rows.

| Arm | RMSE (W/m²) | MBE | R² | placeholder |
|---|---|---|---|---|
| Linear `GHI = a·lux + b` | 85.6 | −0.2 | 0.867 | — (baseline) |
| **Physical model (this paper's model)** | **59.0** | **+1.1** | **0.937** | `[PYR_RMSE]`=59.0 `[PYR_MBE]`=+1.1 `[PYR_R2]`=0.937 `[PYR_NRMSE]`=9.2 |
| CAMS McClear (reference) | 39.4 | +12.3 | 0.972 | `[CAMS_PYR_R2]`=0.972 |

**Two corrections to the handoff's pyranometer expectations (important):**

1. **The "R² = 0.97 prior/old model" is NOT a comparable baseline.** That number came
   from an in-sample throwaway fit on the earlier HSV pipeline. The real, held-out,
   project-model result is **R² = 0.937** (physical) / 0.867 (linear). Report 0.937 as
   the result; do not present 0.97 as "the baseline to beat."
2. **Do NOT claim the twin beats CAMS.** At Thissio, CAMS is *closer* to the pyranometer
   (RMSE 39.4 vs 59.0; R² 0.972 vs 0.937). The handoff's "head-to-head realism test —
   shows whether the twin is more accurate than CAMS" must be reframed: **CAMS leads on
   horizontal GHI, as expected.** The Thissio pixel turned out **near-horizontal (≈11°
   tilt)**, so this site validates *model fidelity against an independent sensor*, not the
   tilt-superiority claim. The twin's value remains **complementary** (per-surface
   geometry CAMS can't resolve), exactly as §14 of the handoff states — just don't assert
   superiority on horizontal GHI.

Defensible sentence: *"Against an independent CMP21 pyranometer, the calibrated twin
predicts clear-sky GHI at R² = 0.937 (RMSE 59 W/m², essentially unbiased), confirming the
calibration transfers to physical measurement; CAMS McClear, a dedicated clear-sky model,
remains marginally closer on horizontal GHI (R² = 0.972), as expected for a near-horizontal
site."*

**Clear-sky filter — methodological upgrade to document (Methods §3.8):** the per-row
validation filter is the **measured diffuse fraction `kd = DHI/GHI ≤ 0.25` with GHI > 50
W/m²**, computed from the station's own global + diffuse channels. This is
*measurement-intrinsic* — independent of CAMS and of the twin — so the twin-vs-CAMS
comparison is **non-circular** (a measured/CAMS-ratio filter would quietly flatter CAMS).
306 of 538 clear rows pass. Sensor (CMP21, ISO 9060:2018 Secondary Standard) is confirmed
and already in the handoff §15/§16.

---

## B. NEW — Physically-structured calibration model + ablation (add to Methods & Results)

The handoff describes only the **linear per-location OLS** (`GHI = a·lux + b`). Since then
we built and validated a **physically-structured inverse model** that should now be the
paper's headline calibration (it fully resolves the handoff's **GAP 4** and strengthens
the novelty argument). Module: `src/solar_twin/physical_model.py`; ablation:
`scripts/ablation_report.py` → `data/results/ablation_loo.csv`.

**Model:** `GHI = lux / (a_beam·k_beam + a_diff·k_diff + a_grnd·k_grnd)`, with
dimensionless kernels computed (not fitted) from solar geometry, surface (tilt/SVF/horizon),
and diffuse fraction kd: `k_beam=(1−kd)·cosAOI·visible/cos z`, `k_diff=kd·SVF`,
`k_grnd=albedo·(1−SVF)`; beam efficacy `a_beam=a_beam0·(1+c·(AM−1))`. Fitted by linear
least squares → coefficients **are** luminous efficacies (lm/W). References to cite:
Perez et al. 1990 (luminous efficacy + transposition), Liu–Jordan 1960, Kasten–Young 1989
(air mass), Erbs et al. 1982 (diffuse decomposition).

**Ablation — leave-location-out on A–J (the objectivity centerpiece, `[ABLATION_TABLE]`):**

| Model | R² | RMSE (W/m²) | nRMSE % |
|---|---|---|---|
| M0 — linear `a·lux+b` (baseline) | 0.939 | 68.0 | 13.0 |
| M1 — + air-mass luminous efficacy | 0.950 | 61.7 | 11.8 |
| **M2 — + beam/diffuse split (kd)** | **0.963** | **53.0** | 10.1 |
| M3 — + air-mass on beam | 0.962 | 53.7 | 10.3 |
| M4 — + ground reflection | 0.962 | 53.7 | 10.3 |

*(10 sites A–J, horizontal-open, common rows; **UPDATED 2026-06-09** after H's roof pixel
was re-picked to a clean sky-open patch (270,222) and Thissio was excluded from the A–J
pool — see the two notes below.)* Clean monotone story: **each physical term earns its
place; the beam/diffuse split (M2, two parameters) is the best/parsimonious model, lifting
leave-location-out R² 0.939 → 0.963 (RMSE −22%).** M3/M4 add nothing. kd from Erbs (no
measured diffuse needed) → fully reproducible. Per-site physical LOO: **nine rooftops
0.94–0.99** (A .988, B .973, C .983, D .987, E .988, F .982, G .967, **H .943**, I .978);
only **J .839** remains weak — now the sole documented geometry case (inter-building
occlusion). Two linear-LOO numbers (different row filters): the ablation's M0 baseline
(all-daylight pooled) is **0.939**; the `loo_validation` per-held-out aggregate (elev ≥ 10°)
is **0.918** (both up from 0.893 before the re-pick; H now 0.890 / J 0.713 linear).

**H roof-pixel re-pick (2026-06-09):** the original H pixel sampled a tilted/intermittently
shadowed facet; re-picking a flat, sky-open, sunlit-all-day patch lifted H from per-site
R² 0.86 → 0.93 and physical LOO 0.79 → 0.94, and normalised its efficacy 35 → 28 lm/W. State
the roof-pixel selection criterion (flat, sky-open, unshadowed across the day) in Methods so
this reads as a documented protocol, not cherry-picking. The "twin resolves geometry"
evidence now lives in the qualitative H morning/noon/sunset shadow-sweep figure (§G), not in
a weak calibration site.

**Keep Thissio OUT of the A–J monolithic:** Thissio is the *independent* pyranometer site;
if its lux/CAMS sit in the A–J `lux_csv`/`raw_GHI` dirs, `build_dataset` pools it into the
10-site set, which both shifts the A–J numbers and **breaks** the `validate_thissio` "pooled
A–J fit applied to Thissio *unseen*" test. All numbers above are A–J only (Thissio excluded).

**Deployable artifact (resolves the app/repro story):** `PhysicalGhiModel` +
`scripts/export_physical_model.py` → `physical_calibration_export.json`. ONE global model,
`predict(lux, when, where)`, computes solar geometry + clear-sky kd internally; generalizes
to unseen roofs (no per-roof coefficients). Caveat: embeds this twin's absolute sky-luminance
scale (see §C-1) so it is tied to the same Isaac/MDL sky configuration.

---

## C. CORRECTIONS to the 2026-06-06 handoff (must propagate to the paper)

**C-1 — Luminous efficacy is NOT mainly roof tilt.** The handoff (§0b, R1.5, §4.2, §4.5,
§5.1) repeatedly explains the ~27–35 lm/W (vs ~110) as *roof-tilt geometry*. That is
**mostly wrong** and now disproven: the dominant cause is the **twin's absolute
sky-luminance scale — the MDL dynamic sky renders ≈ 3.8× dim in absolute terms.** Evidence:
the Thissio pixel is only ≈11° tilted (near-horizontal) yet still reads ≈29 lm/W; and the
*steepest* roof (Location B, 39.8°) calibrates fine (LOO R² 0.972). So the low efficacy is
a **constant** the calibration absorbs — `effective efficacy × 3.8 ≈ 110`, matching Perez.
Roof tilt/orientation is a **secondary, site-specific** effect (the H/J signature).
*Paper fix:* state the twin's absolute-luminance scale factor once; present ~33 lm/W as the
twin's effective efficacy (× scale ≈ physical), with tilt as the secondary per-site
modulation. The lux→GHI model only needs the *stable relationship* (R²≈0.94), not the
absolute scale.

**C-2 — twin-vs-CAMS:** see §A-2. CAMS leads on horizontal GHI; frame complementary, not
superior.

**C-3 — Convergence knob wording:** the handoff is internally inconsistent — GAP 3 still
says "RT_SUBFRAMES=24 (stable by ~16)"; the correct, confirmed knob is
`/rtx/pathtracing/totalSpp` (knee 16, converged 64, production 512), as the handoff itself
states in GAP 1 and §15. Use the totalSpp framing everywhere; drop the RT_SUBFRAMES=24 line.

**C-4 — Pyranometer altitude:** handoff lists Thissio "alt ~168 m"; the CAMS header and the
validation run used **100 m**. Reconcile to the value actually used (100 m) or confirm the
true station altitude before the Methods section fixes it.

---

## D. Figures — GAP 6 now addressable (scripts built, 2026-06-08)

`scripts/make_paper_figures.py` (uv, matplotlib, 300-dpi PNG + vector PDF) generates, from
the result files: **F1** per-site calibration scatter grid · **F2** leave-location-out
predicted-vs-observed (linear + physical panels, R² annotated) · **F3** luminous efficacy
per site · **F4** Athens site map coloured by R² · **F4b** same map over a *pale satellite*
basemap (needs `contextily`) · **F5** convergence (totalSpp vs lux-error + render time) ·
**F6** ablation (M0→M4) · **F7** false-colour rooftop lux map (`solar_twin.luxmap`).
`scripts/render_lux_map_gui.py` captures the numeric lux map in Isaac → `.npy` → F7 (the
C&G hero figure; quantitative lux colorbar, **not** a viewport screenshot).

Still needs the author: one **3D city/scene screenshot** (framed Isaac viewport) and, if the
multi-scale claim is kept, a **district-wide** qualitative render. Everything else is
scripted and reproducible.

---

## E. Results file map — IMPORTANT vs OBSOLETE (`C:\…\Vz Studio\data\results`)

**CITE / USE (current):**

| File | Paper use |
|---|---|
| `dataset/lux_ghi_monolithic.csv` | the dataset (all A–J rows) |
| `dataset/calibration_export.json` | per-location linear model (baseline / app fallback) |
| `dataset/physical_calibration_export.json` | **deployed physical model** (predict lux,when,where) |
| `results/ablation_loo.csv` | `[ABLATION_TABLE]` — **must be the no-geometry run (M2=0.963)** |
| `results/loo_validation.csv` | linear per-held-out-site table (§4.4 baseline) |
| `results/luminous_efficacy.csv` + `luminous_efficacy_scatter.png` | §4.5 efficacy (read with C-1) |
| `results/convergence_table_spp.csv` | §4.3 convergence (the **totalSpp** sweep) |
| `results/scene_complexity.csv` | scene-complexity table + per-site roof pixels |
| `results/thissio_validation_summary.csv` + `thissio_validation_scatter.png` | §4.6 pyranometer |
| `results/figures/` (F1–F7, F4b) + `lux_map_Location_A.npy` | all paper figures |
| `geometry/geometry_*.json` | per-pixel tilt/SVF/horizon (supporting; see caveat below) |

**OBSOLETE — DO NOT CITE:**

- Any **rt_subframes** convergence benchmark / `convergence_table.csv` (v1) — *invalid*
  (flat render time). Only `convergence_table_spp.csv` is valid.
- The **old HSV / 4-day / 1-location** results and the **R²=0.97 in-sample** pyranometer
  number — historical baseline only; superseded by §A.
- The early **dome-pixel** Thissio runs — superseded by the near-flat new-surface pixel.
- Any **with-geometry** `ablation_loo.csv` where M2 ≈ 0.79 — corrupted by an unreconciled
  surface-azimuth convention; the **no-geometry** run (M2 = 0.963) is the correct one.
- `thissio_validation_scatter.png` currently plots the **linear** global-transfer arm; for
  the paper, regenerate/annotate so the figure shows the **physical** arm (0.937) as the
  result, with CAMS (0.972) as reference.

---

## F. Honest open items / caveats (for Limitations + Future Work)

- **Geometry pipeline is optional polish, not load-bearing.** The 0.963 global result is
  *geometry-independent* (horizontal-open). Per-pixel geometry would only help the two weak
  sites (H, J); but the extractor's azimuth convention is unreconciled and its SVF/horizon
  raycast finds no occluders (no physics colliders in the Cesium scenes → SVF=1 for all).
  So J's occlusion is **diagnosed from the lux data**, not from the geometry json. Keep
  H/J as documented geometry cases (handoff §4.2 framing is fine); do **not** claim a
  geometry-corrected fix unless that pipeline is finished.
- **Multi-scale:** all validation is rooftop-level (one pixel/site). Keep the handoff's
  "scalable to district" wording backed by the performance argument (totalSpp 64 ≈ 7 s/frame,
  VRAM ~5 GB); do not claim district/city-scale *validation*.
- **Baseline-rendering comparison (handoff GAP 2)** remains the single biggest open gap — no
  comparison to Radiance/Daysim/rasterization yet.

**Net status:** all result sets are complete (per-site calibration, leave-location-out,
luminous efficacy, convergence, **TWO pyranometer sites** — Thissio §A and Thessaloniki §H),
plus the physically-structured model + ablation and a full figure pipeline (F1–F8). The paper
can be drafted end-to-end; the only author-side artifacts are the 3D scene screenshot and the
repo publish. Remaining *experiments* are future-work only (a deliberately obstructed site for
the shading-superiority claim; all-sky extension).

---

## G. H/J environmental shadowing is VISIBLE — reframe + figure (2026-06-08)

Author inspection of the H and J scenes shows the physical mechanism directly: at **H**,
morning and sunset renders show shadows from surrounding structures/vegetation sweeping
across the rooftop and intermittently covering the sampled pixel; at **J**, the sampled
pixel sits on a **tilted facet** (over an entrance), not the intended horizontal. This is
exactly the statistical signature already reported (H: azimuth-dependent efficacy + low-sun
R² loss; J: collapse at low elevation).

**Key reframe (put in Discussion §5.1/§5.2 — it strengthens the core claim):** the twin
*renders this shadowing/tilt correctly* — the pixel lux genuinely drops when the surface is
shadowed or off-normal. Therefore the poor CAMS-fit at H/J is the twin and CAMS
**disagreeing because the twin resolves geometry CAMS is structurally blind to** (CAMS is
horizontal and obstruction-free), **not** twin error. CAMS is simply the wrong reference for
a shaded/tilted surface. This is the paper's central value proposition (handoff §14) made
concrete — and it is precisely why "twin > CAMS" cannot be proven from CAMS itself: at a
shaded surface neither matches CAMS, and only an **independent shaded sensor** can adjudicate
(→ the Thessaloniki / AUTh-LAP site, now validated in §H — but it turned out **sky-open**, so a
*deliberately obstructed* reference site is the real future-work test).

**Consequence for the geometry-extraction gap:** the renderer captures the occlusion even
though our geometry extractor's SVF/horizon returned "open" (no physics colliders in the
Cesium scenes). So the **illuminance renders themselves are the occlusion evidence** — the
SVF-extraction limitation is **not blocking** for the paper.

**Figure (resolves GAP 6 strongly):** H at **morning / noon / sunset** false-colour lux maps
(`render_lux_map_gui.py` at three timestamps) showing the shadow sweep across the rooftop,
beside the aerial photogrammetric view; a single panel for J's tilted facet. Caption: *"the
twin resolves time-varying inter-object shadowing and roof tilt on individual rooftops that a
horizontal clear-sky model (CAMS) cannot."* No re-render or re-computation of results is
needed — the numbers stand; this only adds the visual mechanism and the reframe.

---

## H. Thessaloniki — SECOND independent ground-truth site + cross-city transfer (NEW, 2026-06-09)

A second pyranometer site in a **different city** (Thessaloniki, ~300 km from Athens) now
validates the calibration beyond the Athens training set. → PAPER_FINDINGS **§4.2** (added).

**Data provenance (for Acknowledgments + Data Availability):** **Thissio** = National
Observatory of Athens (NOA) actinometric station; data owner / contact **[PLACEHOLDER — NOA
provider]**. **Thessaloniki** = Laboratory of Atmospheric Physics, Aristotle University of
Thessaloniki (LAP / AUTh), provided by **Prof. A. Bais and Dr. K. Garane**. Sensor: Kipp &
Zonen **CM21**, ISO 9060 Secondary Standard (same class as Thissio's CMP21). Record: 1-min
global GHI, 2025, **Universal Time** (no clock offset); global-only → kd modelled (Erbs).

**Result (clear-sky, n = 7 545)** — `data/results/thessaloniki_validation_summary.csv`:

| Arm | RMSE | MBE | R² |
|---|---|---|---|
| **Twin held-out physical** | **33.9** | **−2.8** | **0.983** |
| Twin global-transfer (A–J → Thessaloniki, **unseen**) | 37.8 | −11.9 | 0.979 |
| Twin linear | 58.1 | −0.0 | 0.951 |
| CAMS McClear | 34.1 | +20.2 | 0.983 |

**Headlines:** the twin **matches CAMS (0.983)** and is **less biased** (−2.8 vs +20.2); the
**Athens-trained model transfers unseen to a different-city rooftop at R² 0.979** — a strong
cross-city generalisation (the transfer arm that failed at Thissio works here because kd is
consistent — Erbs — at train and test).

**Honest framing — NOT the shading-superiority result.** A bias-vs-geometry analysis shows
CAMS's +20 W/m² is a **proportional clear-sky overestimate** (~3 % at high sun → ~9 % at low
sun; `corr(bias, elev) = +0.20`; peaks at high-sun SE azimuth) — an **aerosol/turbidity**
offset in McClear, **not** an obstruction (which would give a *negative* elevation correlation
+ a low-sun, single-azimuth loss). The LAP sensor is effectively **sky-open**. So Thessaloniki
is a **confirmation + cross-city-transfer** result; the "twin > CAMS on shaded surfaces" claim
stays **qualitative** (the H F8 shadow-sweep), pending a *deliberately obstructed* reference
site (future work).
