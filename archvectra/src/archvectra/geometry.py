"""Shared geometry helpers: wall solids (Shapely) and model rasterisation."""

from __future__ import annotations

import math

import cv2
import numpy as np
from shapely import LineString, MultiPolygon
from shapely import Polygon as ShPolygon
from shapely import unary_union

from .model import Drawing, Polygon, Segment


def wall_footprint(walls: list[Segment]):
    """Union of wall bodies.  Ends that are joined to another wall are extended by
    half the thickness so L/T corners close; free ends (jambs) stay exactly where
    they were measured."""
    shapes = []
    for w in walls:
        if w.length < 1e-6:
            continue
        p, q = np.array([w.x1, w.y1]), np.array([w.x2, w.y2])
        u = (q - p) / np.linalg.norm(q - p)
        if "joint_0" in w.attrs:
            p = p - u * w.thickness / 2
        if "joint_1" in w.attrs:
            q = q + u * w.thickness / 2
        shapes.append(LineString([tuple(p), tuple(q)]).buffer(w.thickness / 2, cap_style="flat", join_style="mitre"))
    if not shapes:
        return None
    return unary_union(shapes)


def as_polygons(geom) -> list[ShPolygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, ShPolygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, ShPolygon)]


def wall_polygons(drawing: Drawing) -> list[Polygon]:
    out = []
    for poly in as_polygons(wall_footprint(drawing.walls())):
        out.append(Polygon([tuple(c) for c in poly.exterior.coords[:-1]],
                           [[tuple(c) for c in r.coords[:-1]] for r in poly.interiors],
                           "A-WALL", True, 1.0, "wall-union"))
    return out


def rasterize(drawing: Drawing, shape: tuple[int, int], include_annotation: bool = True,
              line_px: float | None = None) -> np.ndarray:
    """Draw the model into a binary mask (1 = ink) in the working frame."""
    h, w = shape
    sub = 4  # fixed-point sub-pixel precision
    mask = np.zeros((h, w), np.uint8)

    def pts(seq):
        return (np.array(seq, dtype=np.float64) * sub).round().astype(np.int32)

    for poly in wall_polygons(drawing):
        cv2.fillPoly(mask, [pts(poly.exterior)], 1, shift=2)
        for hole in poly.holes:
            cv2.fillPoly(mask, [pts(hole)], 0, shift=2)
    for poly in drawing.polygons:
        if poly.layer.startswith("A-ANNO") and not include_annotation:
            continue
        cv2.fillPoly(mask, [pts(poly.exterior)], 1, shift=2)
        for hole in poly.holes:
            cv2.fillPoly(mask, [pts(hole)], 0, shift=2)
    for s in drawing.segments:
        if s.kind == "wall":
            continue
        t = max(1, int(round(line_px if line_px else s.thickness)))
        cv2.line(mask, tuple(pts([(s.x1, s.y1)])[0]), tuple(pts([(s.x2, s.y2)])[0]), 1, t, shift=2)
    for a in drawing.arcs:
        t = max(1, int(round(line_px if line_px else a.thickness)))
        cv2.polylines(mask, [pts(a.points())], False, 1, t, shift=2)
    for pl in drawing.polylines:
        t = max(1, int(round(line_px if line_px else pl.thickness)))
        cv2.polylines(mask, [pts(pl.points)], pl.closed, 1, t, shift=2)
    return mask


def seg_distance(px: float, py: float, s: Segment) -> float:
    ax, ay, bx, by = s.x1, s.y1, s.x2, s.y2
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
