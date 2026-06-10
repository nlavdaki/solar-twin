# Reproducing the results (GRSI guide)

This document lets an independent reviewer reproduce the paper's results from this
repository. It separates what is **reproducible without a GPU** (the calibration, the
ablation, the cross-validation, the pyranometer validation, and all data figures) from
what **requires NVIDIA Isaac Sim + an RTX GPU** (the illuminance extraction itself).

## 0. Environment

```bash
uv sync                 # creates the locked environment from uv.lock / pyproject.toml
uv run pytest           # 34 tests, all GPU-free, must pass
```
Python is pinned by `.python-version`. Dependencies (numpy, pandas, pvlib, matplotlib,
openpyxl; optional `contextily` for the satellite basemap figure) are locked in `uv.lock`.

## 1. Data

Two inputs are needed; both are provided or publicly accessible:

- **CAMS McClear clear-sky GHI** (the calibration reference): publicly available from the
  Copernicus Atmosphere Monitoring Service via SoDa (`soda-pro.com` / `atmosphere.copernicus.eu`).
  One CSV per site, `data/raw_GHI/Location_<X>.csv`. Provider format documented in
  `src/solar_twin/io_cams.py`.
- **Extracted illuminance** (`data/lux_csv/lux_Location_<X>.csv`, `timestamp;lux`) and the
  **Thissio pyranometer** record — released with the paper at **[DATA DOI — e.g. Zenodo]**.
  These are the GPU-extraction outputs, provided so the calibration is reproducible without
  a GPU.

## 2. GPU-free reproduction (the paper's quantitative results)

From provided lux CSVs + CAMS, in order:

```bash
# (a) monolithic dataset + per-location linear fits + per-site calibration export
uv run python scripts/build_dataset.py --lux-dir data/lux_csv --cams-dir data/raw_GHI \
    --out-dir data/dataset

# (b) leave-location-out ABLATION of the structured physical model  (Table: ablation)
#     NOTE: no --geometry-dir -> the clean horizontal-open result (M2 R^2=0.948)
uv run python scripts/ablation_report.py --pooled data/dataset/lux_ghi_monolithic.csv \
    --out data/results/ablation_loo.csv

# (c) deployable physical model export  (PhysicalGhiModel)
uv run python scripts/export_physical_model.py --pooled data/dataset/lux_ghi_monolithic.csv \
    --tier split --out data/dataset/physical_calibration_export.json

# (d) linear leave-location-out per-site table + luminous efficacy
uv run python scripts/loo_validation.py   --pooled data/dataset/lux_ghi_monolithic.csv --out data/results/loo_validation.csv
uv run python scripts/luminous_efficacy.py --pooled data/dataset/lux_ghi_monolithic.csv --out data/results/luminous_efficacy.csv

# (e) pyranometer ground-truth validation (Thissio)  -> R^2 0.937 physical / 0.972 CAMS
uv run python scripts/validate_thissio.py \
    --lux data/lux_csv/lux_Location_Thissio.csv --cams data/raw_GHI/Location_Thissio.csv \
    --pyrano-xlsx data/pyranometer_GHI_ground_level/THISSIO-2020-2024_step-15min_FINAL.xlsx \
    --pooled data/dataset/lux_ghi_monolithic.csv --lat 37.9717 --lon 23.7182 --alt 100 \
    --out data/results/thissio_validation_summary.csv --scatter data/results/thissio_validation_scatter.png

# (f) all paper figures (PNG + vector PDF)
uv run python scripts/make_paper_figures.py --pooled data/dataset/lux_ghi_monolithic.csv \
    --convergence data/results/convergence_table_spp.csv --ablation data/results/ablation_loo.csv \
    --lux-map data/results/figures/lux_map_Location_A.npy --out-dir data/results/figures
```

Expected headline numbers (clear-sky): per-site calibration R² 0.85–0.98; physical-model
leave-location-out R² **0.948** (linear baseline 0.89–0.92); luminous efficacy 27–35 lm/W
(twin scale; ×3.8 ≈ 110 physical); pyranometer **R² 0.937** (CAMS 0.972).

## 3. GPU-required steps (NOT reproducible without Isaac Sim + RTX)

These run inside the **full Isaac Sim GUI** (Script Editor), because the MDL dynamic sky
does not illuminate headlessly. Hardware used: RTX 4070 (12 GB), i5-12600K, 32 GB, Isaac
Sim v5.1.0-rc19 (Kit 107.3.3), Windows.

- `scripts/production_sweep_gui.py` — illuminance extraction (`PtIlluminance` AOV →
  photopic lux) → the `lux_*.csv` consumed above.
- `scripts/benchmark_convergence_gui_v2.py` — `totalSpp` convergence table.
- `scripts/render_lux_map_gui.py` — full-frame lux map (`.npy`) for the hero figure.
- `scripts/extract_geometry_gui.py` — per-pixel tilt/SVF/horizon (optional; see paper §
  Limitations on the azimuth convention).

Their outputs are released as data (§1) so §2 reproduces without a GPU.

## 4. What is in `scripts/deprecated/`

Superseded probes/benchmarks are kept for provenance (e.g. the invalid `rt_subframes`
convergence benchmark; the headless extraction attempts). They are not part of the paper
pipeline and must not be cited; see `scripts/deprecated/README.md`.
