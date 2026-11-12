"""Vector PDF export.

The page has exactly the size of the source page.  Content is written as a raw
PDF content stream (linear time even for sheets with 10^5 paths; PyMuPDF's
``Shape`` helper builds its string quadratically), and every CAD layer becomes a
PDF optional-content group, i.e. a layer that can be toggled in Acrobat and
most viewers.  Text from vector sources is re-inserted with PyMuPDF.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from ..config import ExportConfig
from ..model import (
    LAYER_ANNOTATION,
    LAYER_ARC,
    LAYER_COLUMN,
    LAYER_DOOR,
    LAYER_GLAZING,
    LAYER_LINE,
    LAYER_SOLID,
    LAYER_TEXT,
    LAYER_WALL,
    Drawing,
)
from .common import PT_PER_MM, Frame, collect_polygons, fill_style, stroke_style

REVIEW_COLORS = {
    LAYER_WALL: (0.1, 0.1, 0.1), LAYER_COLUMN: (0.0, 0.2, 0.8), LAYER_SOLID: (0.4, 0.4, 0.4),
    LAYER_LINE: (0.0, 0.5, 0.0), LAYER_ARC: (0.0, 0.6, 0.6), LAYER_DOOR: (0.0, 0.6, 0.0),
    LAYER_GLAZING: (0.0, 0.4, 0.9), LAYER_ANNOTATION: (0.7, 0.45, 0.0), LAYER_TEXT: (0.7, 0.45, 0.0),
}


def _n(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def _rgb(c) -> str:
    return " ".join(_n(v) for v in c)


class _Stream:
    """Collects PDF path operators for a page (y-up PDF user space)."""

    def __init__(self, height_pt: float):
        self.h = height_pt
        self.parts: list[str] = []
        self.props: dict[str, int] = {}  # resource name -> OCG xref

    def P(self, pt) -> str:  # noqa: N802
        return f"{_n(pt[0])} {_n(self.h - pt[1])}"

    def begin_layer(self, name: str | None, ocg: int | None) -> None:
        if ocg:
            res = f"oc{ocg}"
            self.props[res] = ocg
            self.parts.append(f"/OC /{res} BDC\n")
        self.parts.append("q\n")

    def end_layer(self, ocg: int | None) -> None:
        self.parts.append("Q\n")
        if ocg:
            self.parts.append("EMC\n")

    def ring(self, pts) -> None:
        self.parts.append(f"{self.P(pts[0])} m\n")
        self.parts.extend(f"{self.P(p)} l\n" for p in pts[1:])
        self.parts.append("h\n")

    def path(self, pts) -> None:
        self.parts.append(f"{self.P(pts[0])} m\n")
        self.parts.extend(f"{self.P(p)} l\n" for p in pts[1:])

    def bytes(self) -> bytes:
        return "".join(self.parts).encode("latin-1")


def _install(doc: pymupdf.Document, page: pymupdf.Page, st: _Stream, extgstate: dict[str, str] | None = None) -> None:
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, st.bytes())
    existing = page.get_contents()
    refs = " ".join(f"{x} 0 R" for x in existing + [xref])
    doc.xref_set_key(page.xref, "Contents", f"[{refs}]")
    kind, val = doc.xref_get_key(page.xref, "Resources")
    if kind == "xref":
        target, prefix = int(val.split()[0]), ""
    else:
        target, prefix = page.xref, "Resources/"
    for name, ocg in st.props.items():
        doc.xref_set_key(target, f"{prefix}Properties/{name}", f"{ocg} 0 R")
    for name, gsv in (extgstate or {}).items():
        doc.xref_set_key(target, f"{prefix}ExtGState/{name}", gsv)


def _draw(drawing: Drawing, cfg: ExportConfig, st: _Stream, ocgs: dict[str, int] | None,
          colors: dict[str, tuple] | None = None, gstate: str | None = None) -> None:
    fr = Frame(drawing)
    lw = cfg.line_width_mm * PT_PER_MM
    wlw = cfg.wall_outline_width_mm * PT_PER_MM

    def col(layer):
        return (colors or {}).get(layer, (0, 0, 0))

    def oc(layer):
        return (ocgs or {}).get(layer)

    gs = f"/{gstate} gs\n" if gstate else ""
    keep = cfg.preserve_vector_style and colors is None
    by_layer: dict[tuple, list] = {}
    for poly in collect_polygons(drawing):
        if poly.layer == LAYER_ANNOTATION and not cfg.include_annotations:
            continue
        by_layer.setdefault((poly.layer, fill_style(poly, keep)), []).append(poly)
    for (layer, fcol), polys in by_layer.items():
        c = fcol or col(layer)
        st.begin_layer(layer, oc(layer))
        st.parts.append(gs + f"{_rgb(c)} rg {_rgb(c)} RG {_n(wlw)} w 1 j\n")
        for poly in polys:
            for ring in [poly.exterior] + poly.holes:
                st.ring([fr.pt(*p) for p in ring])
        if layer == LAYER_WALL:
            st.parts.append("B*\n" if cfg.wall_fill else "S\n")
        else:
            st.parts.append("f*\n")
        st.end_layer(oc(layer))
    lines: dict[tuple, list] = {}

    def key(item):
        c, w, dsh = stroke_style(item, keep, lw)
        return (item.layer, c, round(w, 3), dsh)

    for s in drawing.segments:
        if s.kind == "wall":
            continue
        lines.setdefault(key(s), []).append([fr.pt(s.x1, s.y1), fr.pt(s.x2, s.y2)])
    for a in drawing.arcs:
        lines.setdefault(key(a), []).append([fr.pt(*p) for p in a.points()])
    for pl in drawing.polylines:
        pts = [fr.pt(*p) for p in pl.points]
        lines.setdefault(key(pl), []).append(pts + ([pts[0]] if pl.closed else []))
    for (layer, c, w, dsh), items in lines.items():
        st.begin_layer(layer, oc(layer))
        st.parts.append(gs + f"{_rgb(c or col(layer))} RG {_n(w)} w 1 J 1 j {dsh or '[] 0'} d\n")
        for pts in items:
            st.path(pts)
        st.parts.append("S\n")
        st.end_layer(oc(layer))


def _insert_text(page: pymupdf.Page, drawing: Drawing, ocg: int | None, color=(0, 0, 0)) -> None:
    fr = Frame(drawing)
    k = fr.unit_to_pt
    for t in drawing.texts:
        x, y = fr.pt(t.x, t.y)
        try:
            page.insert_text(pymupdf.Point(x, y), t.text, fontsize=max(t.size * k, 1.0), color=color, oc=ocg or 0,
                             morph=(pymupdf.Point(x, y), pymupdf.Matrix(-t.angle_deg)) if t.angle_deg else None)
        except Exception:  # noqa: BLE001 - glyphs outside the base-14 font are skipped
            pass


def write_pdf(drawing: Drawing, path: str | Path, cfg: ExportConfig, title: str = "archvectra") -> Path:
    path = Path(path)
    doc = pymupdf.open()
    w, h = drawing.page_size_pt
    page = doc.new_page(width=w, height=h)
    used = {s.layer for s in drawing.segments if s.kind != "wall"} | {p.layer for p in drawing.polygons}
    used |= {a.layer for a in drawing.arcs} | {p.layer for p in drawing.polylines}
    if drawing.walls():
        used.add(LAYER_WALL)
    if drawing.texts and cfg.include_text:
        used.add(LAYER_TEXT)
    ocgs = {name: doc.add_ocg(name, on=True) for name in sorted(used)}
    st = _Stream(h)
    _draw(drawing, cfg, st, ocgs)
    _install(doc, page, st)
    if cfg.include_text and drawing.texts:
        _insert_text(page, drawing, ocgs.get(LAYER_TEXT))
    doc.set_metadata({"title": title, "creator": "archvectra", "producer": "archvectra (PyMuPDF)",
                      "subject": f"scale: {drawing.scale.source}"})
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def write_review_pdf(drawing: Drawing, path: str | Path, cfg: ExportConfig, source_pdf: str | Path,
                     page_index: int, background=None) -> Path:
    """Source (faded) with the reconstruction in colour, openings and review flags.

    ``background`` - optional working-frame raster (e.g. the deskewed scan) used
    instead of the original page so that the overlay is aligned."""
    path = Path(path)
    doc = pymupdf.open()
    w, h = drawing.page_size_pt
    page = doc.new_page(width=w, height=h)
    if background is not None:
        import cv2

        ok, buf = cv2.imencode(".jpg", background, [cv2.IMWRITE_JPEG_QUALITY, 70])
        a, b, c, d, e, f = drawing.px_to_pt
        page.insert_image(pymupdf.Rect(e, f, e + a * drawing.width, f + d * drawing.height), stream=buf.tobytes())
    else:
        with pymupdf.open(source_pdf) as src:
            page.show_pdf_page(page.rect, src, page_index)
    fr = Frame(drawing)
    st = _Stream(h)
    st.parts.append(f"q /fade gs 1 1 1 rg 0 0 {_n(w)} {_n(h)} re f Q\n")
    _draw(drawing, cfg, st, None, REVIEW_COLORS, gstate="ink")
    st.parts.append("q 0.8 0 0.8 RG 2 w\n")
    for o in drawing.openings:
        st.path([fr.pt(*o.p1), fr.pt(*o.p2)])
    st.parts.append("S Q\n")
    sev = {"info": (0.2, 0.5, 1.0), "warning": (1.0, 0.5, 0.0), "error": (1.0, 0.0, 0.0)}
    for f in drawing.flags:
        x, y = fr.pt(f.x, f.y)
        st.parts.append(f"q {_rgb(sev.get(f.severity, (1, 0, 0)))} RG 1.2 w\n")
        r = 5.0
        st.parts.append(f"{st.P((x - r, y - r))} m {st.P((x + r, y - r))} l {st.P((x + r, y + r))} l "
                        f"{st.P((x - r, y + r))} l h S Q\n")
    _install(doc, page, st, {"fade": "<</ca 0.65/CA 0.65>>", "ink": "<</ca 0.85/CA 0.85>>"})
    fs = 6
    for o in drawing.openings:
        a, b = fr.pt(*o.p1), fr.pt(*o.p2)
        page.insert_text(((a[0] + b[0]) / 2 + 2, (a[1] + b[1]) / 2 - 2), f"{o.kind} {o.confidence:.2f}",
                         fontsize=fs, color=(0.6, 0, 0.6))
    for f in drawing.flags:
        if f.severity != "info":
            x, y = fr.pt(f.x, f.y)
            page.insert_text((x + 6, y - 6), f.code, fontsize=fs, color=sev.get(f.severity, (1, 0, 0)))
    if cfg.include_text and drawing.texts:
        _insert_text(page, drawing, None, REVIEW_COLORS[LAYER_TEXT])
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path
