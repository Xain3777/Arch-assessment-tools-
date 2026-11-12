# Deliverable C — Development roadmap

Status legend: ✅ implemented and tested · 🟡 implemented, limited testing · ⬜ planned

## Phase 1–4 — MVP (this delivery)

| Capability | Status | Notes |
|---|---|---|
| Page classification raster / vector / hybrid / empty | ✅ | `archvectra analyze` |
| Native scan extraction (no resampling) / render fallback | ✅ | |
| Direct vector extraction with style (colour, width, dashes), fills, curves, text | ✅ | real 37 k-item sheet |
| Hybrid pages (scan + vectors merged, deskew disabled) | 🟡 | code path exists; no real hybrid sample tested |
| Deskew, denoise, Otsu/adaptive threshold, speck removal, optional closing | ✅ | |
| Solid walls H/V + diagonal, thickness from distance transform | ✅ | |
| Thin lines, arcs, free curves (skeleton graph) | ✅ | |
| Columns, solid regions | ✅ | |
| Angle snap, collinear merge, L/T snapping, thickness families | ✅ | |
| Openings: door (arc/leaf), window (glazing), unclassified + flag | ✅ | |
| Double-line (unfilled) wall pairing | 🟡 | relabels only; centreline not yet derived |
| Rooms (polygonize) and areas | ✅ | |
| Scale: 1:N, known distance, consistency warning | ✅ | |
| Clean vector PDF with layers, SVG, DXF (units, layers, XDATA), review PDF | ✅ | |
| DWG via ODA File Converter | 🟡 | code path; ODA not installed here → untested |
| Validation: ink P/R/F1, chamfer, overlay, comparison, ground-truth metrics | ✅ | |
| AutoLISP commands | 🟡 | written; **not run in AutoCAD in this environment** |

## Phase 5 — Architectural enhancements (next)

1. **Dimension-based scale** — harvest numeric text (vector PDFs: text spans; scans: Tesseract on
   annotation blobs), pair with parallel dimension lines + ticks, estimate scale by consensus; report
   as a *suggestion* with residuals, never auto-apply silently.
2. **Scale-bar detection** — alternating filled blocks + numeric labels.
3. **Double-line walls → centrelines** with thickness, joined into the same wall graph as solid walls.
4. **Dashed / dash-dot line linking** in scans (collinear dash chains with periodic gaps).
5. **Hatch recognition** — keep hatches as HATCH entities instead of outline polygons.
6. **Door swing direction and leaf width checks**; double doors; sliding doors.
7. **Stairs, sanitary and furniture symbols** — template matching first; learned detector only if a
   labelled set shows a gain (evaluate DeepLSD/YOLO-class detectors on MLStructFP/own data).
8. **Perspective correction** for photographed sheets (four-corner/border detection).
9. **Multi-page** batch processing and title-block detection.
10. Map uncertain geometry onto an explicit **review queue** (JSON) consumed by the GUI.

## Phase 6 — AutoCAD integration

* Run `archvectra.lsp` in AutoCAD on the demo DXF; fix any dialect issues (AutoCAD LT ≥ 2024 supports
  AutoLISP; older LT does not).
* Optional DWG out via ODA; optional .NET plug-in only if AutoLISP proves too limited.

## Phase 7 — Application interface

* PySide6 desktop app: file picker, parameter panel (from `Config`), side-by-side source/vector view
  with the overlay, flag list with "accept / delete / redraw" tools, re-export.
* Package with PyInstaller (Windows), bundle optional potrace.

## Explicitly out of scope until evidence supports it

* Deep-learning segmentation as a default path.
* Automatic "completion" of walls across gaps larger than the scan-break tolerance.
