# archvectra validation report

- Input: `synthetic_scan.pdf` page 0 - classified **raster**
- Working resolution: 300.0 units/inch; method: native-image
- Scale: manual-denominator (calibrated)

  - scale taken from the user-supplied ratio; it is only as accurate as the sheet was printed/scanned at 100%

## Reconstruction summary

```json
{
 "segments": 30,
 "segments_by_kind": {
  "wall": 15,
  "line": 15
 },
 "arcs": 4,
 "polygons": 41,
 "polylines": 0,
 "texts": 0,
 "openings": {
  "window": 3,
  "door": 4
 },
 "rooms": 4,
 "review_flags": 2
}
```

## Source agreement - all ink

| metric | value |
|---|---|
| precision | 1.0 |
| recall | 0.9994 |
| f1 | 0.9997 |
| output_to_source_mean_px | 0.136 |
| output_to_source_p95_px | 1.0 |
| source_to_output_mean_px | 0.08 |
| source_to_output_p95_px | 1.0 |
| source_ink_px | 216671 |
| output_ink_px | 227365 |
| tolerance_px | 4.72 |

## Source agreement - geometry only

| metric | value |
|---|---|
| precision | 1.0 |
| recall | 0.9994 |
| f1 | 0.9997 |
| output_to_source_mean_px | 0.037 |
| output_to_source_p95_px | 0.0 |
| source_to_output_mean_px | 0.056 |
| source_to_output_p95_px | 0.0 |
| source_ink_px | 208518 |
| output_ink_px | 206412 |
| tolerance_px | 4.72 |

## Ground-truth comparison

```json
{
 "walls": {
  "gt_count": 15,
  "detected_count": 15,
  "recall_by_length": 0.9991,
  "precision_by_length": 0.9968,
  "endpoint_displacement_px": {
   "n": 30,
   "mean": 1.203,
   "max": 3.323,
   "p95": 3.006
  },
  "thickness_error_px": {
   "n": 15,
   "mean": 0.787,
   "max": 0.932,
   "p95": 0.932
  },
  "endpoint_displacement_real_mm": {
   "n": 30,
   "mean": 10.189,
   "max": 28.132,
   "p95": 25.45
  },
  "thickness_error_real_mm": {
   "n": 15,
   "mean": 6.662,
   "max": 7.892,
   "p95": 7.892
  }
 },
 "openings": {
  "gt_count": 7,
  "detected_count": 7,
  "matched": 7,
  "kind_correct": 7,
  "false_positives": 0,
  "width_error_px": {
   "n": 7,
   "mean": 3.101,
   "max": 5.165,
   "p95": 5.165
  }
 },
 "scale": {
  "truth_mm_per_px": 8.466666666666667,
  "used_mm_per_px": 8.466313564020703,
  "relative_error": 4.2e-05
 }
}
```

## Review flags

| code | count |
|---|---|
| free-wall-end | 2 |

## Interpretation

Source-agreement metrics show how well the output reproduces the scanned ink within the stated tolerance. They do not prove dimensional accuracy; that requires a calibrated scale and ground-truth or field measurements. Items listed under review flags were not resolved automatically.
