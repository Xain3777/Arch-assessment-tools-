# Deliverable B — Architecture

## 1. Principles

* **Evidence before beauty.** Geometry is moved, merged or relabelled only when the source supports
  it; gaps are never filled beyond the scan-break tolerance; every inferred element has a confidence
  and every unresolved one becomes a review flag.
* **Keep the best source.** Vector PDFs are read as vectors (no rasterisation). Scans are processed at
  their native pixel grid (embedded image) instead of being re-rendered.
* **Reversible.** The source file is copied untouched; preprocessing is logged; the deskew rotation
  is stored as an invertible affine matrix.
* **Small, local, Windows-first.** One Python package, no services, pure-pip dependencies (wheels
  exist for Windows). Potrace and the ODA converter are optional executables.

## 2. Pipeline

```
           ┌──────────── Stage A  pdf_input.py ────────────┐
 PDF ────► │ analyse page: vector items, images, coverage, │
           │ effective DPI, rotation → raster/vector/hybrid │
           └───────┬───────────────────────┬───────────────┘
        raster/hybrid                    vector
                │                          │  extract_vectors(): paths + style, curves, fills, text
   load_raster(): native image            │  _walls_from_fills(): rectangle fills → walls
   (or render at cfg DPI)                  │
                ▼                          │
   Stage B preprocess.py                   │
   LSD skew → rotate, median, Otsu/        │
   adaptive, speck removal, history        │
                ▼                          │
   Stage C extract.py                      │
   annotation split │ solid walls (directional morphology, │
   DT thickness, minAreaRect) │ thin lines (skeleton graph,│
   RDP, corner split, circle fit)          │
                └──────────┬───────────────┘
                           ▼
          Stage E correct.py   angle snap · collinear align/merge (≤ merge_gap) · thickness
                               families · L/T endpoint snapping (STRtree)
          Stage D semantics.py openings from free wall ends (door: arc/leaf, window: glazing,
                               else unclassified + flag) · double-line walls
          Stage G semantics.py topology: Shapely noding + polygonize → rooms; NetworkX graph
          (raster) residual ink → trace.py (potrace | contours) → annotation outlines
          Grid     grid.py + rectify.py + ocr.py   axes (dash-dot lines, column rows, bubbles) fitted by
                               least squares; columns (+ completion from the grid pattern); OCR of
                               dimension numbers and labels; scale by consensus; shear removal and
                               piecewise-linear rubber-sheeting to the written dimensions; snapping of
                               walls / columns / axes; numbers become text
          Stage F scale.py     manual 1:N, known distance, dimensions, consistency check
          Stage H export/      clean PDF (OCG layers) · SVG (layers) · DXF (layers, XDATA) ·
                               review PDF · optional DWG (ODA)
          Validation validate.py  re-render clean PDF → ink P/R, chamfer, overlay; ground truth
```

## 3. Data model (`model.py`)

All coordinates live in one **working frame** (raster pixels, or PDF points for vector input),
y down. `Drawing.px_to_pt` maps it to the original page so outputs keep the page geometry.

| Entity | Key fields |
|---|---|
| `Segment` | endpoints, `thickness`, `kind` (`wall` = centreline of a solid wall, `line`, `wall-edge`), layer, confidence, source method, attrs (joints, merged pieces, measured thickness, style) |
| `Arc` | centre, radius, start/end angle, thickness, layer |
| `Polygon` | exterior + holes (columns, solids, annotation outlines, PDF fills) |
| `Polyline` | free-form curves that are neither straight nor circular |
| `Text` | real text from vector PDFs (position, size, angle) |
| `Opening` | kind, jamb points on the wall axis, width, wall thickness, confidence, evidence |
| `ReviewFlag` | position, code, message, severity |
| `Scale` | sheet mm per unit (always known), real mm per unit (or `None`), source, notes |

The geometry graph is derived on demand (Shapely noding → NetworkX) rather than stored, so edits
to segments can never desynchronise it.

## 4. Why these components

| Need | Choice | Reason |
|---|---|---|
| PDF analysis/extraction | PyMuPDF | Only library giving drawings *with style*, text spans, image placement matrices and native image bytes in one API |
| Orthogonal walls | Directional morphology | Exact thickness and extents; immune to the double-edge problem of edge-based detectors |
| Thin lines/curves | Skeleton graph + RDP + circle fit | Handles any angle and arcs; junctions become graph nodes |
| Skew | LSD on long near-axis segments, length-weighted | Measured error < 0.01° on synthetic sheets |
| Tolerances | Paper millimetres → pixels | Same config works at any DPI; tied to drawing scale |
| Spatial queries | Shapely STRtree | 37 k-item sheet processed in ~16 s |
| PDF writing | Raw content streams + optional-content groups | Linear time; layers toggle in viewers |
| CAD | ezdxf R2010, ACI layers, XDATA `ARCHVECTRA` | Opens in AutoCAD/LibreCAD; AutoLISP can filter by confidence |
| Deep learning | **Not used** | No demonstrated advantage on the MVP scope; licence/GPU cost |

## 5. Module map

```
src/archvectra/
  config.py      dataclass config, TOML + --set overrides, mm↔px
  model.py       data model and CAD layer table
  pdf_input.py   Stage A
  preprocess.py  Stage B
  extract.py     Stage C
  correct.py     Stage E
  semantics.py   Stage D + G (openings, double-line walls, topology/rooms)
  scale.py       Stage F
  geometry.py    wall solids (union of buffered centrelines), rasterisation
  trace.py       annotation outline tracing (potrace | OpenCV)
  spatial.py     STRtree segment index
  export/        pdf.py, svg.py, dxf.py, common.py
  validate.py    metrics, overlay, comparison, report
  pipeline.py    orchestration, output layout, manifest, logging
  synthetic.py   synthetic sheets with exact ground truth
  cli.py         `archvectra analyze | process | synth`
autocad/archvectra.lsp   AutoLISP commands
```

## 6. Error handling and logging

* `PdfInputError`/`PipelineError` for user-facing problems (missing file, page out of range,
  encrypted PDF, empty page, raster too large); CLI exit code 2. Unexpected errors: exit code 3, full
  traceback in `run.log`.
* `run.log` per run; `manifest.json` stores configuration, processing history, versions, input
  SHA-256 and outputs, so every result is reproducible.

## 7. AutoCAD integration

The computer-vision pipeline stays in Python. AutoLISP (`autocad/archvectra.lsp`) works on the DXF:
import, layer standards, review navigation of `Z-REVIEW` flags, selection by `ARCHVECTRA` XDATA
confidence, wall-thickness and dimension checks. See `autocad/README.md`.
