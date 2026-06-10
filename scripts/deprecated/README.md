# Deprecated / superseded scripts

These are kept **for provenance** — they document how the method evolved and why
the final pipeline looks the way it does. **Do not use them for the paper runs.**
The live equivalents are in `scripts/`.

| Deprecated script | Why deprecated | Use instead |
|---|---|---|
| `production_sweep.py` | Headless extractor — the MDL dynamic sky does **not** light the scene headlessly (renders only ambient ~1100 lux, no sun disk). | `production_sweep_gui.py` (runs in the Isaac GUI Script Editor, where the sky lights correctly) |
| `measure_convergence.py` | Headless rt_subframes convergence probe — same headless lighting problem, and rt_subframes is not the convergence knob. | `benchmark_convergence_gui_v2.py` |
| `benchmark_convergence_gui.py` | v1 swept **rt_subframes**, which doesn't control convergence in interactive PT (render time stayed flat; result flagged INVALID). | `benchmark_convergence_gui_v2.py` (sweeps `/rtx/pathtracing/totalSpp`) |
| `inspect_and_test_sun.py` | Drove the sun by **rotating a DistantLight** — but the scene's sun is the Sun Study/MDL sky, not that light. | `set_environment_time.py` (drives the Sun Study time) |
| `live_illuminance_check.py` | Live check via the standalone launcher; superseded by the async Script-Editor version. | `live_check_script_editor.py` |
| `probe_illuminance_aov.py` | Step-A probe that resolved the AOV token. **Outcome: token = `PtIlluminance`** (now hard-coded in `capture.py`). Job done. | n/a (resolved) |
| `run_probe_standalone.py` | Standalone launcher for the Step-A probe. | n/a (resolved) |
| `diag_intensity.py` | One-off headless diagnostic — found the headless frame was flat (~1100 lux, no shadows). | n/a (diagnosis recorded) |
| `diag_sun_intensity.py` | One-off — confirmed bumping the existing DistantLight did nothing headless. | n/a |
| `diag_add_light.py` | One-off — tested adding our own light headless (pivot exploration). | n/a |
| `sprint0_sweep.py` | 22-instant proof-of-concept sweep (summer+winter day, 1 location). Validated the method (R²≈0.98). | `production_sweep_gui.py` (full schedules) |

**Key resolved facts that came out of these** (now baked into the live pipeline):
the illuminance AOV token is `PtIlluminance`; photopic lux = 0.2126·R + 0.7152·G +
0.0722·B; production must run in the **GUI** (headless sky is unlit); the convergence
knob is **`totalSpp`** (default 512 → already converged).
