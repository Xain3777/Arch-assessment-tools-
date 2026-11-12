# AutoCAD integration

`archvec.lsp` adds commands that work on DXF files written by archvec. The image processing stays in
Python; AutoLISP is used only to import, organise, review and check.

| Command | Purpose |
|---|---|
| `ARCHVEC-IMPORT` | Insert an archvec DXF (exploded) at 0,0, apply layer standards, zoom extents |
| `ARCHVEC-LAYERS` | Colours, lineweights, no-plot for reference layers (`A-WALL-CNTR`, `A-OPEN`, `A-AREA-BDRY`, `Z-REVIEW`) |
| `ARCHVEC-REVIEW` | Zoom to each `Z-REVIEW` flag, print its severity/message, optionally delete it |
| `ARCHVEC-LOWCONF` | Select entities whose `ARCHVEC` XDATA confidence is below a threshold |
| `ARCHVEC-WALLS` | List wall centrelines with length and measured thickness |
| `ARCHVEC-CHECKDIM` | Pick two points, enter the expected dimension, report deviation (>1 % warns) |
| `ARCHVEC-CLEAN` | `-OVERKILL` on linework layers |

Load: `APPLOAD` → `archvec.lsp` (add to the Startup Suite to load automatically).

**Status:** written against documented AutoLISP/Visual LISP functions; **not executed in AutoCAD
during development** (no AutoCAD in the build environment). Test on a copy first. AutoCAD LT supports
AutoLISP from LT 2024.

XDATA layout written by archvec (application `ARCHVEC`): `(1000 . "kind=…")`, then numeric values
as `(1000 . "confidence") (1040 . 0.93)`, `(1000 . "thickness") (1040 . 250.0)`, and strings as
`(1000 . "source=raster-wall-h")`, `(1000 . "severity=warning")`, `(1000 . "message=…")`.
