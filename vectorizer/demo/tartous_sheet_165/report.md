# archvec validation report

- Input: `preview_sheet_165.pdf` page 0 - classified **vector**
- Working resolution: 72.0 units/inch; method: none (direct vector extraction)
- Scale: none (NOT calibrated)

  - no scale information: geometry is exported in sheet millimetres and is NOT dimensionally calibrated

## Reconstruction summary

```json
{
 "segments": 5220,
 "segments_by_kind": {
  "wall": 37,
  "wall-edge": 508,
  "line": 4675
 },
 "arcs": 11,
 "polygons": 2888,
 "polylines": 0,
 "texts": 0,
 "openings": {
  "door": 1,
  "window": 2
 },
 "rooms": 2,
 "review_flags": 45
}
```

## Source agreement - all ink

| metric | value |
|---|---|
| precision | 0.9995 |
| recall | 0.9748 |
| f1 | 0.987 |
| output_to_source_mean_px | 0.027 |
| output_to_source_p95_px | 0.0 |
| source_to_output_mean_px | 0.427 |
| source_to_output_p95_px | 0.0 |
| source_ink_px | 338956 |
| output_ink_px | 336972 |
| tolerance_px | 2.36 |

## Review flags

| code | count |
|---|---|
| free-wall-end | 40 |
| short-gap | 5 |

## Interpretation

Source-agreement metrics show how well the output reproduces the scanned ink within the stated tolerance. They do not prove dimensional accuracy; that requires a calibrated scale and ground-truth or field measurements. Items listed under review flags were not resolved automatically.
