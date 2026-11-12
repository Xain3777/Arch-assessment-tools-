"""Stage D / G - architectural interpretation and topology.

Rule-based (no learned model) and evidence-driven:

* **Openings** are searched from every free wall end along the wall axis.  A gap
  whose width is within the configured opening range becomes an opening; the
  gap is *never* filled.  It is classified from nearby thin-line evidence:
  a swing arc centred on a jamb with radius ~ gap width (door), a leaf line
  (door), or glazing lines parallel to the wall inside the gap (window).
  Without evidence it stays an unclassified opening and is flagged.
* **Double-line walls** (unfilled walls) are recognised as pairs of parallel
  thin lines at a wall-like spacing and relabelled - geometry is unchanged.
* **Topology** - wall centrelines + opening chords are noded and polygonised
  with Shapely to give room-boundary candidates; a NetworkX graph reports
  connectivity and dangling ends.
"""

from __future__ import annotations

import logging
import math

import networkx as nx
import numpy as np
from shapely import LineString, polygonize, set_precision, unary_union

from .config import CorrectConfig
from .spatial import SegmentIndex
from .model import LAYER_DOOR, LAYER_GLAZING, LAYER_ROOM, LAYER_WALL, Drawing, Opening, Polygon, Segment

log = logging.getLogger(__name__)


def _uv(s: Segment):
    p, q = np.array([s.x1, s.y1]), np.array([s.x2, s.y2])
    L = float(np.linalg.norm(q - p))
    u = (q - p) / L if L else np.array([1.0, 0.0])
    return p, q, u, np.array([-u[1], u[0]]), L


def _parallel(a: Segment, b: Segment, tol: float = 3.0) -> bool:
    d = abs(a.angle - b.angle) % 180
    return min(d, 180 - d) <= tol


def find_openings(drawing: Drawing, cfg: CorrectConfig) -> None:
    mm = drawing.mm
    walls = drawing.walls()
    thin = [s for s in drawing.segments if s.kind != "wall"]
    omin, omax, gmerge = mm(cfg.opening_min_mm), mm(cfg.opening_max_mm), mm(cfg.merge_gap_mm)
    found: dict[tuple, Opening] = {}
    free_ends = 0
    index = SegmentIndex(walls)
    max_t = max((w.thickness for w in walls), default=0.0)
    for i, w in enumerate(walls):
        p, q, u, n, L = _uv(w)
        for end in (0, 1):
            if f"joint_{end}" in w.attrs:
                continue
            e = p if end == 0 else q
            d = -u if end == 0 else u
            best = None  # (gap, hit point, other wall index, type)
            far_pt = e + d * (omax + max_t)
            cand = index.query(min(e[0], far_pt[0]) - max_t, min(e[1], far_pt[1]) - max_t,
                               max(e[0], far_pt[0]) + max_t, max(e[1], far_pt[1]) + max_t)
            for j in cand:
                o = walls[j]
                if j == i:
                    continue
                op, oq, ou, on, oL = _uv(o)
                if _parallel(w, o):
                    if abs(float((op - e) @ n)) > max(w.thickness, o.thickness) * 0.5:
                        continue  # not collinear
                    for tip in (op, oq):
                        g = float((tip - e) @ d)
                        if g > 0.5 and (best is None or g < best[0]):
                            # the other wall must lie beyond this tip (we look at its near end)
                            far = oq if tip is op else op
                            if float((far - e) @ d) > g:
                                best = (g, tip, j, "collinear", 0.0)
                else:
                    diff = abs(w.angle - o.angle) % 180
                    if min(diff, 180 - diff) < 60:  # oblique hits are not treated as jamb partners
                        continue
                    denom = d[0] * ou[1] - d[1] * ou[0]
                    if abs(denom) < 1e-9:
                        continue
                    qp = op - e
                    t = (qp[0] * ou[1] - qp[1] * ou[0]) / denom
                    s_ = (qp[0] * d[1] - qp[1] * d[0]) / denom
                    if t <= 0 or s_ < -o.thickness / 2 or s_ > oL + o.thickness / 2:
                        continue
                    g = t - o.thickness / 2
                    if g > 0.5 and (best is None or g < best[0]):
                        best = (g, e + d * g, j, "perpendicular", o.thickness / 2)
            if best is None or best[0] > omax:
                free_ends += 1
                drawing.flag(e[0], e[1], "free-wall-end",
                             "wall ends without a joint or an opening partner", "info")
                continue
            g, hit, j, how, to_centre = best
            if g < omin:
                if g > gmerge:
                    drawing.flag(e[0], e[1], "short-gap",
                                 f"gap {g:.1f}px between walls is shorter than the opening range; "
                                 "left open (not merged) - review", "warning")
                continue
            a, b = e, e + d * g
            key = tuple(np.round((a + b) / 2 / 4).astype(int))
            if key in found:
                continue
            op_ = Opening("opening", (float(a[0]), float(a[1])), (float(b[0]), float(b[1])), float(g),
                          float(w.thickness), 0.5, {"found_from": how, "walls": [i, j],
                                                          "partner_half_thickness": float(to_centre)})
            found[key] = op_
    openings = list(found.values())
    for o in openings:
        classify_opening(drawing, o, thin, cfg)
        if o.kind == "opening":
            drawing.flag((o.p1[0] + o.p2[0]) / 2, (o.p1[1] + o.p2[1]) / 2, "unclassified-opening",
                         f"gap of {o.width:.0f}px with no door/window evidence", "warning")
    drawing.openings = openings
    kinds: dict[str, int] = {}
    for o in openings:
        kinds[o.kind] = kinds.get(o.kind, 0) + 1
    drawing.log("openings", found=len(openings), by_kind=kinds, free_wall_ends=free_ends)


def classify_opening(drawing: Drawing, o: Opening, thin: list[Segment], cfg: CorrectConfig) -> None:
    a, b = np.array(o.p1), np.array(o.p2)
    u = (b - a) / max(o.width, 1e-9)
    n = np.array([-u[1], u[0]])
    w = o.width
    # door: swing arc centred near a jamb with radius ~ width
    for k, arc in enumerate(drawing.arcs):
        c = np.array([arc.cx, arc.cy])
        for jamb, other in ((a, b), (b, a)):
            if np.linalg.norm(c - jamb) <= 0.2 * w + o.wall_thickness and \
                    abs(arc.r - w) / w <= cfg.door_arc_radius_tolerance:
                o.kind = "door"
                o.confidence = round(0.6 + 0.35 * arc.confidence, 3)
                o.evidence.update({"swing_arc": k, "hinge": [float(c[0]), float(c[1])]})
                arc.layer = LAYER_DOOR
                break
        if o.kind == "door":
            break
    # door leaf: thin segment from a jamb, roughly perpendicular to the wall, length ~ width
    for s in thin:
        sp, sq, su, sn, sL = _uv(s)
        if abs(sL - w) / w > 0.3 or abs(float(su @ u)) > 0.35:
            continue
        for jamb in (a, b):
            r = 0.2 * w + o.wall_thickness
            if min(np.linalg.norm(sp - jamb), np.linalg.norm(sq - jamb)) <= r:
                s.layer = LAYER_DOOR
                o.evidence["leaf"] = True
                if o.kind != "door":
                    o.kind, o.confidence = "door", 0.7
                else:
                    o.confidence = min(0.98, o.confidence + 0.05)
                break
    if o.kind == "door":
        return
    # window: thin lines parallel to the wall inside the gap rectangle
    glazing = []
    for s in thin:
        sp, sq, su, sn, sL = _uv(s)
        if abs(abs(float(su @ u)) - 1) > 0.01 or sL < 0.6 * w:
            continue
        mid = (sp + sq) / 2
        t = float((mid - a) @ u)
        off = abs(float((mid - a) @ n))
        if 0 <= t <= w and off <= o.wall_thickness * 0.75:
            glazing.append(s)
    if glazing:
        o.kind = "window"
        o.confidence = 0.9 if len(glazing) >= 2 else 0.65
        o.evidence["glazing_lines"] = len(glazing)
        for s in glazing:
            s.layer = LAYER_GLAZING


def pair_double_line_walls(drawing: Drawing, cfg: CorrectConfig) -> int:
    """Relabel pairs of parallel thin lines with wall-like spacing as wall edges."""
    mm = drawing.mm
    lo, hi = mm(cfg.double_wall_min_mm), mm(cfg.double_wall_max_mm)
    min_len = mm(cfg.opening_min_mm)
    lines = [s for s in drawing.segments if s.kind == "line" and s.layer not in (LAYER_GLAZING, LAYER_DOOR)
             and s.length >= min_len]
    pairs = 0
    index = SegmentIndex(lines)
    for i, a in enumerate(lines):
        if a.kind == "wall-edge":
            continue
        ap, aq, au, an, aL = _uv(a)
        cand = index.query(min(a.x1, a.x2) - hi, min(a.y1, a.y2) - hi, max(a.x1, a.x2) + hi, max(a.y1, a.y2) + hi)
        for b in (lines[k] for k in cand if k > i):
            if b.kind == "wall-edge" or not _parallel(a, b, 1.0):
                continue
            bp, bq, *_ = _uv(b)
            dist = abs(float((bp - ap) @ an))
            if not lo <= dist <= hi:
                continue
            t = sorted([float((bp - ap) @ au), float((bq - ap) @ au)])
            overlap = min(aL, t[1]) - max(0.0, t[0])
            if overlap < 0.6 * min(aL, b.length):
                continue
            for s in (a, b):
                s.kind = "wall-edge"
                s.layer = LAYER_WALL
                s.confidence = min(s.confidence, 0.6)
                s.attrs["pair_spacing"] = round(dist, 2)
            pairs += 1
            break
    drawing.log("double_line_walls", pairs=pairs)
    return pairs


def topology(drawing: Drawing) -> dict:
    walls = drawing.walls()
    lines = [LineString([(w.x1, w.y1), (w.x2, w.y2)]) for w in walls if w.length > 0]
    for o in drawing.openings:  # chords close the room outline; extend to the partner wall's centreline
        a, b = np.array(o.p1), np.array(o.p2)
        ext = o.evidence.get("partner_half_thickness", 0.0)
        u = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        lines.append(LineString([tuple(a), tuple(b + u * ext)]))
    lines = [set_precision(ln, 0.05) for ln in lines]
    info: dict = {"walls": len(walls)}
    if not lines:
        drawing.log("topology", **info)
        return info
    noded = unary_union(lines)
    g = nx.Graph()
    for geom in getattr(noded, "geoms", [noded]):
        cs = list(geom.coords)
        for p, q in zip(cs[:-1], cs[1:]):
            a = (round(p[0], 1), round(p[1], 1))
            b = (round(q[0], 1), round(q[1], 1))
            g.add_edge(a, b, length=math.dist(p, q))
    deg = dict(g.degree())
    info.update({
        "graph_nodes": g.number_of_nodes(),
        "graph_edges": g.number_of_edges(),
        "connected_components": nx.number_connected_components(g),
        "dangling_nodes": sum(1 for v in deg.values() if v == 1),
        "junctions": sum(1 for v in deg.values() if v >= 3),
    })
    min_area = drawing.mm(5.0) ** 2  # ignore slivers smaller than 5x5 mm on paper
    rooms = []
    for poly in polygonize(getattr(noded, "geoms", [noded])).geoms:
        if poly.area < min_area:
            continue
        ring = [(float(x), float(y)) for x, y in poly.exterior.coords[:-1]]
        r = Polygon(ring, [], LAYER_ROOM, False, 0.8, "polygonize-centrelines")
        rooms.append(r)
    drawing.rooms = rooms
    info["rooms"] = len(rooms)
    if drawing.scale.calibrated:
        k = drawing.scale.mm_per_unit / 1000.0
        info["room_areas_m2"] = sorted(round(_area(r.exterior) * k * k, 2) for r in rooms)
    drawing.log("topology", **info)
    return info


def _area(ring) -> float:
    a = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2
