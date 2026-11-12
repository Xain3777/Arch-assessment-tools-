# ArchVectra for AutoCAD — install and use

ArchVectra turns a scanned or vector PDF plan into clean, layered AutoCAD geometry, run from
AutoCAD's command line. The image processing runs in a separate engine (`archvectra.exe`); the LISP
file starts it, waits, and inserts the result into your drawing.

## Install (once per PC)

1. Get the **ArchVectra-windows** package:
   * GitHub → repository → **Actions** → "ArchVectra Windows build" → latest run → Artifacts.
     It contains `engine\archvectra.exe`, `archvectra.lsp`, this file and `default.toml`.
   * or build it yourself: `pip install -e . pyinstaller` then `packaging\build_windows.bat`.
2. Unzip it to a permanent folder, e.g. `C:\ArchVectra\`. Keep the `engine` folder complete.
3. In AutoCAD:
   * `APPLOAD` → select `C:\ArchVectra\archvectra.lsp` → **Load**.
     To load it every time: in APPLOAD, **Startup Suite → Contents → Add**.
   * Run `ARCHVECTRA-SETUP` and select `C:\ArchVectra\engine\archvectra.exe` (remembered in your
     AutoCAD profile).
4. If AutoCAD warns about loading an executable or LISP from an untrusted location, add
   `C:\ArchVectra` to **Options → Files → Trusted Locations** (`TRUSTEDPATHS`).

Requirements: Windows, full AutoCAD or AutoCAD LT 2024 and later (AutoLISP with ActiveX). Set the
drawing units to millimetres (`UNITS`) so calibrated output comes in at real size.

## Use

| Command | What happens |
|---|---|
| `ARCHVECTRA` | Pick a PDF → page number → scale N for 1:N (0 = unknown) → wait → pick an insertion point. Clean walls, doors, windows, lines and text outlines appear on `A-*` layers; a summary prints on the command line. |
| `ARCHVECTRA-UNDERLAY` | *(experimental)* Select a PDF already attached with `PDFATTACH`; the result is placed exactly over it, at the underlay's position and size. Unclip the underlay first. |
| `ARCHVECTRA-REVIEW` | Zooms to each red `Z-REVIEW` circle and explains it (unclassified opening, short gap, untraced ink …). Delete the flag once checked. |
| `ARCHVECTRA-REPORT` | Opens the review PDF (reconstruction drawn over the source). |
| `ARCHVECTRA-LOWCONF` | Selects geometry with low confidence for checking. |
| `ARCHVECTRA-WALLS` | Lists walls with length and measured thickness. |
| `ARCHVECTRA-CHECKDIM` | Pick two points, type the true dimension → shows the error in %. |
| `ARCHVECTRA-IMPORT`, `-LAYERS`, `-CLEAN` | Insert an existing result DXF, re-apply layer standards, OVERKILL linework. |

Results are also saved next to the PDF in `<name>_archvectra\` (clean PDF, DXF, SVG, review PDF,
comparison image, report).

## Notes and limits

* Without a scale (answer 0) the geometry is in **sheet millimetres**, not real size — the summary
  says "NOT calibrated".
* Processing takes a few seconds for an A4 scan and up to a minute for a large sheet; AutoCAD waits
  during that time.
* **Status:** the engine is tested; the LISP was written against documented AutoLISP/ActiveX
  functions and checked for structure, but has **not yet been run inside AutoCAD**. Please report
  the exact command-line message if a step fails.
