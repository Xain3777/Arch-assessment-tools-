# archvec — architectural PDF vectorisation

Converts scanned, vector or hybrid architectural PDFs into a **clean vector PDF**, **layered DXF**
and **SVG**, with a review PDF, an overlay comparison and a validation report. Geometry is extracted
with established open-source libraries (OpenCV, scikit-image, Shapely, NetworkX, PyMuPDF, ezdxf,
optional Potrace) and corrected conservatively: gaps are bridged only up to a scan-break tolerance,
openings are never filled, and uncertain results are flagged for review.

| Document | Content |
|---|---|
| [docs/RESEARCH.md](docs/RESEARCH.md) | Deliverable A — open-source comparison, licences, ranking |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Deliverable B — pipeline, data model, design choices |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Deliverable C — what is done, what is next |
| [docs/VALIDATION.md](docs/VALIDATION.md) | Validation framework and **measured** results |
| [demo/](demo/) | Deliverable E — generated outputs |
| [autocad/](autocad/) | AutoLISP commands for the DXF output |

## What it does (MVP)

1. Classifies each page as raster / vector / hybrid (`archvec analyze`).
2. Vector pages: reads paths, fills, curves and text directly — no rasterisation, styling kept.
3. Scanned pages: uses the embedded scan at its native resolution, deskews (LSD), denoises,
   binarises (Otsu or adaptive), removes specks.
4. Extracts solid walls (centreline + thickness), diagonal walls, columns, thin lines, arcs, curves;
   separates text/symbols, which are kept as outlines.
5. Snaps near-orthogonal lines, merges collinear pieces across scan breaks, closes L/T corners,
   groups wall thicknesses into families.
6. Finds openings from free wall ends and classifies them (door: swing arc or leaf; window: glazing
   lines; otherwise *unclassified* + review flag). Reconstructs rooms and areas.
7. Exports clean PDF (page-identical size, toggleable layers), SVG, DXF (real-world mm when calibrated,
   layers, XDATA with confidence), review PDF, overlay/comparison images, JSON + Markdown report.

## Installation (Windows)

Requires 64-bit **Python 3.11–3.13** from [python.org](https://www.python.org/downloads/windows/)
("Add python.exe to PATH" ticked).

```powershell
cd Arch-assessment-tools-\vectorizer
py -3 -m venv .venv
.venv\Scripts\Activate.ps1          # cmd.exe: .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -e .[dev]
python -m pytest -q                  # 43 tests
```

All dependencies are pip wheels; no compiler is needed. Optional extras:

* **Potrace** (smoother text/symbol outlines): download the Windows build from
  <https://potrace.sourceforge.net/#downloading>, put `potrace.exe` on `PATH`. Without it OpenCV
  contours are used automatically.
* **DWG output**: install the ODA File Converter, then `--set export.dwg=true`. Otherwise open the
  DXF in AutoCAD and `SAVEAS` DWG.

Linux/macOS: the same commands with `source .venv/bin/activate`.

## Usage

```powershell
archvec analyze plan.pdf
archvec process plan.pdf -o out\plan --scale 100
archvec process plan.pdf -o out\plan --known-distance 531.5 413.4 2185.0 413.4 14000   # x1 y1 x2 y2 (px) mm
archvec process plan.pdf -c config\scale_1-50.toml --set correct.snap_distance_mm=2.0
archvec synth samples                                                        # test sheets + truth
archvec process samples\synthetic_scan.pdf -o out\demo --scale 100 --truth samples\synthetic_scan.truth.json
```

`python -m archvec ...` works without the console script. Known-distance points are pixel
coordinates in `01_raster/preprocessed.png` (the working image).

### Output layout

```
out/plan/
  00_source/      untouched copy of the input PDF
  01_raster/      source.png, preprocessed.png, binary.png, classes.png   (raster inputs only)
  02_vector/      <name>_clean.pdf  <name>_clean.svg  <name>_clean.dxf  <name>_review.pdf  model.json
  03_validation/  comparison.png  overlay.png  report.json  report.md
  manifest.json   configuration, processing history, versions, input SHA-256
  run.log
```

### DXF layers

`A-WALL` (solid wall outlines + hatch), `A-WALL-CNTR` (centrelines; XDATA thickness/confidence),
`A-COLS`, `A-SOLID`, `A-DETL`, `A-DETL-ARC`, `A-DOOR`, `A-GLAZ`, `A-OPEN` (opening chords, off),
`A-AREA-BDRY` (room candidates, off), `A-ANNO` (text/symbol outlines), `A-ANNO-TEXT` (real text from
vector PDFs), `Z-REVIEW` (flags with message). Units: `$INSUNITS=4` (mm) only when the scale is
calibrated; otherwise sheet millimetres with `$INSUNITS=0` and header note `ARCHVEC_UNITS`.

## Configuration

All parameters are in [config/default.toml](config/default.toml) (generated from
`src/archvec/config.py`). Lengths are **millimetres on the sheet**, converted to pixels with the
effective resolution, so the same file works at any DPI; scale them with the drawing scale (see
`config/scale_1-50.toml`). Key groups: rasterisation DPI, deskew, threshold, speck sizes; minimum
line length, wall thickness threshold, text size; angle tolerance, merge gap, snap distance,
opening range, thickness-family tolerance; scale; export line weights; validation tolerance.

## Known limitations

See [docs/ROADMAP.md](docs/ROADMAP.md) and [docs/VALIDATION.md §2.4](docs/VALIDATION.md). In short:
no scale-bar / dimension-text calibration yet (the drawing is reported as uncalibrated instead),
dashed lines in scans are kept as outlines rather than linked into lines, double-line walls are
labelled but not converted to centrelines, no perspective correction, single page per run, and
only synthetic scans have been tested.

## Licensing

archvec has **no licence chosen yet**. It depends on PyMuPDF (AGPL-3.0 or commercial), which
constrains distribution — see [docs/RESEARCH.md §3](docs/RESEARCH.md). Other dependencies are
Apache-2.0, BSD or MIT; Potrace (GPL-2.0) is optional and only run as a separate program.
