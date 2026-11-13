"""Grid- and dimension-based rectification ("correct the scan / the drawing").

How a plan is built: axes first, columns on the axes, walls on or flush with the
axes, and dimension chains stating the axis spacings.  So:

1. **Axes** are fitted to all their evidence (``grid.py``) - noise is averaged.
2. **Dimension numbers** centred between neighbouring axes are read (OCR) and
   assigned to their span; the overall dimension is used as a cross-check.
3. **Scale**: written value / measured distance for every span, robust median.
   Spans that disagree by more than ``dimension_tolerance`` are flagged (OCR
   error or a drawing that is not to scale) and not used for the scale.
4. **Rectification** (the automated version of "rubber-sheeting with grid
   points"): rotation/shear is removed so axes become exactly perpendicular,
   then a piecewise-linear map along x and along y moves every axis to the
   position given by the written dimensions.  This corrects non-uniform scan
   stretch and, where the drawing itself was drawn inaccurately, makes the
   geometry agree with its dimensions.  Spans without a readable dimension keep
   their measured size (only the average scale is applied there).
5. **Snapping**: walls on / flush with an axis, columns on intersections and the
   axis lines themselves are placed exactly; column sizes are regularised.

Nothing is moved further than ``max_correction_mm``; larger corrections are
reported instead of applied.
"""

from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import ocr
from .grid import Axis, Grid
from .model import (
    LAYER_ANNOTATION,
    LAYER_COLUMN,
    LAYER_GRID,
    LAYER_TEXT,
    Drawing,
    Polygon,
    Segment,
    Text,
)

log = logging.getLogger(__name__)

STANDARD_SCALES = [10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 500, 1000]


@dataclass
class SpanDim:
    orientation: str  # "v" spans between vertical axes (x direction), "h" between horizontal axes
    i: int  # span between axis i and i+1
    measured_px: float
    values: list[float] = field(default_factory=list)  # raw numbers read for this span
    groups: list[ocr.TextGroup] = field(default_factory=list)
    value: float | None = None  # chosen raw value
    real_mm: float | None = None
    status: str = "no-dimension"


# --------------------------------------------------------------------------- reading
def _span_positions(axes: list[Axis], t: float) -> list[float]:
    return [a.at(t) for a in axes]


def read_grid_text(binary: np.ndarray, anno_mask: np.ndarray, grid: Grid, drawing: Drawing,
                   max_per_span: int = 6) -> tuple[list[SpanDim], list[ocr.TextGroup]]:
    """Find and read dimension numbers between axes and labels inside bubbles."""
    mm = drawing.mm
    spans: list[SpanDim] = []
    if not ocr.available():
        return spans, []
    groups = ocr.group_text(anno_mask, max(2, int(round(mm(0.6)))))
    groups = [g for g in groups if mm(1.0) <= min(g.w, g.h) <= mm(9.0) and max(g.w, g.h) <= mm(40.0)]
    walls = drawing.walls()
    if walls:
        bx0 = min(min(s.x1, s.x2) for s in walls)
        bx1 = max(max(s.x1, s.x2) for s in walls)
        by0 = min(min(s.y1, s.y2) for s in walls)
        by1 = max(max(s.y1, s.y2) for s in walls)
    else:
        bx0, bx1, by0, by1 = 0, drawing.width, 0, drawing.height
    read_cache: dict[int, ocr.TextGroup] = {}

    def read(g: ocr.TextGroup, rotations) -> ocr.TextGroup:
        key = id(g)
        if key not in read_cache:
            read_cache[key] = ocr.read_group(binary, g, rotations, ocr.NUMBER_RE)
            read_cache[key].value = ocr.parse_number(read_cache[key].text)
        return read_cache[key]

    for orient, axes in (("v", grid.v), ("h", grid.h)):
        for i in range(len(axes) - 1):
            a0, a1 = axes[i], axes[i + 1]
            sd = SpanDim(orient, i, float(a1.mid - a0.mid))
            cands = []
            for g in groups:
                t = g.cy if orient == "v" else g.cx  # position along the axes
                c = g.cx if orient == "v" else g.cy  # position across the axes
                p0, p1 = a0.at(t), a1.at(t)
                span = p1 - p0
                if span <= 0 or abs(c - (p0 + p1) / 2) > 0.2 * span:
                    continue
                horizontal = g.w >= 0.8 * g.h
                if (orient == "v") != horizontal and min(g.w, g.h) > mm(2.0) and max(g.w, g.h) > 1.6 * min(g.w, g.h):
                    continue  # text runs the wrong way for this chain
                outside = (t < (by0 if orient == "v" else bx0)) or (t > (by1 if orient == "v" else bx1))
                cands.append((0 if outside else 1, abs(c - (p0 + p1) / 2) / span, g))
            cands.sort(key=lambda r: (r[0], r[1]))
            for _, _, g in cands[:max_per_span]:
                rots = (0,) if orient == "v" else (90, -90, 0)
                r = read(g, rots)
                if r.value is not None and r.score >= 0.5:
                    sd.values.append(r.value)
                    sd.groups.append(r)
            spans.append(sd)
    # bubble labels
    labels: list[ocr.TextGroup] = []
    for ax in grid.v + grid.h:
        if not ax.bubble:
            continue
        cx, cy, r = ax.bubble
        # read only the inside of the bubble: the circle itself confuses the recogniser
        x0, y0, x1, y1 = int(cx - r), int(cy - r), int(cx + r) + 1, int(cy + r) + 1
        sub = binary[max(y0, 0):y1, max(x0, 0):x1].copy()
        yy, xx = np.mgrid[max(y0, 0):y1, max(x0, 0):x1]
        sub[(xx - cx) ** 2 + (yy - cy) ** 2 > (0.72 * r) ** 2] = 0
        ys_, xs_ = np.nonzero(sub)
        if not len(xs_):
            continue
        tight = sub[ys_.min():ys_.max() + 1, xs_.min():xs_.max() + 1]
        g = ocr.TextGroup(0, 0, tight.shape[1], tight.shape[0])
        g = ocr.read_group(np.pad(tight, 2), ocr.TextGroup(2, 2, tight.shape[1], tight.shape[0]), (0,), ocr.LABEL_RE)
        g.x, g.y = int(max(x0, 0) + xs_.min()), int(max(y0, 0) + ys_.min())
        if g.text and g.score >= 0.4:
            ax.label = g.text.upper()
            labels.append(g)
    for axes in (grid.v, grid.h):
        infer_labels(axes)
    return spans, labels


def infer_labels(axes: list[Axis]) -> int:
    """Fill unread grid labels from the sequence (1,2,?,4 -> 3 ; B,?,D -> C).

    Only when every read label agrees with one consistent sequence."""
    known = [(i, a.label) for i, a in enumerate(axes) if a.label]
    if len(known) < 2:
        return 0

    def code(lbl):
        if lbl.isdigit():
            return ("n", int(lbl))
        if len(lbl) == 1 and lbl.isalpha():
            return ("a", ord(lbl.upper()) - ord("A"))
        return None

    codes = [(i, code(lbl)) for i, lbl in known]
    if any(c is None for _, c in codes) or len({c[0] for _, c in codes}) != 1:
        return 0
    kind = codes[0][1][0]
    offs = {c[1] - i for i, c in codes}
    step = 1
    if len(offs) != 1:  # maybe numbered against the axis order
        offs = {c[1] + i for i, c in codes}
        step = -1
        if len(offs) != 1:
            return 0
    off = offs.pop()
    n = 0
    for i, a in enumerate(axes):
        if a.label:
            continue
        v = off + step * i
        if v < (1 if kind == "n" else 0):
            continue
        a.label = str(v) if kind == "n" else chr(ord("A") + v)
        a.evidence["label_inferred"] = True
        n += 1
    return n


# --------------------------------------------------------------------------- scale
def choose_scale(spans: list[SpanDim], paper_mm_per_px: float, nominal_mm_per_px: float | None,
                 tol: float) -> dict[str, Any]:
    """Pick the unit of the written numbers and the mm-per-pixel scale by consensus."""
    for sd in spans:
        if sd.values:
            vals, counts = np.unique(np.round(sd.values, 3), return_counts=True)
            sd.value = float(vals[np.argmax(counts)])
    have = [sd for sd in spans if sd.value and sd.measured_px > 0]
    if not have:
        return {"mm_per_px": None, "unit": None, "used": 0}
    best = None
    for unit, name in ((1.0, "mm"), (10.0, "cm"), (1000.0, "m")):
        ratios = np.array([sd.value * unit / sd.measured_px for sd in have])
        med = float(np.median(ratios))
        if nominal_mm_per_px:
            err = abs(math.log(med / nominal_mm_per_px))
        else:
            den = med / paper_mm_per_px
            err = min(abs(math.log(den / s)) for s in STANDARD_SCALES)
        # structural grid spans are practically always 1.2 - 18 m: this separates e.g.
        # "6000 mm at 1:100" from "6000 cm at 1:1000", which fit standard scales equally well
        span_m = float(np.median([sd.value * unit for sd in have])) / 1000.0
        if not 1.2 <= span_m <= 18.0:
            err += 2.0
        if best is None or err < best[0]:
            best = (err, unit, name, med, ratios)
    _, unit, name, med, ratios = best
    inl = np.abs(ratios / med - 1) <= tol
    if inl.sum() >= 1:
        med = float(np.median(ratios[inl]))
    for sd, r, ok in zip(have, ratios, inl):
        sd.real_mm = sd.value * unit
        sd.status = "used" if ok else "disagrees"
    return {"mm_per_px": med, "unit": name, "unit_factor": unit, "used": int(inl.sum()),
            "rejected": int((~inl).sum()), "denominator": med / paper_mm_per_px,
            "ratio_spread": float(np.ptp(ratios[inl]) / med) if inl.sum() > 1 else 0.0}


# --------------------------------------------------------------------------- transform
@dataclass
class GridTransform:
    bx: float  # shear removal: x1 = x - bx * y
    dy: float  # rotation of horizontals: y1 = y - dy * x
    px: np.ndarray  # observed (de-sheared) axis positions along x
    X: np.ndarray  # target positions
    py: np.ndarray
    Y: np.ndarray

    def __call__(self, x, y):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        x1 = x - self.bx * y
        y1 = y - self.dy * x
        return _interp(x1, self.px, self.X), _interp(y1, self.py, self.Y)

    def local_scale(self, x, y) -> float:
        e = 5.0
        x0, y0 = self(x, y)
        x1, _ = self(x + e, y)
        _, y1 = self(x, y + e)
        return float(math.sqrt(abs((x1 - x0) / e * (y1 - y0) / e)))


def _interp(v, p, P):
    """Piecewise-linear map through (p, P) with linear extrapolation."""
    if len(p) == 1:
        return v + (P[0] - p[0])
    out = np.interp(v, p, P)
    lo, hi = v < p[0], v > p[-1]
    s0 = (P[1] - P[0]) / (p[1] - p[0])
    s1 = (P[-1] - P[-2]) / (p[-1] - p[-2])
    out = np.where(lo, P[0] + (v - p[0]) * s0, out)
    out = np.where(hi, P[-1] + (v - p[-1]) * s1, out)
    return out


def build_transform(grid: Grid, spans: list[SpanDim], mm_per_px: float, max_corr_px: float,
                    ym: float, xm: float) -> tuple[GridTransform, dict]:
    bx = float(np.median([a.b for a in grid.v])) if grid.v else 0.0
    dy = float(np.median([a.b for a in grid.h])) if grid.h else 0.0
    info: dict[str, Any] = {"shear_removed_deg": round(math.degrees(math.atan(bx)), 4),
                            "horizontal_tilt_removed_deg": round(math.degrees(math.atan(dy)), 4)}

    def positions(axes, orient, along_mid):
        obs = []
        for a in axes:
            if orient == "v":  # x of axis at mid height, after de-shear
                y = along_mid
                x = a.at(y)
                obs.append(x - bx * y)
            else:
                x = along_mid
                y = a.at(x)
                obs.append(y - dy * x)
        return np.array(obs, float)

    out = {}
    for orient, axes in (("v", grid.v), ("h", grid.h)):
        mid = ym if orient == "v" else xm
        p = positions(axes, orient, mid)
        if len(p) == 0:  # no axes this way: identity
            out[orient] = (np.array([0.0, 1.0]), np.array([0.0, 1.0]))
            info[f"{orient}_axis_shift_max_px"] = 0.0
            continue
        order = np.argsort(p)
        p = p[order]
        T = [p[0]]
        corrections = []
        for i in range(len(p) - 1):
            sd = next((s for s in spans if s.orientation == orient and s.i == i), None)
            meas = p[i + 1] - p[i]
            if sd is not None and sd.status == "used":
                target = sd.real_mm / mm_per_px
                if abs(target - meas) > max_corr_px:
                    sd.status = "correction-too-large"
                    target = meas
            else:
                target = meas
            corrections.append(target - meas)
            T.append(T[-1] + target)
        T = np.array(T)
        # keep the grid centred where it was (distribute the change symmetrically)
        T += (p.mean() - T.mean())
        out[orient] = (p, T)
        info[f"{orient}_axis_shift_max_px"] = round(float(np.max(np.abs(T - p))) if len(p) else 0.0, 2)
    tr = GridTransform(bx, dy, out["v"][0], out["v"][1], out["h"][0], out["h"][1])
    return tr, info


def apply_transform(drawing: Drawing, tr: GridTransform) -> None:
    def P(pts):  # noqa: N802
        if not pts:
            return pts
        a = np.asarray(pts, float)
        x, y = tr(a[:, 0], a[:, 1])
        return [(float(u), float(v)) for u, v in zip(x, y)]

    if drawing.segments:
        a = np.array([[s.x1, s.y1, s.x2, s.y2] for s in drawing.segments], float)
        x1, y1 = tr(a[:, 0], a[:, 1])
        x2, y2 = tr(a[:, 2], a[:, 3])
        for k, s in enumerate(drawing.segments):
            s.x1, s.y1, s.x2, s.y2 = float(x1[k]), float(y1[k]), float(x2[k]), float(y2[k])
    for arc in drawing.arcs:
        k = tr.local_scale(arc.cx, arc.cy)
        (arc.cx, arc.cy), = P([(arc.cx, arc.cy)])
        arc.r *= k
    for poly in drawing.polygons + drawing.rooms:
        poly.exterior = P(poly.exterior)
        poly.holes = [P(h) for h in poly.holes]
    for pl in drawing.polylines:
        pl.points = P(pl.points)
    for t in drawing.texts:
        (t.x, t.y), = P([(t.x, t.y)])
    for o in drawing.openings:
        o.p1, o.p2 = P([o.p1, o.p2])
        o.width = math.dist(o.p1, o.p2)
    for f in drawing.flags:
        (f.x, f.y), = P([(f.x, f.y)])


# --------------------------------------------------------------------------- snapping
def snap_to_grid(drawing: Drawing, X: np.ndarray, Y: np.ndarray, snap_px: float, col_snap_px: float,
                 grid: Grid) -> dict:
    stats = {"walls_on_axis": 0, "walls_flush": 0, "columns_snapped": 0, "lines_on_axis": 0}
    for s in drawing.segments:
        if s.kind not in ("wall", "line", "wall-edge"):
            continue
        d = abs(s.angle - 90)
        if d <= 1.0:  # vertical
            x = (s.x1 + s.x2) / 2
            targets = [(v, "on") for v in X]
            if s.kind == "wall":
                targets += [(v + sgn * s.thickness / 2, "flush") for v in X for sgn in (-1, 1)]
            best = min(targets, key=lambda t: abs(t[0] - x)) if targets else None
            tol = snap_px if s.kind == "wall" else snap_px * 0.4
            if best and abs(best[0] - x) <= tol:
                s.x1 = s.x2 = float(best[0])
                stats["walls_on_axis" if s.kind == "wall" and best[1] == "on" else
                      "walls_flush" if s.kind == "wall" else "lines_on_axis"] += 1
        elif min(s.angle, 180 - s.angle) <= 1.0:  # horizontal
            y = (s.y1 + s.y2) / 2
            targets = [(v, "on") for v in Y]
            if s.kind == "wall":
                targets += [(v + sgn * s.thickness / 2, "flush") for v in Y for sgn in (-1, 1)]
            best = min(targets, key=lambda t: abs(t[0] - y)) if targets else None
            tol = snap_px if s.kind == "wall" else snap_px * 0.4
            if best and abs(best[0] - y) <= tol:
                s.y1 = s.y2 = float(best[0])
                stats["walls_on_axis" if s.kind == "wall" and best[1] == "on" else
                      "walls_flush" if s.kind == "wall" else "lines_on_axis"] += 1
        # wall ends close to a perpendicular axis are placed on it
        if s.kind == "wall":
            for end in (0, 1):
                ex, ey = (s.x1, s.y1) if end == 0 else (s.x2, s.y2)
                if abs(s.angle - 90) <= 1.0 and len(Y):
                    v = Y[np.argmin(np.abs(Y - ey))]
                    if abs(v - ey) <= snap_px:
                        if end == 0:
                            s.y1 = float(v)
                        else:
                            s.y2 = float(v)
                elif min(s.angle, 180 - s.angle) <= 1.0 and len(X):
                    v = X[np.argmin(np.abs(X - ex))]
                    if abs(v - ex) <= snap_px:
                        if end == 0:
                            s.x1 = float(v)
                        else:
                            s.x2 = float(v)
    # columns: centre on intersections, regular size per size family
    cols = [p for p in drawing.polygons if p.layer == LAYER_COLUMN]
    sizes = []
    for p in cols:
        xs = [q[0] for q in p.exterior]
        ys = [q[1] for q in p.exterior]
        sizes.append((max(xs) - min(xs), max(ys) - min(ys)))
    if cols:
        w_med = float(np.median([s[0] for s in sizes]))
        h_med = float(np.median([s[1] for s in sizes]))
        for p, (w, h) in zip(cols, sizes):
            cx = (max(q[0] for q in p.exterior) + min(q[0] for q in p.exterior)) / 2
            cy = (max(q[1] for q in p.exterior) + min(q[1] for q in p.exterior)) / 2
            if not (len(X) and len(Y)):
                continue
            gx, gy = X[np.argmin(np.abs(X - cx))], Y[np.argmin(np.abs(Y - cy))]
            if math.hypot(gx - cx, gy - cy) <= col_snap_px:
                w2 = w_med if abs(w / w_med - 1) <= 0.15 else w
                h2 = h_med if abs(h / h_med - 1) <= 0.15 else h
                p.exterior = [(gx - w2 / 2, gy - h2 / 2), (gx + w2 / 2, gy - h2 / 2), (gx + w2 / 2, gy + h2 / 2),
                              (gx - w2 / 2, gy + h2 / 2)]
                p.holes = []
                p.attrs["snapped_to_grid"] = True
                stats["columns_snapped"] += 1
    # walls that stop at a column are connected to the column centre (structural joint)
    boxes = []
    for p in drawing.polygons:
        if p.layer == LAYER_COLUMN:
            xs = [q[0] for q in p.exterior]
            ys = [q[1] for q in p.exterior]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
    stats["wall_ends_joined_to_columns"] = 0
    for s in drawing.walls():
        for end in (0, 1):
            ex, ey = (s.x1, s.y1) if end == 0 else (s.x2, s.y2)
            for x0, y0, x1, y1 in boxes:
                m = s.thickness * 0.5
                if x0 - m <= ex <= x1 + m and y0 - m <= ey <= y1 + m:
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                    if abs(s.angle - 90) <= 1.0:
                        cx = s.x1  # keep the wall straight; move along its own axis only
                    elif min(s.angle, 180 - s.angle) <= 1.0:
                        cy = s.y1
                    if end == 0:
                        s.x1, s.y1 = float(cx), float(cy)
                    else:
                        s.x2, s.y2 = float(cx), float(cy)
                    s.attrs[f"joint_{end}"] = "column"
                    stats["wall_ends_joined_to_columns"] += 1
                    break
    # 'free wall end' flags inside a column are resolved
    drawing.flags = [f for f in drawing.flags if not (f.code == "free-wall-end" and any(
        x0 - 2 <= f.x <= x1 + 2 and y0 - 2 <= f.y <= y1 + 2 for x0, y0, x1, y1 in boxes))]
    return stats


def complete_columns(binary: np.ndarray, grid: Grid, min_share: float = 0.6, fill: float = 0.85) -> int:
    """Use the grid pattern: if most intersections carry a column, look at the empty ones in the
    scan and add a column where the ink there is solid (missed by the detector, e.g. scan nicks).
    Evidence is required - nothing is added on a blank intersection."""
    if len(grid.columns) < 4:
        return 0
    pts = grid.intersections()
    w = float(np.median([c.w for c in grid.columns]))
    h = float(np.median([c.h for c in grid.columns]))
    have = [p for p in pts if any(math.hypot(c.cx - p[2], c.cy - p[3]) < max(w, h) / 2 for c in grid.columns)]
    if len(have) < min_share * len(pts):
        return 0
    n = 0
    H, W = binary.shape
    for i, j, x, y in pts:
        if any(math.hypot(c.cx - x, c.cy - y) < max(w, h) / 2 for c in grid.columns):
            continue
        x0, x1 = int(round(x - w * 0.4)), int(round(x + w * 0.4))
        y0, y1 = int(round(y - h * 0.4)), int(round(y + h * 0.4))
        if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
            continue
        if binary[y0:y1, x0:x1].mean() >= fill:
            from .grid import Column

            grid.columns.append(Column(float(x), float(y), w, h, "grid-pattern"))
            n += 1
    return n


def add_columns(drawing: Drawing, grid: Grid) -> int:
    """Columns found by the grid detector but missing from the model become A-COLS polygons."""
    existing = []
    for p in drawing.polygons:
        if p.layer == LAYER_COLUMN:
            xs = [q[0] for q in p.exterior]
            ys = [q[1] for q in p.exterior]
            existing.append(((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2))
    n = 0
    for c in grid.columns:
        if any(math.hypot(c.cx - x, c.cy - y) < max(c.w, c.h) / 2 for x, y in existing):
            continue
        hw, hh = c.w / 2, c.h / 2
        drawing.polygons.append(Polygon([(c.cx - hw, c.cy - hh), (c.cx + hw, c.cy - hh), (c.cx + hw, c.cy + hh),
                                         (c.cx - hw, c.cy + hh)], [], LAYER_COLUMN, True, 0.85, "grid-column"))
        n += 1
    return n


def draw_axes(drawing: Drawing, grid: Grid, X: np.ndarray, Y: np.ndarray, ext_px: float) -> int:
    """Replace the traced axis pieces with exact axis lines on S-GRID (+ bubble labels as text)."""
    drop = set()
    for ax in grid.v + grid.h:
        drop.update(ax.segments)
    keep = [s for k, s in enumerate(drawing.segments) if k not in drop]
    n = 0
    k = 72.0 / drawing.dpi  # working units -> pt (approximately) for the dash pattern
    style = {"stroke": (0.0, 0.0, 0.0), "fill": None, "width": 0.18 * 72 / 25.4,
             "dashes": f"[ {12 / k * k:.2f} 3 2 3 ] 0"}
    xs_lo = min(Y) - ext_px if len(Y) else 0
    xs_hi = max(Y) + ext_px if len(Y) else drawing.height
    ys_lo = min(X) - ext_px if len(X) else 0
    ys_hi = max(X) + ext_px if len(X) else drawing.width
    for v, ax in zip(X, grid.v):
        keep.append(Segment(float(v), float(xs_lo), float(v), float(xs_hi), 1.0, "axis", LAYER_GRID, ax.confidence,
                            "grid-axis", attrs={"label": ax.label or "", "style": style}))
        n += 1
    for v, ax in zip(Y, grid.h):
        keep.append(Segment(float(ys_lo), float(v), float(ys_hi), float(v), 1.0, "axis", LAYER_GRID, ax.confidence,
                            "grid-axis", attrs={"label": ax.label or "", "style": style}))
        n += 1
    drawing.segments = keep
    return n


def replace_text(drawing: Drawing, groups: list[ocr.TextGroup], tr: GridTransform | None) -> int:
    """Readable numbers / labels become real text; their traced outlines are removed."""
    n = 0
    for g in groups:
        if not g.text:
            continue
        x0, y0, x1, y1 = g.x, g.y, g.x + g.w, g.y + g.h
        # remove annotation outlines whose centre lies in the group's box (still in the old frame)
        g.attrs["box"] = (x0, y0, x1, y1)
        height = min(g.w, g.h) if g.angle else g.h
        cx, cy = g.cx, g.cy
        if tr is not None:
            (cx,), (cy,) = (np.atleast_1d(v) for v in tr(cx, cy))
        if g.angle == 90:  # reads bottom-to-top
            bx, by, ang = cx + height * 0.4, cy + len(g.text) * height * 0.3, 90.0
        elif g.angle == -90:
            bx, by, ang = cx - height * 0.4, cy - len(g.text) * height * 0.3, -90.0
        else:
            bx, by, ang = cx - len(g.text) * height * 0.3, cy + height * 0.4, 0.0
        drawing.texts.append(Text(float(bx), float(by), g.text, float(height), ang, LAYER_TEXT, "ocr"))
        n += 1
    return n


def remove_outlines_in_boxes(drawing: Drawing, boxes: list[tuple[float, float, float, float]]) -> int:
    if not boxes:
        return 0
    keep, n = [], 0
    for p in drawing.polygons:
        if p.layer == LAYER_ANNOTATION:
            cx = sum(q[0] for q in p.exterior) / len(p.exterior)
            cy = sum(q[1] for q in p.exterior) / len(p.exterior)
            if any(x0 - 2 <= cx <= x1 + 2 and y0 - 2 <= cy <= y1 + 2 for x0, y0, x1, y1 in boxes):
                n += 1
                continue
        keep.append(p)
    drawing.polygons = keep
    return n


__all__ = ["read_grid_text", "choose_scale", "build_transform", "apply_transform", "snap_to_grid",
           "add_columns", "draw_axes", "replace_text", "remove_outlines_in_boxes", "SpanDim", "copy"]
