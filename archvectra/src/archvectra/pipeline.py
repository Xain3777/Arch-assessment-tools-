"""End-to-end orchestration: PDF in -> clean vector PDF / SVG / DXF + validation.

Output layout (one folder per run)::

    <out>/
      00_source/      untouched copy of the input PDF
      01_raster/      source raster, preprocessed raster, binary and class masks
      02_vector/      clean.pdf, clean.svg, clean.dxf, review.pdf, model.json
      03_validation/  overlay.png, comparison.png, report.json, report.md
      manifest.json   configuration, processing history, versions, checksums
      run.log
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from . import __version__
from .config import Config, mm_to_px
from .correct import correct
from .export.dxf import write_dwg, write_dxf
from .export.pdf import write_pdf, write_review_pdf
from .export.svg import write_svg
from .extract import classify_path, extract
from .geometry import rasterize
from .model import LAYER_COLUMN, LAYER_SOLID, LAYER_WALL, Drawing, Segment
from .pdf_input import analyze_pdf, extract_vectors, load_raster
from .preprocess import preprocess
from .scale import build_scale
from .semantics import find_openings, pair_double_line_walls, topology
from .trace import trace
from .validate import (
    comparison_image,
    ink_metrics,
    overlay_image,
    render_pdf_to_frame,
    truth_metrics,
    write_markdown,
)

log = logging.getLogger("archvectra")


class PipelineError(RuntimeError):
    pass


@dataclass
class RunResult:
    out_dir: Path
    drawing: Drawing
    outputs: dict[str, str] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _setup_logging(out: Path, verbose: bool) -> logging.Handler:
    handler = logging.FileHandler(out / "run.log", mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("archvectra")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(handler)
    return handler


def _imwrite(path: Path, img: np.ndarray) -> None:
    if not cv2.imwrite(str(path), img):
        raise PipelineError(f"could not write {path}")


# --------------------------------------------------------------------------- raster branch
def _process_raster(pdf: Path, cfg: Config, out: Path, kind: str) -> tuple[Drawing, dict]:
    rp = load_raster(pdf, cfg.input.page, cfg.input.dpi, cfg.input.prefer_native_image, cfg.input.max_pixels)
    log.info("raster acquired via %s: %dx%d px at %.1f dpi", rp.method, rp.gray.shape[1], rp.gray.shape[0], rp.dpi)
    if rp.dpi < cfg.input.min_dpi_warning:
        log.warning("effective resolution %.0f dpi is low; thin lines may be lost", rp.dpi)
    allow_deskew = kind != "hybrid"
    pre = preprocess(rp.gray, rp.dpi, cfg.preprocess, allow_deskew=allow_deskew)
    raster_dir = out / "01_raster"
    _imwrite(raster_dir / "source.png", rp.gray)
    _imwrite(raster_dir / "preprocessed.png", pre.gray)
    _imwrite(raster_dir / "binary.png", ((1 - pre.binary) * 255).astype(np.uint8))

    ex = extract(pre.binary, cfg.extract, rp.dpi, heal_mm=cfg.correct.merge_gap_mm)
    h, w = pre.binary.shape
    drawing = Drawing(w, h, rp.dpi, rp.px_to_pt, rp.page_size_pt, build_scale(cfg.scale, rp.dpi), kind)
    drawing.segments, drawing.arcs, drawing.polylines = ex.segments, ex.arcs, ex.polylines
    drawing.polygons = ex.polygons
    drawing.history.extend({"stage": "preprocess", **hst} for hst in pre.history)
    drawing.log("acquire", method=rp.method, dpi=round(rp.dpi, 3), notes=rp.notes)
    drawing.log("extract", **ex.stats)
    drawing.meta["deskew_affine"] = pre.affine.tolist()
    drawing.meta["skew_deg"] = pre.skew_deg

    masks = np.full((h, w, 3), 255, np.uint8)
    masks[ex.thin_mask > 0] = (0, 150, 0)
    masks[ex.wall_mask > 0] = (40, 40, 40)
    masks[ex.annotation_mask > 0] = (200, 120, 0)
    _imwrite(raster_dir / "classes.png", masks)

    if kind == "hybrid":
        vc = extract_vectors(pdf, cfg.input.page, cfg.export.include_text)
        _merge_vectors(drawing, vc, to_frame=True)
        drawing.log("hybrid_vectors", **vc.stats)

    correct(drawing, cfg.correct)
    find_openings(drawing, cfg.correct)
    if cfg.correct.pair_double_line_walls:
        pair_double_line_walls(drawing, cfg.correct)
    topology(drawing)

    # annotation + any ink the geometry does not explain -> traced outlines
    geom_bin = pre.binary & (1 - ex.annotation_mask)
    recon = rasterize(drawing, (h, w), include_annotation=False)
    tol = max(2, int(round(mm_to_px(cfg.validation.tolerance_mm, rp.dpi))))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * tol + 1, 2 * tol + 1))
    residual = geom_bin & (1 - cv2.dilate(recon, k))
    residual = cv2.morphologyEx(residual, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, labels, st, cents = cv2.connectedComponentsWithStats(residual, connectivity=8)
    min_area = mm_to_px(0.5, rp.dpi) ** 2
    keep = np.zeros(n, bool)
    big = 0
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] >= min_area:
            keep[i] = True
            if max(st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT]) > mm_to_px(cfg.correct.opening_min_mm, rp.dpi):
                big += 1
                drawing.flag(cents[i][0], cents[i][1], "untraced-ink",
                             "ink not explained by extracted geometry; kept as outline", "warning")
    residual_kept = keep[labels].astype(np.uint8)
    anno_mask = ex.annotation_mask | residual_kept
    if cfg.export.include_annotations:
        polys, backend = trace(anno_mask, cfg.export.annotation_backend)
        drawing.polygons.extend(polys)
        drawing.log("annotation_trace", backend=backend, polygons=len(polys),
                    residual_components=int(keep.sum()), large_residuals=big)
    drawing.meta["_binary"] = pre.binary  # transient, stripped before saving
    drawing.meta["_annotation_mask"] = anno_mask
    drawing.meta["_source_gray"] = rp.gray
    drawing.meta["_working_gray"] = pre.gray
    return drawing, {"raster_method": rp.method, "raster_notes": rp.notes}


def _merge_vectors(drawing: Drawing, vc, to_frame: bool = False) -> None:
    """Add PDF vector content; ``to_frame`` maps PDF points into the raster frame."""
    a, b, c, d, e, f = drawing.px_to_pt

    def T(x, y):  # noqa: N802
        return ((x - e) / a, (y - f) / d) if to_frame else (x, y)

    k = 1 / a if to_frame else 1.0
    for s in vc.segments:
        x1, y1 = T(s.x1, s.y1)
        x2, y2 = T(s.x2, s.y2)
        drawing.segments.append(Segment(x1, y1, x2, y2, s.thickness * k, s.kind, s.layer, 1.0, s.source,
                                        attrs=dict(s.attrs)))
    for poly in vc.polygons:
        poly.exterior = [T(*p) for p in poly.exterior]
        poly.holes = [[T(*p) for p in h] for h in poly.holes]
        drawing.polygons.append(poly)
    eps = drawing.mm(0.05)
    for pl in vc.polylines:
        pts = np.array([T(*p) for p in pl.points])
        segs, arcs, polys = classify_path(pts, eps, drawing.mm(0.5), drawing.mm(0.05), 10.0, pl.thickness * k,
                                          True, "pdf-curve")
        for item in segs + arcs + polys:
            item.attrs["style"] = pl.attrs.get("style")
        drawing.segments += segs
        drawing.arcs += arcs
        drawing.polylines += polys
    for t in vc.texts:
        t.x, t.y = T(t.x, t.y)
        t.size *= k
        drawing.texts.append(t)


def _walls_from_fills(drawing: Drawing, cfg: Config) -> int:
    """Vector PDFs: filled, rectangle-like polygons with wall-like width become wall segments."""
    from shapely import Polygon as ShPolygon

    lo, hi = drawing.mm(cfg.extract.wall_min_thickness_mm), drawing.mm(cfg.correct.double_wall_max_mm * 2)
    keep = []
    n = 0
    for poly in drawing.polygons:
        if poly.holes or len(poly.exterior) < 4:
            keep.append(poly)
            continue
        sp = ShPolygon(poly.exterior)
        if not sp.is_valid or sp.area <= 0:
            keep.append(poly)
            continue
        mrr = sp.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)
        e1, e2 = np.subtract(cs[1], cs[0]), np.subtract(cs[2], cs[1])
        l1, l2 = float(np.hypot(*e1)), float(np.hypot(*e2))
        long_, short = max(l1, l2), min(l1, l2)
        if sp.area / max(mrr.area, 1e-9) > 0.95 and lo <= short <= hi and long_ >= 2 * short:
            ax = e1 if l1 >= l2 else e2
            u = ax / np.linalg.norm(ax)
            cx, cy = mrr.centroid.x, mrr.centroid.y
            p = np.array([cx, cy]) - u * long_ / 2
            q = np.array([cx, cy]) + u * long_ / 2
            drawing.segments.append(Segment(float(p[0]), float(p[1]), float(q[0]), float(q[1]), short, "wall",
                                            LAYER_WALL, 1.0, "pdf-fill-wall"))
            n += 1
        else:
            if poly.layer == LAYER_SOLID and sp.area < drawing.mm(cfg.extract.column_max_size_mm) ** 2 and \
                    long_ / max(short, 1e-9) < 2.5 and short >= lo:
                poly.layer = LAYER_COLUMN
            keep.append(poly)
    drawing.polygons = keep
    return n


def _process_vector(pdf: Path, cfg: Config, info) -> tuple[Drawing, dict]:
    vc = extract_vectors(pdf, cfg.input.page, cfg.export.include_text)
    w, h = info.width_pt, info.height_pt
    drawing = Drawing(int(round(w)), int(round(h)), 72.0, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), (w, h),
                      build_scale(cfg.scale, 72.0), "vector")
    _merge_vectors(drawing, vc)
    n_walls = _walls_from_fills(drawing, cfg)
    drawing.log("vector_extract", **vc.stats, walls_from_fills=n_walls)
    correct(drawing, cfg.correct, vector_source=True)
    find_openings(drawing, cfg.correct)
    if cfg.correct.pair_double_line_walls:
        pair_double_line_walls(drawing, cfg.correct)
    topology(drawing)
    return drawing, {"raster_method": "none (direct vector extraction)"}


# --------------------------------------------------------------------------- main entry
def run(input_pdf: str | Path, out_dir: str | Path, cfg: Config | None = None, truth: str | Path | None = None,
        verbose: bool = False) -> RunResult:
    cfg = cfg or Config()
    pdf = Path(input_pdf)
    if not pdf.is_file():
        raise PipelineError(f"input not found: {pdf}")
    out = Path(out_dir)
    for sub in ("00_source", "01_raster", "02_vector", "03_validation"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    handler = _setup_logging(out, verbose)
    t0 = time.perf_counter()
    try:
        src_hash = _sha256(pdf)
        shutil.copy2(pdf, out / "00_source" / pdf.name)
        pages = analyze_pdf(pdf)
        if not 0 <= cfg.input.page < len(pages):
            raise PipelineError(f"page {cfg.input.page} out of range (document has {len(pages)} pages)")
        info = pages[cfg.input.page]
        log.info("page %d classified as %s (%d vector items, %d images, coverage %.2f)", info.index, info.kind,
                 info.vector_items, len(info.images), info.image_coverage)
        if info.kind == "empty":
            raise PipelineError("page contains neither vector content nor images")
        if info.kind == "vector":
            drawing, extra = _process_vector(pdf, cfg, info)
        else:
            drawing, extra = _process_raster(pdf, cfg, out, info.kind)
        drawing.meta["page_info"] = info.to_dict()

        # ---- export
        vec = out / "02_vector"
        outputs: dict[str, str] = {}
        stem = pdf.stem
        if "pdf" in cfg.export.formats:
            outputs["pdf"] = str(write_pdf(drawing, vec / f"{stem}_clean.pdf", cfg.export, title=stem))
        if "svg" in cfg.export.formats:
            outputs["svg"] = str(write_svg(drawing, vec / f"{stem}_clean.svg", cfg.export))
        if "dxf" in cfg.export.formats:
            outputs["dxf"] = str(write_dxf(drawing, vec / f"{stem}_clean.dxf", cfg.export))
            if cfg.export.dwg:
                try:
                    outputs["dwg"] = str(write_dwg(outputs["dxf"], vec / f"{stem}_clean.dwg"))
                except RuntimeError as exc:
                    log.warning("DWG not written: %s", exc)
        if cfg.export.review_pdf:
            outputs["review_pdf"] = str(write_review_pdf(drawing, vec / f"{stem}_review.pdf", cfg.export, pdf,
                                                         cfg.input.page, drawing.meta.get("_working_gray")))

        # ---- validation
        report: dict[str, Any] = {
            "source": {"file": pdf.name, "sha256": src_hash, "page": cfg.input.page, "kind": info.kind, **extra},
            "dpi": drawing.dpi,
            "scale": {"source": drawing.scale.source, "calibrated": drawing.scale.calibrated,
                      "mm_per_unit": drawing.scale.mm_per_unit, "denominator": drawing.scale.denominator,
                      "notes": drawing.scale.notes},
            "summary": drawing.summary(),
            "page_size_mm": [round(v * 25.4 / 72.0, 4) for v in drawing.page_size_pt],
        }
        flags: dict[str, int] = {}
        for fl in drawing.flags:
            flags[fl.code] = flags.get(fl.code, 0) + 1
        report["flags_by_code"] = flags
        if cfg.validation.enabled and "pdf" in outputs and "_binary" in drawing.meta:
            tol = mm_to_px(cfg.validation.tolerance_mm, drawing.dpi)
            recon = render_pdf_to_frame(outputs["pdf"], drawing)
            src = drawing.meta["_binary"]
            report["ink_all"] = ink_metrics(src, recon, tol)
            anno = drawing.meta["_annotation_mask"]
            recon_geom = rasterize(drawing, src.shape, include_annotation=False,
                                   line_px=max(1.0, cfg.export.line_width_mm * drawing.dpi / 25.4))
            report["ink_geometry"] = ink_metrics(src & (1 - anno), recon_geom, tol)
            ov = overlay_image(src, recon, tol)
            vdir = out / "03_validation"
            _imwrite(vdir / "overlay.png", ov)
            _imwrite(vdir / "comparison.png",
                     comparison_image(drawing.meta["_source_gray"], recon, ov, cfg.validation.comparison_max_width_px))
            outputs["overlay"] = str(vdir / "overlay.png")
            outputs["comparison"] = str(vdir / "comparison.png")
        elif cfg.validation.enabled and "pdf" in outputs:
            # vector input: compare the clean output against a rendering of the original page
            report["ink_all"] = _vector_agreement(pdf, cfg, outputs["pdf"], out / "03_validation", outputs)
        if truth:
            report["truth"] = truth_metrics(drawing, json.loads(Path(truth).read_text()),
                                            mm_to_px(cfg.validation.tolerance_mm, drawing.dpi))
        report["elapsed_s"] = round(time.perf_counter() - t0, 2)
        (out / "03_validation" / "report.json").write_text(json.dumps(report, indent=1, default=float))
        write_markdown(report, out / "03_validation" / "report.md")
        (out / "summary.txt").write_text(_summary_text(report), encoding="utf-8")
        outputs["report"] = str(out / "03_validation" / "report.md")

        for key in [k for k in drawing.meta if k.startswith("_")]:
            drawing.meta.pop(key)
        (vec / "model.json").write_text(json.dumps(drawing.to_dict(), default=float))
        outputs["model"] = str(vec / "model.json")
        manifest = {
            "archvectra_version": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "input": {"path": str(pdf), "sha256": src_hash},
            "config": cfg.to_dict(),
            "history": drawing.history,
            "outputs": outputs,
            "elapsed_s": report["elapsed_s"],
        }
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
        log.info("done in %.1fs: %s", report["elapsed_s"], json.dumps(drawing.summary()))
        return RunResult(out, drawing, outputs, report)
    except Exception:
        log.exception("pipeline failed")
        raise
    finally:
        logging.getLogger("archvectra").removeHandler(handler)
        handler.close()


def _summary_text(report: dict[str, Any]) -> str:
    """Short plain-text result, one fact per line (read by the AutoCAD command)."""
    s = report.get("summary", {})
    sc = report.get("scale", {})
    kinds = s.get("segments_by_kind", {})
    ops = ", ".join(f"{k} {v}" for k, v in s.get("openings", {}).items()) or "none"
    flags = ", ".join(f"{k} {v}" for k, v in report.get("flags_by_code", {}).items()) or "none"
    lines = [
        f"Source: {report['source']['file']} page {report['source']['page'] + 1} ({report['source']['kind']})",
        f"Scale: {'calibrated 1:%g' % sc['denominator'] if sc.get('calibrated') and sc.get('denominator') else 'NOT calibrated (sheet mm)'}",
        f"Walls: {kinds.get('wall', 0)}   lines: {kinds.get('line', 0)}   arcs: {s.get('arcs', 0)}   rooms: {s.get('rooms', 0)}",
        f"Openings: {ops}",
        f"Review flags: {flags}",
    ]
    ink = report.get("ink_all")
    if ink:
        lines.append(f"Match with source: precision {ink['precision']:.3f}  recall {ink['recall']:.3f}")
    lines.append(f"Time: {report.get('elapsed_s', 0):.1f} s")
    w, h = report.get("page_size_mm", (0.0, 0.0))
    lines.append(f"PAGE_MM {w:.4f} {h:.4f}")  # machine-readable: sheet size, used by AutoCAD alignment
    return "\n".join(lines) + "\n"


def _vector_agreement(pdf: Path, cfg: Config, clean_pdf: str, vdir: Path, outputs: dict) -> dict:
    import pymupdf

    dpi = 150

    def render(path):
        with pymupdf.open(path) as doc:
            pix = doc[0 if path == clean_pdf else cfg.input.page].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, : pix.width]
            return img.copy()

    a, b = render(pdf), render(clean_pdf)
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    a, b = a[:h, :w], b[:h, :w]
    sa, sb = (a < 160).astype(np.uint8), (b < 160).astype(np.uint8)
    tol = mm_to_px(cfg.validation.tolerance_mm, dpi)
    ov = overlay_image(sa, sb, tol)
    _imwrite(vdir / "overlay.png", ov)
    _imwrite(vdir / "comparison.png", comparison_image(a, sb, ov, cfg.validation.comparison_max_width_px))
    outputs["overlay"] = str(vdir / "overlay.png")
    outputs["comparison"] = str(vdir / "comparison.png")
    return ink_metrics(sa, sb, tol)
