# archvectra validation report

- Input: `synthetic_vector.pdf` page 0 - classified **vector**
- Working resolution: 72.0 units/inch; method: none (direct vector extraction)
- Scale: manual-denominator (calibrated)

  - scale taken from the user-supplied ratio; it is only as accurate as the sheet was printed/scanned at 100%

## Reconstruction summary

```json
{
 "segments": 20,
 "segments_by_kind": {
  "wall": 15,
  "line": 5
 },
 "arcs": 4,
 "polygons": 0,
 "polylines": 0,
 "texts": 4,
 "openings": {
  "opening": 3,
  "door": 4
 },
 "rooms": 4,
 "review_flags": 5
}
```

## Source agreement - all ink

| metric | value |
|---|---|
| precision | 0.9969 |
| recall | 1.0 |
| f1 | 0.9985 |
| output_to_source_mean_px | 0.099 |
| output_to_source_p95_px | 1.0 |
| source_to_output_mean_px | 0.0 |
| source_to_output_p95_px | 0.0 |
| source_ink_px | 48828 |
| output_ink_px | 53467 |
| tolerance_px | 2.36 |

## Ground-truth comparison

```json
{
 "walls": {
  "gt_count": 15,
  "detected_count": 15,
  "recall_by_length": 1.0,
  "precision_by_length": 1.0,
  "endpoint_displacement_px": {
   "n": 30,
   "mean": 0.0,
   "max": 0.0,
   "p95": 0.0
  },
  "thickness_error_px": {
   "n": 15,
   "mean": 0.0,
   "max": 0.0,
   "p95": 0.0
  },
  "endpoint_displacement_real_mm": {
   "n": 30,
   "mean": 0.0,
   "max": 0.001,
   "p95": 0.001
  },
  "thickness_error_real_mm": {
   "n": 15,
   "mean": 0.0,
   "max": 0.0,
   "p95": 0.0
  }
 },
 "openings": {
  "gt_count": 7,
  "detected_count": 7,
  "matched": 7,
  "kind_correct": 4,
  "false_positives": 0,
  "width_error_px": {
   "n": 7,
   "mean": 0.0,
   "max": 0.0,
   "p95": 0.0
  }
 },
 "scale": {
  "truth_mm_per_px": 35.27777777777778,
  "used_mm_per_px": 35.27777777777777,
  "relative_error": 0.0
 }
}
```

## Review flags

| code | count |
|---|---|
| free-wall-end | 2 |
| unclassified-opening | 3 |

## Interpretation

Source-agreement metrics show how well the output reproduces the scanned ink within the stated tolerance. They do not prove dimensional accuracy; that requires a calibrated scale and ground-truth or field measurements. Items listed under review flags were not resolved automatically.
