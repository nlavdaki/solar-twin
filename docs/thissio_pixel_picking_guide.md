# Thissio pyranometer-pixel picking — guide & decision rule

The pyranometer measures **GHI on a horizontal, sky-exposed plane**. To compare
fairly, the twin pixel should sit on a surface that resembles that. The first
attempt landed on a **dome** (curved/tilted) a few metres from the sensor — usable
as a first test, but flagged.

## How to judge the current (dome) extraction — DON'T gate on R² alone

A tilted/curved facet can still post a decent R² because the linear fit absorbs a
constant tilt factor into its slope. Judge instead on all three:

1. **Elevation-bin consistency** (`pyranometer_validation_summary.csv`, the
   `elev_10_20 / elev_20_40 / elev_40_91` rows): a good horizontal pixel is roughly
   uniform across bins. A dome facet degrades in some bins (it doesn't face those
   sun angles). Inconsistent bins → re-run.
2. **MBE (bias):** a tilted facet shows a systematic offset even with high R².
   Large |MBE| with good R² is the dome signature → re-run.
3. **Head-to-head vs CAMS:** if twin-vs-pyranometer RMSE is *worse* than
   CAMS-vs-pyranometer, the tilt is hurting → re-run. If twin ≥ CAMS, keep it.

Keep the dome pixel only if: bins consistent **and** |MBE| small **and** twin ≥ CAMS.

## If re-running — picking a better pixel

- **Prefer a flat roof section** on the sensor's building (or the flattest sky-open
  patch nearby). Horizontal beats exact-location.
- **Use View → Illuminance to confirm flatness:** a horizontal surface renders as a
  near-**uniform** colour. The dome showed a **radial rainbow gradient** (blue→green→
  red around the curve) — that gradient *is* the tilt; avoid it.
- **Avoid:** dome/curved roofs, edges/parapets, anything with trees or taller
  structures breaking the sky view (the small park beside the sensor is why the exact
  spot is hard — pick a cleaner sky-exposed surface even if slightly offset).
- **Sky exposure matters more than the few-metre offset:** a horizontal offset of a
  few metres barely changes sun geometry; matching horizon/sky-exposure to the real
  sensor matters far more.
- Optionally sample 2–3 candidate pixels and compare — the most horizontal, lowest-MBE,
  most bin-consistent one wins.

## Re-running is cheap

The schedule already exists (`schedule_Location_Thissio.csv`, ~538 renders). To
re-extract: set the new `ROOF_PX` in `production_sweep_gui.py`, **delete the old
`lux_Location_Thissio.csv`** (so checkpoint/resume starts fresh), and re-run. ~1–2 h.
