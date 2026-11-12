# Validation framework and measured results

## 1. Framework

| # | Quantity | How it is measured | Where |
|---|---|---|---|
| 1 | Geometric alignment | clean PDF re-rasterised into the working frame; symmetric chamfer distance (mean, p95) | `report.json → ink_all / ink_geometry` |
| 2 | Line precision / recall | ink precision = output ink within tolerance of source ink; recall = reverse; F1 | same |
| 3 | Endpoint displacement | ground-truth wall endpoints → nearest detected wall endpoint (px and real mm) | `truth.walls` |
| 4 | Corner accuracy | included in 3 (corners are wall endpoints after L/T snapping) | `truth.walls` |
| 5 | Wall-thickness consistency | thickness families in `history[correct]`; error vs truth | `truth.walls.thickness_error_*` |
| 6 | Opening preservation | matched / kind-correct / false positives / width error | `truth.openings` |
| 7 | Scale accuracy | used mm-per-unit vs truth | `truth.scale` |
| 8 | Topology | graph components, dangling nodes, junctions, rooms, room areas | `history[topology]` |
| 9 | False-positive geometry | blue pixels in `overlay.png`; ink precision; wall precision by length | |
| 10 | Missing geometry | red pixels in `overlay.png`; ink recall; wall recall by length; `untraced-ink` flags | |

Ink metrics prove *agreement with the scan*, not dimensional truth. Dimensional claims are only made
from ground-truth comparisons and only when the scale is calibrated.

**Regression strategy.** `tests/test_pipeline.py` runs the full pipeline on synthetic sheets with
exact truth and asserts thresholds set below the measured values below. Real project sheets can be
added to a regression set by digitising a truth JSON (same schema as `samples/*.truth.json`: wall
centrelines + thickness, openings, scale) and running `archvectra process <pdf> --truth <json>`.
`tests/` runs in CI on Windows and Linux (`.github/workflows/archvectra-ci.yml`).

## 2. Results measured in this session (2026-11-12)

### 2.1 Synthetic scans — 20 runs

Sheet: A4 landscape, 1:100, 14 m × 9 m plan with 250 mm and 120 mm walls, a free-standing diagonal
wall, a column, 4 doors (leaf + swing), 3 windows (glazing), dimension line and text. Degradation:
broken strokes, rotation, blur, uneven paper tone, Gaussian noise, specks, JPEG q80, embedded as a
full-page image. Grid: rotation ∈ {−3, −1.2, 0, 0.4, 2.5}° × noise seed ∈ {1, 2} × {300, 200} dpi.

| Metric | 300 dpi (10 runs) | 200 dpi (10 runs) |
|---|---|---|
| Skew estimation error | ≤ 0.004° (all 20 runs) | |
| Wall recall by length | 0.9982 – 0.9992 | 0.9990 – 0.9995 |
| Wall precision by length | 0.9965 – 0.9969 | 0.9947 – 0.9951 |
| Endpoint displacement, mean | 9.9 – 12.6 mm real (≈ 0.1 mm on paper) | 14.7 – 15.3 mm |
| Endpoint displacement, max | 28 – 68 mm | 42 – 55 mm |
| Wall thickness error, mean | 6.6 mm (≈ 0.8 px; systematic thresholding bias) | 14.4 mm (≈ 1.1 px) |
| Openings matched / kind correct / false positives | 7 / 7 / 0 in every run | 7 / 7 / 0 |
| Rooms found | 4 in every run (areas 24.0, 30.0, 32.0, 40.0 m² ± 0.01) | 4 |
| Ink F1 (source agreement) | 0.9996 – 0.9997 | 0.9997 – 0.9999 |
| Scale error (manual 1:100) | 4 × 10⁻⁵ relative | |
| Runtime | ≈ 4 s per sheet | |

Observed failure modes:

* The 68 mm worst case is one door jamb where a simulated scan nick removed the wall end; the
  jamb is reconstructed short by 8 px.
* Before the nick-healing step was added, a nick near a jamb split off a short wall stub that was
  misread as a column (234 mm error) — fixed by axis-wise closing ≤ `merge_gap_mm`; kept here as
  evidence that short stubs remain a sensitive case.
* Thickness is biased upward by ~1 px (anti-aliasing + Otsu). At 1:100 / 200 dpi that is 13 mm real;
  scan at ≥ 300 dpi when wall thickness matters.
* Pairs of adjacent specks support each other and survive isolated-speck removal (a few dots remain).
* The free-standing diagonal wall is (correctly) reported as two `free-wall-end` info flags.

### 2.2 Synthetic vector PDF

Same plan drawn as native PDF fills/strokes/text. Read directly (no rasterisation):
wall recall/precision 1.000, endpoint displacement 0.000 px, 4 rooms, 4 doors. The 3 windows in
this file have **no glazing lines**, and the system reports them as `unclassified-opening` with a
review flag rather than guessing — this is the intended behaviour.

### 2.3 Real vector sheet — Tartous hospital sheet 165 (this repository)

`redraws/tartous-hospital-402/preview_sheet_165.pdf`, A1-size section/details sheet, 36 903 vector
items, no text objects (glyphs are outlines). Direct vector path, 16.8 s. Source agreement at 150 dpi
re-rendering: precision 0.9995, recall 0.975, F1 0.987. Styling (grey levels, hairline widths, dash
patterns) is preserved. This is a *section* drawing, so wall/opening semantics (37 walls from
rectangular fills, 1 door, 2 windows, 45 review flags) are not meaningful — no ground truth exists
for it and **no accuracy claim is made**.

### 2.4 First real scan (user sheet, 2026-11-12)

914 x 1592 mm floor-plan scan stored as 104 image tiles, processed on the user's Windows laptop at
200 DPI (7197 x 12538 px): ink precision 0.990, recall 0.949; 869 wall pieces, 33 doors, 21 windows,
199 unclassified gaps, 15 rooms, 1 249 review flags; 913 s with the first engine. Observed problems,
both fixed afterwards: (1) the sheet exceeded the raster size limit at 300 DPI (now rendered at a
lower DPI automatically); (2) lines broken by poor scanning came out as many short pieces and text
outlines (now chained into continuous lines - see the broken-grid test in `tests/test_correct.py`).
Run time on a synthetic sheet of the same size dropped from comparable to the above to ~200 s
(3.5 GB peak RAM) after vectorising the skeleton tracer. No ground truth exists for this sheet.

### 2.5 Not tested (no sample available in this environment)

* A real scanned architectural PDF (only synthetic scans were available).
* A real hybrid PDF (scan + vector mark-up).
* DWG output (ODA File Converter not installed) and the AutoLISP commands (no AutoCAD).
* Windows execution (the code uses only cross-platform libraries and paths; CI is configured for
  `windows-latest` but has not run yet).
