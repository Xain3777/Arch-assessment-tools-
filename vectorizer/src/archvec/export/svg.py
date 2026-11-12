"""SVG export: one <g> per CAD layer (Inkscape-compatible layers), page-sized."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from ..config import ExportConfig
from ..model import LAYER_ANNOTATION, LAYER_TEXT, LAYER_WALL, Drawing
from .common import PT_PER_MM, Frame, collect_polygons, fill_style, parse_dashes, stroke_style


def _f(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def write_svg(drawing: Drawing, path: str | Path, cfg: ExportConfig) -> Path:
    path = Path(path)
    fr = Frame(drawing)
    w, h = drawing.page_size_pt
    lw = cfg.line_width_mm * PT_PER_MM
    wlw = cfg.wall_outline_width_mm * PT_PER_MM
    groups: dict[str, list[str]] = {}
    keep = cfg.preserve_vector_style

    def hexc(c):
        return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in c)

    def sattr(item):
        c, w, dsh = stroke_style(item, keep, lw)
        if c is None and dsh is None and w == lw:
            return ""
        out = f' stroke-width="{_f(w)}"'
        if c is not None:
            out += f' stroke="{hexc(c)}"'
        if dsh:
            out += f' stroke-dasharray="{" ".join(_f(v) for v in parse_dashes(dsh))}"'
        return out

    def ring_d(ring):
        pts = [fr.pt(*p) for p in ring]
        return "M" + " L".join(f"{_f(x)},{_f(y)}" for x, y in pts) + " Z"

    for poly in collect_polygons(drawing):
        if poly.layer == LAYER_ANNOTATION and not cfg.include_annotations:
            continue
        d = " ".join(ring_d(r) for r in [poly.exterior] + poly.holes)
        if poly.layer == LAYER_WALL:
            fill = "#000" if cfg.wall_fill else "none"
            groups.setdefault(poly.layer, []).append(
                f'<path d="{d}" fill="{fill}" fill-rule="evenodd" stroke="#000" stroke-width="{_f(wlw)}"/>')
        else:
            fc = fill_style(poly, keep)
            groups.setdefault(poly.layer, []).append(
                f'<path d="{d}" fill="{hexc(fc) if fc else "#000"}" stroke="none" fill-rule="evenodd"/>')
    for s in drawing.segments:
        if s.kind == "wall":
            continue
        (x1, y1), (x2, y2) = fr.pt(s.x1, s.y1), fr.pt(s.x2, s.y2)
        groups.setdefault(s.layer, []).append(
            f'<line x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}"{sattr(s)}/>')
    for a in drawing.arcs:
        # true SVG arc command keeps the curve exact
        (sx, sy), (ex, ey) = fr.pt(*a.points()[0]), fr.pt(*a.points()[-1])
        r = a.r * fr.unit_to_pt
        large = 1 if a.sweep > 180 else 0
        if a.sweep >= 359.9:
            cx, cy = fr.pt(a.cx, a.cy)
            groups.setdefault(a.layer, []).append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="{_f(r)}" fill="none"{sattr(a)}/>')
        else:
            groups.setdefault(a.layer, []).append(
                f'<path d="M{_f(sx)},{_f(sy)} A{_f(r)},{_f(r)} 0 {large} 1 {_f(ex)},{_f(ey)}" fill="none"{sattr(a)}/>')
    for pl in drawing.polylines:
        pts = " ".join(f"{_f(x)},{_f(y)}" for x, y in (fr.pt(*p) for p in pl.points))
        tag = "polygon" if pl.closed else "polyline"
        groups.setdefault(pl.layer, []).append(f'<{tag} points="{pts}" fill="none"{sattr(pl)}/>')
    if cfg.include_text:
        k = fr.unit_to_pt
        for t in drawing.texts:
            x, y = fr.pt(t.x, t.y)
            rot = f' transform="rotate({_f(-t.angle_deg)} {_f(x)} {_f(y)})"' if t.angle_deg else ""
            groups.setdefault(LAYER_TEXT, []).append(
                f'<text x="{_f(x)}" y="{_f(y)}" font-size="{_f(t.size * k)}" font-family="Helvetica, Arial, sans-serif"'
                f'{rot}>{escape(t.text)}</text>')
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{_f(w / PT_PER_MM)}mm" height="{_f(h / PT_PER_MM)}mm" viewBox="0 0 {_f(w)} {_f(h)}">',
        f'<rect width="{_f(w)}" height="{_f(h)}" fill="#fff"/>',
    ]
    for layer in sorted(groups):
        stroke = f' stroke="#000" stroke-width="{_f(lw)}" stroke-linecap="round" stroke-linejoin="round"'
        out.append(f'<g id="{escape(layer)}" inkscape:groupmode="layer" inkscape:label="{escape(layer)}"{stroke}>')
        out.extend(groups[layer])
        out.append("</g>")
    out.append("</svg>")
    path.write_text("\n".join(out), encoding="utf-8")
    return path
