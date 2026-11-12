"""Coordinate transforms and primitive collection shared by all exporters."""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import wall_polygons
from ..model import LAYER_TEXT, LAYER_WALL_CENTER, Drawing, Polygon

PT_PER_MM = 72.0 / 25.4


@dataclass
class Frame:
    """Maps working-frame coordinates to PDF points (y down) and CAD millimetres (y up)."""

    drawing: Drawing

    def pt(self, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.drawing.px_to_pt
        return a * x + c * y + e, b * x + d * y + f

    @property
    def unit_to_pt(self) -> float:
        a, b, c, d, *_ = self.drawing.px_to_pt
        return (abs(a * d - b * c)) ** 0.5

    @property
    def cad_factor(self) -> float:
        """CAD mm per sheet mm (the scale denominator when calibrated, else 1)."""
        sc = self.drawing.scale
        return sc.mm_per_unit / sc.paper_mm_per_unit if sc.calibrated else 1.0

    def cad(self, x: float, y: float) -> tuple[float, float]:
        px, py = self.pt(x, y)
        h = self.drawing.page_size_pt[1]
        k = self.cad_factor / PT_PER_MM
        return px * k, (h - py) * k

    def cad_len(self, v: float) -> float:
        return v * self.unit_to_pt / PT_PER_MM * self.cad_factor


def parse_dashes(dashes: str | None) -> list[float] | None:
    """PyMuPDF dash string '[ 3 2 ] 0' -> [3.0, 2.0]; None for solid."""
    if not dashes or "[" not in dashes:
        return None
    inner = dashes[dashes.index("[") + 1:dashes.index("]")].split()
    vals = [float(v) for v in inner if v]
    return vals if vals and any(v > 0 for v in vals) else None


def stroke_style(item, preserve: bool, default_width: float):
    """(rgb or None, width_pt, PDF dash string or None) for a line-like item."""
    st = item.attrs.get("style") if preserve and hasattr(item, "attrs") else None
    if not st:
        return None, default_width, None
    color = tuple(st["stroke"]) if st.get("stroke") else None
    width = float(st.get("width") or 0.0)
    return color, max(width, 0.1), st.get("dashes") if parse_dashes(st.get("dashes")) else None


def fill_style(poly, preserve: bool):
    st = poly.attrs.get("style") if preserve else None
    return tuple(st["fill"]) if st and st.get("fill") else None


def collect_polygons(drawing: Drawing) -> list[Polygon]:
    return wall_polygons(drawing) + list(drawing.polygons)


__all__ = ["Frame", "collect_polygons", "PT_PER_MM", "LAYER_TEXT", "LAYER_WALL_CENTER"]
