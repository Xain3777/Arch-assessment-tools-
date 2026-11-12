# AutoCAD integration

`archvectra.lsp` adds commands that work on DXF files written by archvectra. The image processing stays in
Python; AutoLISP is used only to import, organise, review and check.

| Command | Purpose |
|---|---|
| `ARCHVECTRA-IMPORT` | Insert an archvectra DXF (exploded) at 0,0, apply layer standards, zoom extents |
| `ARCHVECTRA-LAYERS` | Colours, lineweights, no-plot for reference layers (`A-WALL-CNTR`, `A-OPEN`, `A-AREA-BDRY`, `Z-REVIEW`) |
| `ARCHVECTRA-REVIEW` | Zoom to each `Z-REVIEW` flag, print its severity/message, optionally delete it |
| `ARCHVECTRA-LOWCONF` | Select entities whose `ARCHVECTRA` XDATA confidence is below a threshold |
| `ARCHVECTRA-WALLS` | List wall centrelines with length and measured thickness |
| `ARCHVECTRA-CHECKDIM` | Pick two points, enter the expected dimension, report deviation (>1 % warns) |
| `ARCHVECTRA-CLEAN` | `-OVERKILL` on linework layers |

Load: `APPLOAD` → `archvectra.lsp` (add to the Startup Suite to load automatically).

**Status:** written against documented AutoLISP/Visual LISP functions; **not executed in AutoCAD
during development** (no AutoCAD in the build environment). Test on a copy first. AutoCAD LT supports
AutoLISP from LT 2024.

XDATA layout written by archvectra (application `ARCHVECTRA`): `(1000 . "kind=…")`, then numeric values
as `(1000 . "confidence") (1040 . 0.93)`, `(1000 . "thickness") (1040 . 250.0)`, and strings as
`(1000 . "source=raster-wall-h")`, `(1000 . "severity=warning")`, `(1000 . "message=…")`.
