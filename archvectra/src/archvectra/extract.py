"""Stage C - geometry extraction from a binary raster.

Strategy (chosen per stroke class rather than one algorithm for everything):

1. **Annotation separation** - isolated small connected components (text,
   symbols, dashes) are set aside and later traced as outlines, so they are
   preserved visually but never turned into CAD lines.
2. **Solid walls** - a morphological opening with a square kernel keeps only
   strokes thicker than ``wall_min_thickness``.  Horizontal and vertical wall
   runs are isolated with directional openings whose length is derived from
   the measured wall thickness (distance transform), then fitted as
   centreline + thickness.  Remaining solid blobs become columns, diagonal
   walls (minimum-area rectangle) or generic solid polygons.
3. **Thin linework** - skeletonised (scikit-image) and traced into pixel
   paths (own graph walker); paths are simplified with Douglas-Peucker
   (OpenCV) and classified as straight segments, circular arcs (algebraic
   circle fit) or polylines, so genuine angled and curved geometry is kept.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import cv2
import numpy as np
from skimage.morphology import skeletonize

from .config import ExtractConfig, mm_to_px
from .model import (
    LAYER_ARC,
    LAYER_COLUMN,
    LAYER_LINE,
    LAYER_SOLID,
    LAYER_WALL,
    Arc,
    Polygon,
    Polyline,
    Segment,
)

log = logging.getLogger(__name__)


@dataclass
class Extraction:
    segments: list[Segment] = field(default_factory=list)
    arcs: list[Arc] = field(default_factory=list)
    polylines: list[Polyline] = field(default_factory=list)
    polygons: list[Polygon] = field(default_factory=list)
    annotation_mask: np.ndarray | None = None
    wall_mask: np.ndarray | None = None
    thin_mask: np.ndarray | None = None
    stats: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- helpers
def _kernel(w: int, h: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, w), max(1, h)))


def separate_annotation(binary: np.ndarray, max_size_px: float, min_solid_px: float,
                        frag: tuple[float, float, float] | None = None):
    """Split ink into (geometry, annotation[, fragments]) by connected-component size.

    Small isolated components are annotation (text, symbols) unless they are solid
    blobs at least ``min_solid_px`` thick (columns, piers).  With ``frag =
    (min_len_px, max_width_px, min_aspect)`` small *elongated* components are
    returned separately as line fragments (pieces of broken lines / dashes); they
    are chained into continuous lines later, and only unchained ones fall back
    to annotation.
    """
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    w = stats[:, cv2.CC_STAT_WIDTH]
    h = stats[:, cv2.CC_STAT_HEIGHT]
    area = stats[:, cv2.CC_STAT_AREA]
    big = np.maximum(w, h)
    fill = area / np.maximum(w * h, 1)
    solid = (fill > 0.8) & (np.minimum(w, h) >= min_solid_px)
    is_anno = (big <= max_size_px) & ~solid
    is_anno[0] = False
    fragments: list[Segment] = []
    if frag is not None:
        min_len, max_w, min_aspect = frag
        binary = binary.copy()  # never modify the caller's array
        for i in np.nonzero(is_anno)[0]:
            x, y, ww, hh, a = stats[i]
            if max(ww, hh) < min_len:
                continue
            sub = (labels[y:y + hh, x:x + ww] == i).astype(np.uint8)
            cnts, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE, offset=(int(x), int(y)))
            (cx, cy), (rw, rh), ang = cv2.minAreaRect(max(cnts, key=cv2.contourArea))
            long_, short = max(rw, rh), max(min(rw, rh), 1.0)
            if long_ < min_len or short > max_w or long_ / short < min_aspect:
                continue
            t = math.radians(ang if rw >= rh else ang + 90)
            dx, dy = math.cos(t) * long_ / 2, math.sin(t) * long_ / 2
            fragments.append(Segment(cx - dx, cy - dy, cx + dx, cy + dy, float(min(short, max_w)), "line", LAYER_LINE,
                                     0.8, "raster-fragment", attrs={"fragment": True}))
            is_anno[i] = False
            binary[y:y + hh, x:x + ww][sub > 0] = 0  # handled as a fragment, not traced again
    anno = is_anno[labels].astype(np.uint8)
    if frag is not None:
        return binary & (1 - anno), anno, fragments
    return binary & (1 - anno), anno


def wall_thickness_px(wall_mask: np.ndarray) -> list[float]:
    """Sample stroke thickness (2 x distance-transform on the skeleton)."""
    if not wall_mask.any():
        return []
    dt = cv2.distanceTransform(wall_mask, cv2.DIST_L2, 5)
    sk = skeletonize(wall_mask.astype(bool))
    vals = 2.0 * dt[sk]
    return [float(v) for v in vals if v > 1]


def _fit_runs(mask: np.ndarray, horizontal: bool, min_len: float, kind: str, layer: str,
              source: str, min_thickness: float = 0.0) -> list[Segment]:
    """Fit axis-aligned centreline segments to the components of a directional mask."""
    segs: list[Segment] = []
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        length = w if horizontal else h
        if length < min_len:
            continue
        sub = labels[y:y + h, x:x + w] == i
        if horizontal:
            runs = sub.sum(axis=0).astype(float)  # thickness per column
            ys = np.arange(h)[:, None] + y
            center = float((sub * ys).sum() / max(sub.sum(), 1))
            thick = float(np.median(runs[runs > 0]))
            if thick < min_thickness or length < 2.0 * thick or h > 1.5 * thick + 3:
                continue  # h > thickness: staircase of a diagonal stroke, not a horizontal run
            seg = Segment(float(x), center + 0.5, float(x + w), center + 0.5, thick, kind, layer, 1.0, source)
        else:
            runs = sub.sum(axis=1).astype(float)
            xs = np.arange(w)[None, :] + x
            center = float((sub * xs).sum() / max(sub.sum(), 1))
            thick = float(np.median(runs[runs > 0]))
            if thick < min_thickness or length < 2.0 * thick or w > 1.5 * thick + 3:
                continue
            seg = Segment(center + 0.5, float(y), center + 0.5, float(y + h), thick, kind, layer, 1.0, source)
        # confidence: how well a rectangle explains the component
        fill = area / max(length * thick, 1.0)
        seg.confidence = float(max(0.0, min(1.0, 1.0 - abs(1.0 - fill))))
        seg.attrs["fill_ratio"] = round(float(fill), 3)
        segs.append(seg)
    return segs


# --------------------------------------------------------------------------- walls
def extract_walls(geom: np.ndarray, cfg: ExtractConfig, dpi: float,
                  heal_px: int = 0) -> tuple[list[Segment], list[Polygon], np.ndarray, dict]:
    tmin = max(2, int(round(mm_to_px(cfg.wall_min_thickness_mm, dpi))))
    wall_mask = cv2.morphologyEx(geom, cv2.MORPH_OPEN, _kernel(tmin, tmin))
    # restore wall boundary pixels lost by opening: reconstruct within the original ink
    stats: dict = {"wall_kernel_px": tmin}
    if not wall_mask.any():
        return [], [], wall_mask, stats
    t = wall_thickness_px(wall_mask)
    t95 = float(np.percentile(t, 95)) if t else float(tmin)
    stats["wall_thickness_samples"] = len(t)
    stats["wall_thickness_p50_px"] = round(float(np.median(t)), 2) if t else None
    stats["wall_thickness_p95_px"] = round(t95, 2)
    k = int(math.ceil(t95 * 1.25)) + 1
    min_len = max(k, mm_to_px(cfg.min_line_length_mm, dpi))
    # heal scan nicks no longer than heal_px along each axis (never door-sized gaps)
    hsrc = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, _kernel(heal_px, 1)) if heal_px > 1 else wall_mask
    vsrc = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, _kernel(1, heal_px)) if heal_px > 1 else wall_mask
    hmask = cv2.morphologyEx(hsrc, cv2.MORPH_OPEN, _kernel(k, 1))
    vmask = cv2.morphologyEx(vsrc, cv2.MORPH_OPEN, _kernel(1, k))
    stats["heal_px"] = heal_px
    segs = _fit_runs(hmask, True, min_len, "wall", LAYER_WALL, "raster-wall-h", tmin * 0.8)
    segs += _fit_runs(vmask, False, min_len, "wall", LAYER_WALL, "raster-wall-v", tmin * 0.8)

    # residual solids: columns, diagonal walls, odd shapes
    covered = np.zeros_like(wall_mask)
    for sg in segs:  # rasterise accepted runs only, so rejected stubs stay in the residual
        if sg.orientation == "h":
            y0 = int(round(sg.y1 - sg.thickness / 2))
            covered[max(y0, 0):int(round(sg.y1 + sg.thickness / 2)) + 1, int(sg.x1):int(math.ceil(sg.x2))] = 1
        else:
            x0 = int(round(sg.x1 - sg.thickness / 2))
            covered[int(sg.y1):int(math.ceil(sg.y2)), max(x0, 0):int(round(sg.x1 + sg.thickness / 2)) + 1] = 1
    covered = cv2.dilate(covered & wall_mask, _kernel(3, 3))
    residual = wall_mask & (1 - covered)
    residual = cv2.morphologyEx(residual, cv2.MORPH_OPEN, _kernel(3, 3))
    polys: list[Polygon] = []
    col_max = mm_to_px(cfg.column_max_size_mm, dpi)
    n, labels, st, _ = cv2.connectedComponentsWithStats(residual, connectivity=8)
    n_cols = n_diag = n_solid = 0
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if area < tmin * tmin:
            continue
        comp = (labels[y:y + h, x:x + w] == i).astype(np.uint8)
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE, offset=(int(x), int(y)))
        cnt = max(cnts, key=cv2.contourArea)
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(cnt)
        long_, short = max(rw, rh), min(rw, rh)
        rect_fill = area / max(rw * rh, 1)
        m = 3
        ya, yb, xa, xb = max(y - m, 0), y + h + m, max(x - m, 0), x + w + m
        win = (labels[ya:yb, xa:xb] == i).astype(np.uint8)
        touches_wall = bool((cv2.dilate(win, _kernel(5, 5)) & covered[ya:yb, xa:xb]).any())
        if long_ / max(short, 1) >= 3 and rect_fill > 0.75 and short <= t95 * 1.3:
            # straight diagonal wall
            a = math.radians(ang if rw >= rh else ang + 90)
            dx, dy = math.cos(a) * long_ / 2, math.sin(a) * long_ / 2
            s = Segment(cx - dx, cy - dy, cx + dx, cy + dy, float(short), "wall", LAYER_WALL,
                        float(min(1.0, rect_fill)), "raster-wall-diag")
            segs.append(s)
            n_diag += 1
            continue
        approx = cv2.approxPolyDP(cnt, 1.0, True).reshape(-1, 2)
        ring = [(float(px), float(py)) for px, py in approx]
        if len(ring) < 3:
            continue
        if long_ <= col_max and long_ / max(short, 1) < 2.5 and not touches_wall:
            polys.append(Polygon(ring, [], LAYER_COLUMN, True, float(min(1.0, rect_fill)), "raster-column"))
            n_cols += 1
        else:
            polys.append(Polygon(ring, [], LAYER_SOLID, True, 0.8, "raster-solid"))
            n_solid += 1
    stats.update({"wall_runs": len(segs) - n_diag, "diagonal_walls": n_diag, "columns": n_cols, "solids": n_solid})
    return segs, polys, wall_mask, stats


# --------------------------------------------------------------------------- skeleton tracing
_NEIGH = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def trace_skeleton(skel: np.ndarray) -> list[np.ndarray]:
    """Trace a 1-px skeleton into ordered pixel paths (arrays of (x, y)).

    Vectorised: junction pixels (>= 3 neighbours) are removed, the remaining
    simple curves are labelled with OpenCV and each is ordered with
    ``findContours`` (a 1-px open curve's contour runs out and back, so its first
    half from an end point is the ordered path).  Path ends are then extended to
    the centroid of the junction they touch, keeping the topology.  Linear in the
    number of skeleton pixels and memory-light (no per-pixel Python objects).
    """
    sk = (skel > 0).astype(np.uint8)
    if not sk.any():
        return []
    k = np.ones((3, 3), np.float32)
    k[1, 1] = 0
    deg = cv2.filter2D(sk, cv2.CV_8U, k, borderType=cv2.BORDER_CONSTANT) * sk
    junction = ((deg >= 3) & (sk > 0)).astype(np.uint8)
    edges = sk & (1 - junction)
    n_j, jlab, _, jcent = cv2.connectedComponentsWithStats(junction, connectivity=8)
    n_e, elab, est, _ = cv2.connectedComponentsWithStats(edges, connectivity=8)
    edeg = cv2.filter2D(edges, cv2.CV_8U, k, borderType=cv2.BORDER_CONSTANT) * edges
    H, W = sk.shape
    paths: list[np.ndarray] = []
    for i in range(1, n_e):
        x, y, w, h, area = est[i]
        x0, y0 = max(x - 1, 0), max(y - 1, 0)
        x1, y1 = min(x + w + 1, W), min(y + h + 1, H)
        comp = (elab[y0:y1, x0:x1] == i).astype(np.uint8)
        if area == 1:
            pts = np.array([[x, y]], np.float64)
        else:
            cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            c = max(cnts, key=len).reshape(-1, 2)
            local_deg = edeg[y0:y1, x0:x1]
            ends = [j for j, (cx, cy) in enumerate(c) if local_deg[cy, cx] == 1]
            if ends:  # open curve: walk from one end to the other
                a = ends[0]
                c = np.roll(c, -a, axis=0)
                other = [j for j, (cx, cy) in enumerate(c) if j > 0 and local_deg[cy, cx] == 1]
                c = c[: other[0] + 1] if other else c
            else:  # closed loop
                c = np.vstack([c, c[:1]])
            pts = (c + [x0, y0]).astype(np.float64)
        # reconnect both ends to adjacent junctions
        for end in (0, -1):
            ex, ey = int(pts[end][0]), int(pts[end][1])
            win = jlab[max(ey - 1, 0):ey + 2, max(ex - 1, 0):ex + 2]
            js = win[win > 0]
            if js.size:
                cxy = jcent[int(js[0])]
                if end == 0:
                    pts = np.vstack([[cxy], pts])
                else:
                    pts = np.vstack([pts, [cxy]])
        paths.append(pts)
    return paths


def fit_circle(pts: np.ndarray) -> tuple[float, float, float, float]:
    """Algebraic (Kasa) circle fit. Returns (cx, cy, r, rms_residual)."""
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x**2 + y**2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = sol[0] / 2, sol[1] / 2
    r = math.sqrt(max(sol[2] + cx**2 + cy**2, 0.0))
    res = np.hypot(x - cx, y - cy) - r
    return float(cx), float(cy), float(r), float(np.sqrt(np.mean(res**2)))


def _arc_from_points(pts: np.ndarray, cfg_res: float, min_sweep: float, thickness: float, source: str) -> Arc | None:
    if len(pts) < 8:
        return None
    cx, cy, r, rms = fit_circle(pts)
    if not math.isfinite(r) or r <= 0 or rms > cfg_res:
        return None
    chord = math.dist(pts[0], pts[-1])
    span = float(np.ptp(pts[:, 0]) + np.ptp(pts[:, 1]))
    if r > 20 * span:  # nearly straight
        return None
    ang = np.degrees(np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx))
    unwrapped = np.degrees(np.unwrap(np.radians(ang)))
    sweep = float(unwrapped[-1] - unwrapped[0])
    if abs(sweep) < min_sweep:
        return None
    if abs(sweep) >= 350 and chord < 0.1 * r:
        start, end = 0.0, 360.0
    elif sweep > 0:
        start, end = float(ang[0]), float(ang[0] + sweep)
    else:
        start, end = float(ang[-1]), float(ang[-1] - sweep)
    conf = float(max(0.0, 1.0 - rms / cfg_res * 0.5))
    return Arc(cx, cy, r, start % 360, end if end - start >= 360 else (start % 360) + (end - start),
               thickness, LAYER_ARC, conf, source)


def classify_path(pts: np.ndarray, eps: float, min_len: float, arc_res: float, min_sweep: float,
                  thickness: float, detect_curves: bool, source: str, corner_deg: float = 40.0):
    """Convert one traced path into straight segments, circular arcs and polylines.

    The Douglas-Peucker polygon is split at sharp corners; every corner-free run
    of 3+ vertices is tested as a circular arc against the dense pixel path, so a
    door leaf joined to its swing becomes one segment plus one arc.
    """
    segs: list[Segment] = []
    arcs: list[Arc] = []
    polys: list[Polyline] = []
    if len(pts) < 2:
        return segs, arcs, polys
    total = float(np.sum(np.hypot(*np.diff(pts, axis=0).T)))
    if total < min_len:
        return segs, arcs, polys
    closed = len(pts) > 3 and math.dist(pts[0], pts[-1]) <= 1.5
    if closed and detect_curves:
        arc = _arc_from_points(pts, arc_res, min_sweep, thickness, source + "-arc")
        if arc is not None:
            return segs, [arc], polys
    approx = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2), eps, False).reshape(-1, 2)
    # indices of RDP vertices in the dense path
    idx = []
    start = 0
    for v in approx:
        d = np.hypot(pts[start:, 0] - v[0], pts[start:, 1] - v[1])
        k = start + int(np.argmin(d))
        idx.append(k)
        start = k
    # split at corners
    cuts = [0]
    for i in range(1, len(approx) - 1):
        a = approx[i] - approx[i - 1]
        b = approx[i + 1] - approx[i]
        turn = abs(math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1])))
        if turn > corner_deg:
            cuts.append(i)
    cuts.append(len(approx) - 1)
    for ci in range(len(cuts) - 1):
        i, j = cuts[ci], cuts[ci + 1]
        if j - i == 1:
            (x1, y1), (x2, y2) = approx[i], approx[j]
            if math.dist((x1, y1), (x2, y2)) >= min_len * 0.25:
                segs.append(Segment(float(x1), float(y1), float(x2), float(y2), thickness, "line", LAYER_LINE,
                                    1.0, source))
            continue
        dense = pts[idx[i]:idx[j] + 1]
        arc = _arc_from_points(dense, arc_res, min_sweep, thickness, source + "-arc") if detect_curves else None
        if arc is not None:
            arcs.append(arc)
            continue
        run = approx[i:j + 1]
        lens = np.hypot(*np.diff(run, axis=0).T)
        if float(lens.min()) >= min_len:  # genuinely straight pieces meeting at shallow angles
            for (x1, y1), (x2, y2) in zip(run[:-1], run[1:]):
                segs.append(Segment(float(x1), float(y1), float(x2), float(y2), thickness, "line", LAYER_LINE,
                                    0.9, source))
        else:  # free-form curve: keep as polyline, do not force into lines
            polys.append(Polyline([(float(x), float(y)) for x, y in run], False, thickness, LAYER_LINE, 0.7, source))
    return segs, arcs, polys


def extract_thin(thin: np.ndarray, cfg: ExtractConfig, dpi: float) -> tuple[list[Segment], list[Arc], list[Polyline], dict]:
    if not thin.any():
        return [], [], [], {"paths": 0}
    dt = cv2.distanceTransform(thin, cv2.DIST_L2, 3)
    sk = skeletonize(thin.astype(bool))
    stroke = 2.0 * float(np.median(dt[sk])) if sk.any() else 1.0
    paths = trace_skeleton(sk)
    eps = max(0.75, mm_to_px(cfg.rdp_epsilon_mm, dpi))
    min_len = mm_to_px(cfg.min_line_length_mm, dpi)
    frag_len = mm_to_px(cfg.fragment_min_length_mm, dpi)
    arc_res = max(0.8, mm_to_px(cfg.arc_max_residual_mm, dpi))
    segs: list[Segment] = []
    arcs: list[Arc] = []
    polys: list[Polyline] = []
    for p in paths:
        s, a, pl = classify_path(p, eps, frag_len, arc_res, cfg.arc_min_sweep_deg, stroke,
                                 cfg.detect_curves, "raster-skeleton")
        segs += s
        arcs += a
        polys += pl
    # short pieces are kept as fragments: line chaining joins them or returns them to annotation
    segs = [s for s in segs if s.length >= frag_len]
    for s in segs:
        if s.length < min_len:
            s.attrs["fragment"] = True
    return segs, arcs, polys, {"paths": len(paths), "thin_stroke_px": round(stroke, 2),
                               "thin_segments": len(segs), "arcs": len(arcs), "polylines": len(polys)}


def annotation_stroke_candidates(anno: np.ndarray, cfg: ExtractConfig, dpi: float) -> list[Segment]:
    """Straight thin strokes inside annotation-sized blobs, as *candidate* line pieces.

    Where a broken line crosses another one, its pieces fuse into small L/T/+ blobs
    that look like symbols.  Their straight strokes are offered to line chaining as
    candidates; a candidate is only used when it extends a chain of real line
    pieces (so text on its own never turns into lines) and is otherwise discarded -
    the blob itself stays annotation.
    """
    if not anno.any():
        return []
    max_w = mm_to_px(cfg.fragment_max_width_mm, dpi)
    frag_len = mm_to_px(cfg.fragment_min_length_mm, dpi)
    eps = max(0.75, mm_to_px(cfg.rdp_epsilon_mm, dpi))
    dt = cv2.distanceTransform(anno, cv2.DIST_L2, 3)
    sk = skeletonize(anno.astype(bool))
    out: list[Segment] = []
    for path in trace_skeleton(sk):
        segs, _, _ = classify_path(path, eps, frag_len, 1.0, 360.0, 1.0, False, "annotation-stroke")
        for sg in segs:
            if sg.length < frag_len:
                continue
            mx, my = int(round((sg.x1 + sg.x2) / 2)), int(round((sg.y1 + sg.y2) / 2))
            if not (0 <= my < dt.shape[0] and 0 <= mx < dt.shape[1]):
                continue
            w = 2.0 * float(dt[my, mx])
            if w > max_w or w <= 0:
                continue
            sg.thickness = w
            sg.confidence = 0.6
            sg.attrs.update({"fragment": True, "candidate": True})
            out.append(sg)
    return out


# --------------------------------------------------------------------------- main entry
def extract(binary: np.ndarray, cfg: ExtractConfig, dpi: float, heal_mm: float = 0.0) -> Extraction:
    max_anno = mm_to_px(cfg.text_max_size_mm, dpi)
    geom, anno, fragments = separate_annotation(
        binary, max_anno, 2 * mm_to_px(cfg.wall_min_thickness_mm, dpi),
        (mm_to_px(cfg.fragment_min_length_mm, dpi), mm_to_px(cfg.fragment_max_width_mm, dpi), cfg.fragment_min_aspect))
    candidates = annotation_stroke_candidates(anno, cfg, dpi)
    walls, polys, wall_mask, wstats = extract_walls(geom, cfg, dpi, int(round(mm_to_px(heal_mm, dpi))))
    # thin = geometry ink not explained by the solid wall mask
    grown = cv2.dilate(wall_mask, _kernel(3, 3)) if wall_mask.any() else wall_mask
    thin = geom & (1 - grown)
    thin = cv2.morphologyEx(thin, cv2.MORPH_OPEN, _kernel(1, 1))
    tsegs, arcs, plines, tstats = extract_thin(thin, cfg, dpi)
    ex = Extraction(walls + tsegs + fragments + candidates, arcs, plines, polys, anno, wall_mask, thin)
    ex.stats = {"annotation_px": int(anno.sum()), "line_fragments": len(fragments),
                "annotation_stroke_candidates": len(candidates), **wstats, **tstats}
    return ex
