# AutoCAD integration

* **[INSTALL.md](INSTALL.md)** — install and use ArchVectra inside AutoCAD (start here).
* `archvectra.lsp` — commands `ARCHVECTRA`, `ARCHVECTRA-UNDERLAY`, `ARCHVECTRA-SETUP`, `-REVIEW`,
  `-REPORT`, `-LOWCONF`, `-WALLS`, `-CHECKDIM`, `-IMPORT`, `-LAYERS`, `-CLEAN`.

How it fits together: AutoLISP cannot read PDFs or process images, so `ARCHVECTRA` starts the
engine `archvectra.exe` hidden (`WScript.Shell.Run`, waiting for the exit code), then inserts
`<name>_archvectra\02_vector\<name>_clean.dxf` exploded into the current drawing and prints
`summary.txt`. `ARCHVECTRA-UNDERLAY` runs the engine without a scale (sheet millimetres, origin at the
page's lower-left corner) and inserts at the underlay's insertion point, scaled by underlay width ÷
sheet width.

XDATA written on entities (application `ARCHVECTRA`): `(1000 . "kind=…")`, numbers as
`(1000 . "confidence") (1040 . 0.93)` / `(1000 . "thickness") (1040 . 250.0)`, strings as
`(1000 . "source=…")`, `(1000 . "severity=…")`, `(1000 . "message=…")`.

**Status:** not yet executed in AutoCAD (none available during development).
