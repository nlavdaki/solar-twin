# Synthetic illuminance data (`data/synthetic_lux/`)

These files are the **authors' own** synthetic illuminance output, rendered with NVIDIA
Isaac Sim RTX path tracing (`PtIlluminance` AOV) over an urban digital twin of Athens and
converted to photopic illuminance (lux) via the CIE luminosity weighting
`lux = 0.2126·R + 0.7152·G + 0.0722·B`. They are released so the calibration, validation,
and figure pipelines can be reproduced **without a GPU or Isaac Sim**.

## Files

| File | Contents |
|------|----------|
| `lux_Location_A.csv` … `lux_Location_J.csv` | 10 Athens rooftop sites — the calibration / leave-location-out set. |
| `lux_Location_Thissio.csv` | Validation-site render at the NOA Thissio sensor pixel. |
| `lux_Location_Thessaloniki.csv` | Validation-site render at the LAP/AUTh (Thessaloniki) sensor pixel. |
| `lux_ghi_monolithic.csv` | Calibration-ready joined table: per-timestamp synthetic lux + solar geometry + clear-sky GHI. |

## Schema

Per-site files (`;`-delimited):

```
timestamp_utc ; lux
2025-01-01T06:00:00+00:00 ; 1482.8
```

`lux_ghi_monolithic.csv` (`;`-delimited) columns:
`location_id, latitude, longitude, altitude_m, timestamp_utc, year, month, day, hour,
day_of_year, solar_elevation_deg, solar_azimuth_deg, air_mass, sun_study_current_time,
qa_flag, lux, ghi`

- `lux` — synthetic photopic illuminance (lm/m²), authors' own RTX render output.
- `ghi` — global horizontal irradiance (W/m²) used as the calibration target. **Source:
  CAMS McClear v3.6 clear-sky model (Copernicus Atmosphere Monitoring Service).**

## Provenance, attribution, and licence

- **Synthetic lux** (all `lux*` columns/files): created by the authors; released under
  **CC-BY-4.0**. Please cite the paper and the software (`CITATION.cff`).
- **`ghi` column** in the monolithic table: derived from **CAMS McClear** (Copernicus),
  used under the Copernicus licence — free reuse with attribution to CAMS/Copernicus.
- **Ground-truth pyranometer data are NOT included here** and are not the authors' to
  redistribute: the Thissio record is owned by the **National Observatory of Athens (NOA)**
  (contact: Dr. Basil E. Psiloglou); the Thessaloniki record by the **Laboratory of
  Atmospheric Physics, Aristotle University of Thessaloniki (LAP/AUTh)** (Prof. A. Bais,
  Dr. K. Garane). Both are available from the owners on reasonable request. The synthetic
  renders for those two validation sites are included so the twin side of the comparison is
  reproducible.
