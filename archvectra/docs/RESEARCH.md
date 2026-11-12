# Deliverable A — Open-source research report

Research date: **2026-11-12**. Repository status (language, licence as GitHub detects it, stars,
last push) was queried live from the GitHub search API in this session. Each row says how its
capabilities were established:

* **[code]** — repository cloned and source read in this session.
* **[tested]** — installed and run in this session.
* **[docs]** — taken from the project's README/documentation or prior knowledge, *not* verified
  by running it here. Treat as an assumption until tested.

## 1. Comparison table

| Project | Functionality | License | Maturity | Reusability | Limitations for architectural plans |
|---|---|---|---|---|---|
| [TheHyller/scan-vectorizer](https://github.com/TheHyller/scan-vectorizer) **[code]** | Windows GUI/CLI wrapper: Poppler `pdftoppm` → `mkbitmap` → `potrace` → SVG/PDF/DXF; Douglas-Peucker DXF simplification (ezdxf); optional Tesseract OCR text layer | MIT (repo `LICENSE`; GitHub shows NOASSERTION because GPL-2.0/Apache-2.0 texts of bundled tools are included) | 1 file (899 lines), 2★, last push 2026-06-19; PowerShell/Inno Setup packaging | Low as code (subprocess glue); useful reference for bundling potrace/Poppler/Tesseract on Windows | Outline tracing only: every stroke becomes a closed outline, not a CAD line; no deskew, no line/wall/opening semantics, no scale |
| [YImingZHANG615/floorplan-to-vector](https://github.com/YImingZHANG615/floorplan-to-vector) **[code]** | Agent skill + offline toolkit: wall baselines, thickness families, protected door gaps, door geometry, layered DXF/SVG/PDF, QA overlay; Windows py3.12 offline bundle; pytest + CI | MIT | ~3 k lines Python, 2★, last push 2026-10-15 | Medium: good ideas (thickness families, protected gaps, QA) — re-implemented here, not copied | **Does not read raw scans**: input is a same-canvas *semantic colour mask* (from another tool) or human-reviewed JSON baselines |
| [OSGeo/grass](https://github.com/OSGeo/grass) **[docs]** | GIS engine: `r.thin` + `r.to.vect type=line` (raster→vector lines), `v.clean` (snap, break, rmdupl, rmdangle), `v.generalize` | GPL-2.0-or-later (GitHub: NOASSERTION) | Very mature, 1.2 k★, pushed today; Windows via OSGeo4W | Low for an embedded desktop tool: heavy runtime, GIS location/projection model, GPL | The closest "ArcScan-like" open tool; no architectural semantics; output needs CAD conversion |
| [Potrace](https://potrace.sourceforge.net/) **[tested]** (1.16) | Bitmap → smooth vector outlines; backends SVG/PDF/DXF/**GeoJSON** | GPL-2.0 | Stable since 2019; Windows binaries | High **as an external program** (no linking ⇒ no licence contamination) | Outlines, not centrelines; curve fitting may round sharp CAD corners (`-a` controls it) |
| [opencv/opencv](https://github.com/opencv/opencv) **[tested]** (5.0.0) | Thresholding, morphology, connected components, contours, Hough, **LSD**, distance transform | Apache-2.0 | 91 k★, very active | High | General-purpose; no plan semantics |
| [pymupdf/PyMuPDF](https://github.com/pymupdf/PyMuPDF) **[tested]** (2.1) | PDF analysis (`get_drawings`, `get_image_info`, text with positions), native-image extraction, rendering, PDF writing with optional-content layers | **AGPL-3.0** or Artifex commercial | 11 k★, very active | High technically; **licence is the main constraint** (see §3) | `Shape` helper builds content strings quadratically — we write raw content streams instead |
| [mozman/ezdxf](https://github.com/mozman/ezdxf) **[tested]** (1.4.5) | DXF R12–R2018 read/write, layers, hatches, XDATA; `odafc` add-on for DWG via ODA File Converter | MIT | 1.5 k★, active | High | No native DWG writer (verified: DWG only through external ODA converter) |
| [shapely/shapely](https://github.com/shapely/shapely) **[tested]** (2.2) | Buffers, unions, noding, polygonize, STRtree | BSD-3-Clause | 4.5 k★, active | High | — |
| [networkx](https://github.com/networkx/networkx) **[tested]** | Graph topology analysis | BSD-3-Clause | Mature | High | — |
| [scikit-image](https://github.com/scikit-image/scikit-image) **[tested]** | Skeletonisation | BSD-3-Clause | Mature | High | — |
| [visioncortex/vtracer](https://github.com/visioncortex/vtracer) **[tested: install + API only]** | Raster → SVG (spline / polygon), Python binding on PyPI | MIT | 7.5 k★, active | High as a **permissive replacement for potrace** for annotation outlines | Graphics-oriented; SVG output only (needs parsing) |
| [autotrace/autotrace](https://github.com/autotrace/autotrace) **[docs]** | Raster → vector incl. **centre-line** mode | GPL-2.0 | 753★, active (2026-11) | Medium (subprocess) | Centre-line quality on noisy scans unknown — to evaluate |
| [fablabnbg/inkscape-centerline-trace](https://github.com/fablabnbg/inkscape-centerline-trace) **[docs]** | Inkscape extension wrapping autotrace centre-line | GPL-2.0 | 286★, last push 2020 | Low | Unmaintained |
| [art-programmer/FloorplanTransformation](https://github.com/art-programmer/FloorplanTransformation) **[docs]** | ICCV'17 Raster-to-Vector: junction heat-maps + integer programming | MIT | 689★, last push 2022; Lua/Torch7 | Low (obsolete framework) | Residential raster images; research demo |
| [CubiCasa/CubiCasa5k](https://github.com/CubiCasa/CubiCasa5k) **[docs]** | 5 000 annotated floor plans + PyTorch segmentation model | GitHub: NOASSERTION; dataset stated as CC BY-NC 4.0 in its README (verify) | 630★ | Evaluation data only | **Non-commercial** data; weights trained on it inherit that restriction |
| [SizheHu/Raster-to-Graph](https://github.com/SizheHu/Raster-to-Graph) **[docs]** | Floor-plan recognition as autoregressive graph prediction | GPL-3.0 | 68★, 2026-05 | Low | Research; GPU + weights; residential plans |
| [zcemycl/TF2DeepFloorplan](https://github.com/zcemycl/TF2DeepFloorplan) **[docs]** | Deep Floorplan multi-task segmentation (walls, rooms) | GPL-3.0 | 270★, 2023 | Low–medium | Pixel masks only; needs vectorisation anyway |
| [Vahe1994/Deep-Vectorization-of-Technical-Drawings](https://github.com/Vahe1994/Deep-Vectorization-of-Technical-Drawings) **[docs]** | Learned primitive (line/curve) vectorisation of technical drawings | MPL-2.0 | 159★, 2026-10 | Medium (file-level copyleft) | GPU, slow; no architectural semantics |
| [cvg/DeepLSD](https://github.com/cvg/DeepLSD) **[docs]** | Learned line-segment detection and refinement | MIT | 657★, 2026-09 | Medium | GPU recommended; candidate only if classic LSD fails on degraded scans |
| [navervision/mlsd](https://github.com/navervision/mlsd) **[docs]** | Lightweight learned LSD | Apache-2.0 | 621★, 2023 | Medium | Trained on natural images |
| [tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract) **[docs]** | OCR | Apache-2.0 | 77 k★ | High (Phase 5 dimension reading) | Rotated, small dimension text needs pre-cropping |
| [LibreCAD/LibreCAD](https://github.com/LibreCAD/LibreCAD) **[docs]** | 2-D CAD; DXF/DWG read, DXF write | GPL-2.0 | 6.6 k★, active | Free manual-correction tool for users without AutoCAD | Not a library |
| [tataksh-bhagat/2D-Floor-Plan-to-DXF](https://github.com/tataksh-bhagat/2D-Floor-Plan-to-DXF) **[code]** | 68-line contour → DXF script | GPL-3.0 | 19★, 2023 | None | Toy example |
| [RasterScan/Floor-Plan-Recognition](https://github.com/RasterScan/Floor-Plan-Recognition) **[docs]** | Commercial on-premise recognition | **No licence** | 98★ | **Cannot be reused** | — |
| [MLSTRUCT/MLStructFP](https://github.com/MLSTRUCT/MLStructFP) **[docs]** | Multi-unit floor-plan dataset | MIT | 68★ | Evaluation data | — |
| ODA File Converter **[docs]** | DXF ↔ DWG conversion (used by `ezdxf.addons.odafc`) | Proprietary freeware | — | Optional external step | Separate download/registration |
| LibreDWG **[docs, not verified this session]** | Experimental DWG write | GPL-3.0 | — | Low | Write support marked experimental by its authors |

## 2. Ranking and selection

1. **OpenCV + scikit-image + Shapely + NetworkX** — core of the raster pipeline. Mature, permissive
   (Apache/BSD), Windows wheels, deterministic, no GPU. Verified in this session.
2. **PyMuPDF** — best single library for *analysis* of PDFs (vector paths with style, text with
   positions, image placement matrices, native image extraction) and for layered PDF output. Chosen
   for the MVP, isolated in `pdf_input.py` and `export/pdf.py` because of AGPL (see §3).
3. **ezdxf** — the only mature pure-Python DXF writer; XDATA lets AutoLISP read confidence values.
   DWG via ODA File Converter is optional.
4. **Potrace (subprocess, optional)** — high-quality outlines for text/symbols that must be preserved
   but must not become CAD lines; falls back to OpenCV contours. **vtracer (MIT)** is the permissive
   replacement if potrace's GPL is unwanted even as a separate program.
5. **floorplan-to-vector** — not used as code (it expects semantic masks), but its *ideas* (thickness
   families, protected opening gaps, QA overlays, "never invent geometry") shaped Stage E.
6. **Deep models (DeepLSD, Deep Floorplan, Raster-to-Graph, CubiCasa)** — rejected for the MVP: GPU,
   weights, residential training data, GPL/NC licences, and no demonstrated advantage on clean
   orthogonal drawings. DeepLSD (MIT) is the first candidate if degraded scans defeat classic LSD.
7. **GRASS GIS** — strongest open ArcScan analogue, but too heavy and GPL for embedding; can be used
   offline as an independent cross-check of topology cleaning.

## 3. Licensing considerations

* PyMuPDF is **AGPL-3.0** (or commercial from Artifex). Distributing archvectra with PyMuPDF requires
  the whole application to be distributed under AGPL-compatible terms (source offered to users, also
  for network use). Options: (a) license archvectra as AGPL-3.0; (b) buy an Artifex licence; (c) replace
  PyMuPDF with **pypdfium2** (Apache-2.0/BSD, rendering + image extraction), **pdfminer.six** (MIT,
  path/text extraction) and **reportlab** (BSD, PDF writing — no optional-content layers). The
  backend is confined to two modules so (c) is a bounded change. **No licence has been chosen for
  archvectra yet — this is a decision for the project owner.**
* Potrace and autotrace are GPL-2.0 and are only invoked as separate executables; they are optional.
* CubiCasa5k data is non-commercial; do not ship models trained on it in a commercial product.
* RasterScan has no licence: all rights reserved — do not copy.

## 4. Algorithm comparison (Stage C)

| Method | Strengths | Weaknesses | Used for |
|---|---|---|---|
| Standard Hough | Robust to gaps | Infinite lines, quantised angle, no endpoints | Not used |
| Probabilistic Hough | Endpoints | Many fragments, parameter-sensitive | Not used |
| **LSD** (OpenCV) | Sub-pixel, parameter-free, fast | Double edges on thick strokes, splits at noise | **Skew estimation** |
| **Directional morphology + component fit** | Exact centreline and thickness of orthogonal solid walls | Orthogonal only | **Solid walls (H/V)** |
| **Minimum-area rectangle** | Straight thick diagonal blobs | Only straight | **Diagonal walls** |
| **Skeleton + graph tracing + Douglas-Peucker** | Any angle, curves, junction topology | Spurs at junctions, needs thin strokes | **Thin linework** |
| **Algebraic circle fit** | Exact arcs (door swings) | Needs a corner-free run | **Arcs** |
| Contours / Potrace | Faithful outlines | Not CAD lines | **Annotation preservation** |
| Graph reconstruction (Shapely noding + NetworkX) | Topology, rooms | Needs clean endpoints | **Rooms / connectivity** |
