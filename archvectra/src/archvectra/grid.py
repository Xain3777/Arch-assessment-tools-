"""Structural grid (axes / محاور) and columns.

Architectural and structural plans are organised on a grid of reference axes,
lettered one way and numbered the other, labelled in bubbles at the axis ends
outside the building; columns sit on the grid intersections and dimension chains
give the axis spacings.  These conventions are strong, drawing-independent
priors, so the grid is used as the drawing's skeleton:

* axes are found from long straight (often dash-dot, chained) lines, from rows /
  columns of columns, and from bubbles at line ends;
* each axis is *fitted* by least squares to all its evidence (line pieces and
  column centres), which averages out scan noise;
* intersections become control points for rectification (``rectify.py``).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .model import Arc, Drawing, Segment

log = logging.getLogger(__name__)


@dataclass
class Axis:
    orientation: str  # "v": x = a + b*y ; "h": y = a + b*x
    a: float
    b: float
    lo: float  # extent along the axis (y-range for v, x-range for h)
    hi: float
    evidence: dict = field(default_factory=dict)
    label: str | None = None
    bubble: tuple[float, float, float] | None = None  # (cx, cy, r)
    confidence: float = 0.5
    segments: list[int] = field(default_factory=list)  # indices into drawing.segments

    def at(self, t: float) -> float:
        """Perpendicular coordinate at position t along the axis."""
        return self.a + self.b * t

    @property
    def mid(self) -> float:
        return self.at((self.lo + self.hi) / 2)


@dataclass
class Column:
    cx: float
    cy: float
    w: float
    h: float
    source: str = "raster"


@dataclass
class Grid:
    v: list[Axis] = field(default_factory=list)
    h: list[Axis] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)

    def intersections(self) -> list[tuple[int, int, float, float]]:
        out = []
        for i, av in enumerate(self.v):
            for j, ah in enumerate(self.h):
                # x = av.a + av.b*y ; y = ah.a + ah.b*x
                den = 1 - av.b * ah.b
                if abs(den) < 1e-9:
                    continue
                x = (av.a + av.b * ah.a) / den
                y = ah.a + ah.b * x
                out.append((i, j, x, y))
        return out


# --------------------------------------------------------------------------- columns
def detect_columns(geom: np.ndarray, dpi: float, wall_t_px: float, min_mm: float = 1.5,
                   max_mm: float = 12.0) -> list[Column]:
    """Solid, compact blobs clearly thicker than the walls (columns embedded in walls included)."""
    pxmm = dpi / 25.4
    k = int(math.ceil(max(1.35 * wall_t_px, min_mm * pxmm)))
    if k < 3 or not geom.any():
        return []
    core = cv2.morphologyEx(geom, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    n, lab, st, cent = cv2.connectedComponentsWithStats(core, connectivity=8)
    cols = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if max(w, h) > max_mm * pxmm or min(w, h) < k:
            continue
        if max(w, h) / max(min(w, h), 1) > 1.8 or area / max(w * h, 1) < 0.8:
            continue
        cols.append(Column(float(cent[i][0]), float(cent[i][1]), float(w), float(h)))
    return cols


# --------------------------------------------------------------------------- axes
def _fit(points: np.ndarray, weights: np.ndarray, orientation: str) -> tuple[float, float]:
    """Weighted LSQ: x = a + b*y (v) or y = a + b*x (h)."""
    t = points[:, 1] if orientation == "v" else points[:, 0]
    c = points[:, 0] if orientation == "v" else points[:, 1]
    if len(points) < 2 or np.ptp(t) < 1e-6:
        return float(np.average(c, weights=weights)), 0.0
    A = np.column_stack([np.ones_like(t), t]) * np.sqrt(weights)[:, None]
    sol, *_ = np.linalg.lstsq(A, c * np.sqrt(weights), rcond=None)
    return float(sol[0]), float(sol[1])


def _bubbles(drawing: Drawing) -> list[tuple[float, float, float]]:
    """Grid bubbles: circles of 2-9 mm radius (arcs split by noise are recombined)."""
    mm = drawing.mm
    arcs = [a for a in drawing.arcs if mm(2.0) <= a.r <= mm(9.0)]
    groups: list[list[Arc]] = []
    for a in arcs:
        for g in groups:
            if math.hypot(g[0].cx - a.cx, g[0].cy - a.cy) <= mm(0.6) and abs(g[0].r - a.r) <= mm(0.6):
                g.append(a)
                break
        else:
            groups.append([a])
    out = []
    for g in groups:
        if sum(a.sweep for a in g) >= 300:
            out.append((float(np.mean([a.cx for a in g])), float(np.mean([a.cy for a in g])),
                        float(np.mean([a.r for a in g]))))
    return out


def detect_axes(drawing: Drawing, columns: list[Column], min_len_frac: float = 0.35, merge_mm: float = 1.5,
                angle_tol: float = 3.0) -> Grid:
    mm = drawing.mm
    segs = drawing.segments
    walls = [s for s in segs if s.kind == "wall"]
    ref = walls if walls else segs
    if not ref:
        return Grid(columns=columns)
    xs = [v for s in ref for v in (s.x1, s.x2)] + [c.cx for c in columns]
    ys = [v for s in ref for v in (s.y1, s.y2)] + [c.cy for c in columns]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)  # building extent
    ext_x, ext_y = bx1 - bx0, by1 - by0
    margin = mm(3.0)
    bubbles = _bubbles(drawing)
    grid = Grid(columns=columns)
    for orient in ("v", "h"):
        ext = ext_y if orient == "v" else ext_x
        lo_b, hi_b = (bx0, bx1) if orient == "v" else (by0, by1)  # range of axis positions
        cands: list[dict] = []
        for k, s in enumerate(segs):
            if s.kind == "wall":
                continue
            ang = s.angle
            dev = abs(ang - 90) if orient == "v" else min(ang, 180 - ang)
            if dev > angle_tol or s.length < min_len_frac * ext:
                continue
            pos = (s.x1 + s.x2) / 2 if orient == "v" else (s.y1 + s.y2) / 2
            if not lo_b - margin <= pos <= hi_b + margin:
                continue  # outside the building: dimension line, border, title block
            cands.append({"pos": pos, "seg": k, "len": s.length})
        for c in columns:
            cands.append({"pos": c.cx if orient == "v" else c.cy, "col": c})
        for bc in bubbles:
            cx, cy, r = bc
            if orient == "v" and (cy < by0 or cy > by1) and bx0 - margin <= cx <= bx1 + margin:
                cands.append({"pos": cx, "bubble": bc})
            if orient == "h" and (cx < bx0 or cx > bx1) and by0 - margin <= cy <= by1 + margin:
                cands.append({"pos": cy, "bubble": bc})
        cands.sort(key=lambda d: d["pos"])
        clusters: list[list[dict]] = []
        for c in cands:
            if clusters and c["pos"] - clusters[-1][-1]["pos"] <= mm(merge_mm):
                clusters[-1].append(c)
            else:
                clusters.append([c])
        axes = []
        for cl in clusters:
            lines = [c for c in cl if "seg" in c]
            cols = [c["col"] for c in cl if "col" in c]
            bubs = [c["bubble"] for c in cl if "bubble" in c]
            line_len = sum(c["len"] for c in lines)
            if not (bubs or (lines and cols) or len(cols) >= 3 or line_len >= 0.7 * ext):
                continue
            pts, wts, lo, hi = [], [], [], []
            for c in lines:
                s = segs[c["seg"]]
                for p in ((s.x1, s.y1), ((s.x1 + s.x2) / 2, (s.y1 + s.y2) / 2), (s.x2, s.y2)):
                    pts.append(p)
                    wts.append(s.length / 3)
                lo.append(min(s.y1, s.y2) if orient == "v" else min(s.x1, s.x2))
                hi.append(max(s.y1, s.y2) if orient == "v" else max(s.x1, s.x2))
            for col in cols:
                pts.append((col.cx, col.cy))
                wts.append(mm(20.0))  # a column centre is strong evidence
                t = col.cy if orient == "v" else col.cx
                lo.append(t)
                hi.append(t)
            for cx, cy, r in bubs:
                pts.append((cx, cy))
                wts.append(mm(8.0))
            if not lo:  # bubble only: span the building
                lo, hi = [by0 if orient == "v" else bx0], [by1 if orient == "v" else bx1]
            a, b = _fit(np.array(pts, float), np.array(wts, float), orient)
            if len(pts) < 3 or (not cols and not lines):
                b = 0.0  # too little evidence for a slope
                a = float(np.average([p[0] if orient == "v" else p[1] for p in pts], weights=wts))
            ax = Axis(orient, a, b, float(min(min(lo), by0 if orient == "v" else bx0)),
                      float(max(max(hi), by1 if orient == "v" else bx1)),
                      {"lines": len(lines), "line_length_px": round(line_len, 1), "columns": len(cols),
                       "bubble": bool(bubs)}, segments=[c["seg"] for c in lines])
            if bubs:
                ax.bubble = bubs[0]
            ax.confidence = min(1.0, 0.3 + 0.12 * len(cols) + 0.3 * min(1.0, line_len / max(ext, 1))
                                + (0.3 if bubs else 0.0))
            axes.append(ax)
        axes.sort(key=lambda a: a.mid)
        if orient == "v":
            grid.v = axes
        else:
            grid.h = axes
    return grid
