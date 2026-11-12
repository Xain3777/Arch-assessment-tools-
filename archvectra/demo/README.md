# Deliverable E — demonstration outputs

Generated on 2026-11-12 with `archvectra 0.1.0` by the commands below. Everything listed here was
**actually generated and inspected**; metrics come from each folder's `report.json`.

| Folder | Input | Kind | Generated | Key results |
|---|---|---|---|---|
| `synthetic_scan/` | `samples/synthetic_scan.pdf` (simulated scan: 0.8° skew, noise, specks, broken strokes, JPEG) | raster | clean PDF, SVG, DXF, review PDF, comparison, overlay, class mask, report | walls recall 0.999 (by length); 7/7 openings found and classified (4 doors, 3 windows), 0 false positives; 4 rooms; ink F1 0.9997; 2.9 s |
| `synthetic_vector/` | `samples/synthetic_vector.pdf` (same plan as native vectors + text) | vector | clean PDF, SVG, DXF, review PDF, comparison, overlay, report | walls exact (0.000 px); 4 doors; 3 windows **left unclassified and flagged** because the source has no glazing lines; text re-emitted as text |
| `tartous_sheet_165/` | `../redraws/tartous-hospital-402/preview_sheet_165.pdf` (real CAD section sheet, 36 903 vector items) | vector | clean PDF, comparison, report (DXF 35 MB / SVG 7 MB not committed — regenerate with the command below) | ink precision 0.9995, recall 0.975, F1 0.987; styling kept; semantics not meaningful on a section, no accuracy claim |

Not demonstrated: a real scanned plan (none available), DWG output (ODA converter not installed),
AutoLISP in AutoCAD (not available).

Reproduce (from `vectorizer/`):

```
archvectra synth samples
archvectra process samples/synthetic_scan.pdf   -o out/synthetic_scan   --scale 100 --truth samples/synthetic_scan.truth.json
archvectra process samples/synthetic_vector.pdf -o out/synthetic_vector --scale 100 --truth samples/synthetic_vector.truth.json
archvectra process ../redraws/tartous-hospital-402/preview_sheet_165.pdf -o out/tartous_sheet_165
```

`comparison.png` shows original | reconstruction | overlay (grey = match, red = source ink missing
from the output, blue = output ink not in the source). The review PDF shows the reconstruction in
colour over the (deskewed) source with openings and review flags labelled.
