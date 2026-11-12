"""Stage A - PDF analysis, raster acquisition and direct vector extraction.

Uses PyMuPDF (AGPL-3.0, see docs/RESEARCH.md for licensing implications).  All
PyMuPDF access in the project is confined to this module and ``export/pdf.py``
so the backend can be replaced (e.g. pypdfium2 + pdfminer.six + reportlab).
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pymupdf

from .model import (
    LAYER_ANNOTATION,
    LAYER_LINE,
    LAYER_SOLID,
    Polygon,
    Polyline,
    Segment,
    Text,
)

log = logging.getLogger(__name__)


class PdfInputError(RuntimeError):
    pass


@dataclass
class ImageInfo:
    xref: int
    width: int
    height: int
    bbox: tuple[float, float, float, float]
    transform: tuple[float, ...]
    effective_dpi: float
    axis_aligned: bool


@dataclass
class PageInfo:
    index: int
    width_pt: float
    height_pt: float
    rotation: int
    vector_items: int
    text_chars: int
    images: list[ImageInfo] = field(default_factory=list)
    image_coverage: float = 0.0
    kind: str = "unknown"  # "raster" | "vector" | "hybrid" | "empty"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- analysis
def analyze_page(page: pymupdf.Page) -> PageInfo:
    rect = page.rect
    drawings = page.get_drawings()
    vector_items = sum(len(d["items"]) for d in drawings)
    text_chars = len(page.get_text("text").strip())
    images: list[ImageInfo] = []
    covered = 0.0
    page_area = max(rect.width * rect.height, 1e-9)
    for info in page.get_image_info(xrefs=True):
        x0, y0, x1, y1 = info["bbox"]
        w_pt, h_pt = abs(x1 - x0), abs(y1 - y0)
        if w_pt < 1 or h_pt < 1:
            continue
        t = tuple(float(v) for v in info["transform"])
        aligned = abs(t[1]) < 1e-6 and abs(t[2]) < 1e-6 and t[0] > 0 and t[3] > 0
        eff = info["width"] / (w_pt / 72.0) if w_pt else 0.0
        images.append(ImageInfo(int(info.get("xref", 0)), int(info["width"]), int(info["height"]),
                                (x0, y0, x1, y1), t, float(eff), aligned))
        covered += (w_pt * h_pt) / page_area
    info = PageInfo(page.number, rect.width, rect.height, page.rotation, vector_items, text_chars,
                    images, min(covered, 1.0))
    info.kind = classify(info)
    if info.kind == "raster" and text_chars > 20:
        info.notes.append("page has a text layer over a scan (probably OCR); text is not re-used")
    return info


def classify(info: PageInfo) -> str:
    if info.image_coverage >= 0.5 and info.vector_items < 50:
        return "raster"
    if info.image_coverage < 0.05 and (info.vector_items > 0 or info.text_chars > 0):
        return "vector"
    if info.image_coverage >= 0.05 and info.vector_items >= 50:
        return "hybrid"
    if info.image_coverage >= 0.05:
        return "raster"
    return "empty"


def analyze_pdf(path: str | Path) -> list[PageInfo]:
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            raise PdfInputError("PDF is encrypted")
        return [analyze_page(p) for p in doc]


# --------------------------------------------------------------------------- raster
@dataclass
class RasterPage:
    gray: np.ndarray  # uint8, white paper ~255
    dpi: float  # pixels per inch on the sheet
    px_to_pt: tuple[float, float, float, float, float, float]
    page_size_pt: tuple[float, float]
    method: str
    notes: list[str] = field(default_factory=list)


def _pixmap_to_gray(pix: pymupdf.Pixmap) -> np.ndarray:
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    if pix.colorspace is None or pix.n != 1:
        pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
    return arr[:, : pix.width].copy()


def load_raster(path: str | Path, page_index: int, dpi: int, prefer_native: bool = True,
                max_pixels: int = 160_000_000, min_dpi: int = 100) -> RasterPage:
    with pymupdf.open(path) as doc:
        if not 0 <= page_index < len(doc):
            raise PdfInputError(f"page {page_index} out of range (document has {len(doc)} pages)")
        page = doc[page_index]
        info = analyze_page(page)
        size = (page.rect.width, page.rect.height)
        notes: list[str] = []
        # Native path: one dominant, axis-aligned image on an unrotated page.
        if prefer_native and page.rotation == 0 and info.images:
            img = max(info.images, key=lambda im: (im.bbox[2] - im.bbox[0]) * (im.bbox[3] - im.bbox[1]))
            area = (img.bbox[2] - img.bbox[0]) * (img.bbox[3] - img.bbox[1]) / (size[0] * size[1])
            if img.axis_aligned and area > 0.5 and img.xref > 0 and img.width * img.height <= max_pixels:
                gray = _pixmap_to_gray(pymupdf.Pixmap(doc, img.xref))
                if gray.shape != (img.height, img.width):
                    notes.append("native image size differs from metadata; using rendered page")
                else:
                    if gray.mean() < 100:
                        gray = 255 - gray
                        notes.append("embedded image appears inverted (white on black); inverted it")
                    sx = (img.bbox[2] - img.bbox[0]) / img.width
                    sy = (img.bbox[3] - img.bbox[1]) / img.height
                    dpi_x = 72.0 / sx
                    if abs(sx - sy) / sx > 0.01:
                        notes.append(f"non-square pixels (sx={sx:.4f}, sy={sy:.4f} pt/px)")
                    return RasterPage(gray, dpi_x, (sx, 0.0, 0.0, sy, img.bbox[0], img.bbox[1]),
                                      size, "native-image", notes)
        requested = dpi
        # tiled / multi-image scans: rendering above the scan's own resolution adds nothing
        if info.kind == "raster" and info.images:
            native = max(im.effective_dpi for im in info.images)
            if 72 <= native < dpi:
                dpi = int(round(native))
                notes.append(f"scan resolution is {native:.0f} DPI; rendered at that instead of {requested} DPI")
        # very large sheets: lower the resolution to stay within input.max_pixels (memory)
        fit = 72.0 * math.sqrt(max_pixels / (size[0] * size[1]))
        if dpi > fit:
            if fit < min_dpi:
                raise PdfInputError(f"page is too large: even {min_dpi} DPI exceeds input.max_pixels "
                                    f"({size[0] / 72 * 25.4:.0f} x {size[1] / 72 * 25.4:.0f} mm)")
            dpi = int(fit)
            notes.append(f"large sheet: rendered at {dpi} DPI instead of {requested} DPI to stay within "
                         f"input.max_pixels")
            log.warning("large sheet: rendering at %d DPI instead of %d DPI", dpi, requested)
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
        gray = _pixmap_to_gray(pix)
        s = size[0] / gray.shape[1]
        notes.append(f"rendered at {dpi} DPI")
        return RasterPage(gray, 72.0 / s, (s, 0.0, 0.0, s, 0.0, 0.0), size, "rendered", notes)


# --------------------------------------------------------------------------- vectors
def _bezier(p0, p1, p2, p3, n: int = 16) -> list[tuple[float, float]]:
    out = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3 * p0.x + 3 * mt**2 * t * p1.x + 3 * mt * t**2 * p2.x + t**3 * p3.x
        y = mt**3 * p0.y + 3 * mt**2 * t * p1.y + 3 * mt * t**2 * p2.y + t**3 * p3.y
        out.append((x, y))
    return out


@dataclass
class VectorContent:
    segments: list[Segment] = field(default_factory=list)
    polylines: list[Polyline] = field(default_factory=list)  # curve chains (arc fitting later)
    polygons: list[Polygon] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def extract_vectors(path: str | Path, page_index: int, include_text: bool = True) -> VectorContent:
    """Extract stroked/filled paths and text from a vector page, in PDF points (y down)."""
    out = VectorContent()
    with pymupdf.open(path) as doc:
        page = doc[page_index]
        rot = page.rotation_matrix if page.rotation else None

        def P(p):  # noqa: N802 - point transform
            q = p * rot if rot is not None else p
            return q

        n_lines = n_curves = n_fill = 0
        for d in page.get_drawings():
            width = d.get("width") or 0.0
            stroked = d.get("color") is not None and "s" in (d.get("type") or "s")
            filled = d.get("fill") is not None and "f" in (d.get("type") or "")
            style = {"stroke": d.get("color"), "fill": d.get("fill"), "width": width,
                     "dashes": d.get("dashes") if d.get("dashes") not in (None, "[] 0", "[] 0.0") else None}
            rings: list[list[tuple[float, float]]] = []
            chain: list[tuple[float, float]] = []
            curve_chain: list[tuple[float, float]] = []

            def flush_curve():
                nonlocal curve_chain
                if len(curve_chain) > 2:
                    out.polylines.append(Polyline(curve_chain, False, max(width, 0.1), LAYER_LINE, 1.0, "pdf-curve",
                                                  attrs={"style": style}))
                curve_chain = []

            for item in d["items"]:
                op = item[0]
                if op == "l":
                    a, b = P(item[1]), P(item[2])
                    if chain and math.dist(chain[-1], (a.x, a.y)) > 1e-3:
                        rings.append(chain)
                        chain = []
                    if not chain:
                        chain.append((a.x, a.y))
                    chain.append((b.x, b.y))
                    if stroked:
                        flush_curve()
                        out.segments.append(Segment(a.x, a.y, b.x, b.y, max(width, 0.1), "line",
                                                    LAYER_LINE, 1.0, "pdf-vector", attrs={"style": style}))
                        n_lines += 1
                elif op in ("re", "qu"):
                    if op == "re":
                        r = item[1]
                        pts = [P(r.tl), P(r.tr), P(r.br), P(r.bl)]
                    else:
                        q = item[1]
                        pts = [P(q.ul), P(q.ur), P(q.lr), P(q.ll)]
                    ring = [(p.x, p.y) for p in pts]
                    rings.append(ring + [ring[0]])
                    if stroked:
                        flush_curve()
                        for i in range(4):
                            a, b = ring[i], ring[(i + 1) % 4]
                            if math.dist(a, b) > 1e-6:
                                out.segments.append(Segment(a[0], a[1], b[0], b[1], max(width, 0.1),
                                                            "line", LAYER_LINE, 1.0, "pdf-vector",
                                                            attrs={"style": style}))
                                n_lines += 1
                elif op == "c":
                    pts = _bezier(P(item[1]), P(item[2]), P(item[3]), P(item[4]))
                    if chain and math.dist(chain[-1], pts[0]) > 1e-3:
                        rings.append(chain)
                        chain = []
                    chain.extend(pts if not chain else pts[1:])
                    if stroked:
                        if curve_chain and math.dist(curve_chain[-1], pts[0]) > 1e-3:
                            flush_curve()
                        curve_chain.extend(pts if not curve_chain else pts[1:])
                        n_curves += 1
            flush_curve()
            if chain:
                rings.append(chain)
            if filled:
                for poly in _nest_rings([r for r in rings if len(r) >= 3]):
                    poly.attrs["style"] = style
                    out.polygons.append(poly)
                    n_fill += 1
        if include_text:
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    dx, dy = line.get("dir", (1, 0))
                    ang = math.degrees(math.atan2(dy, dx))
                    for span in line.get("spans", []):
                        txt = span.get("text", "")
                        if txt.strip():
                            o = P(pymupdf.Point(span["origin"]))
                            out.texts.append(Text(o.x, o.y, txt, float(span["size"]), ang))
        out.stats = {"stroke_lines": n_lines, "curves": n_curves, "fills": n_fill, "texts": len(out.texts)}
    return out


def _nest_rings(rings: list[list[tuple[float, float]]]) -> list[Polygon]:
    """Group the sub-paths of one fill into polygons: a ring inside an outer ring is a hole."""
    from shapely import Polygon as ShPolygon

    rings = [r[:-1] if len(r) > 3 and math.dist(r[0], r[-1]) < 1e-6 else r for r in rings]
    rings = sorted((r for r in rings if len(r) >= 3 and abs(_ring_area(r)) > 1e-9), key=lambda r: -abs(_ring_area(r)))
    outers: list[tuple[ShPolygon, Polygon]] = []
    for r in rings:
        probe = ShPolygon(r).buffer(0)
        parent = None
        for sp, poly in reversed(outers):
            if sp.buffer(1e-6).contains(probe):
                parent = poly
                break
        if parent is not None and not any(ShPolygon(h).buffer(1e-6).contains(probe) for h in parent.holes):
            parent.holes.append(r)
            continue
        poly = Polygon(r, [], LAYER_SOLID, True, 1.0, "pdf-fill")
        outers.append((ShPolygon(r).buffer(0), poly))
    return [p for _, p in outers]


def _ring_area(r: list[tuple[float, float]]) -> float:
    a = 0.0
    for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
        a += x1 * y2 - x2 * y1
    return a / 2


__all__ = [
    "PageInfo", "ImageInfo", "RasterPage", "VectorContent", "PdfInputError",
    "analyze_pdf", "analyze_page", "classify", "load_raster", "extract_vectors", "LAYER_ANNOTATION",
]
