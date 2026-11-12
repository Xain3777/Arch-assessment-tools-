"""Stage E - geometry correction.

Every operation is conservative and logged:

* near-orthogonal segments are snapped to 0/90 degrees; other angles are kept;
* collinear pieces are merged only across gaps <= ``merge_gap`` (scan breaks);
  longer gaps are never closed here - they are handed to opening detection;
* endpoints are moved to a line intersection only when the move is within
  the snapping radius (plus the half-thickness of the walls involved);
* wall thicknesses are grouped into families and snapped to the family value
  only when within a relative tolerance.

Nothing is created from nothing: correction moves, merges or relabels
existing evidence and records a confidence for each change.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict

import numpy as np

from .config import CorrectConfig
from .model import LAYER_ANNOTATION, Drawing, Segment
from .spatial import SegmentIndex

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- angles
def snap_angles(segs: list[Segment], tol_deg: float) -> int:
    n = 0
    for s in segs:
        a = s.angle
        if s.orientation in ("h", "v"):
            continue
        if min(a, 180 - a) <= tol_deg:
            y = (s.y1 + s.y2) / 2
            s.y1 = s.y2 = y
            s.attrs["angle_snapped_from"] = round(a, 3)
            n += 1
        elif abs(a - 90) <= tol_deg:
            x = (s.x1 + s.x2) / 2
            s.x1 = s.x2 = x
            s.attrs["angle_snapped_from"] = round(a, 3)
            n += 1
    for s in segs:
        s.normalised()
    return n


# --------------------------------------------------------------------------- collinear merge
def _frame(angle_deg: float) -> tuple[np.ndarray, np.ndarray]:
    a = math.radians(angle_deg)
    u = np.array([math.cos(a), math.sin(a)])
    return u, np.array([-u[1], u[0]])


def merge_collinear(segs: list[Segment], offset_tol: float, gap_tol: float, thick_rel_tol: float = 0.35,
                    angle_bucket_deg: float = 1.0) -> tuple[list[Segment], list[dict]]:
    """Merge overlapping / nearly touching collinear segments of the same kind."""
    groups: dict[tuple, list[Segment]] = defaultdict(list)
    for s in segs:
        key = (s.kind, s.layer, round(s.angle / angle_bucket_deg) % round(180 / angle_bucket_deg),
               repr(s.attrs.get("style")))
        groups[key].append(s)
    out: list[Segment] = []
    bridged: list[dict] = []
    for (kind, layer, bucket, _style), items in groups.items():
        ang = float(np.average([s.angle for s in items], weights=[s.length + 1e-6 for s in items]))
        if any(abs(s.angle - ang) > 90 for s in items):  # bucket straddles 0/180
            ang = 0.0
        u, n = _frame(ang)
        rec = []
        for s in items:
            p, q = np.array([s.x1, s.y1]), np.array([s.x2, s.y2])
            t0, t1 = sorted((float(p @ u), float(q @ u)))
            off = float((p @ n + q @ n) / 2)
            rec.append([off, t0, t1, s])
        rec.sort(key=lambda r: r[0])
        # cluster by offset
        clusters: list[list] = []
        for r in rec:
            tol = max(offset_tol, 0.25 * r[3].thickness) if kind == "wall" else offset_tol
            if clusters and abs(r[0] - clusters[-1][-1][0]) <= tol:
                clusters[-1].append(r)
            else:
                clusters.append([r])
        for cl in clusters:
            # align members of a collinear cluster (pieces of one wall split by openings)
            if len(cl) > 1:
                wts = [max(r[2] - r[1], 1e-6) for r in cl]
                mean_off = float(np.average([r[0] for r in cl], weights=wts))
                if max(abs(r[0] - mean_off) for r in cl) <= offset_tol:
                    for r in cl:
                        if abs(r[0] - mean_off) > 1e-9:
                            s_ = r[3]
                            shift = n * (mean_off - r[0])
                            s_.x1 += shift[0]; s_.x2 += shift[0]  # noqa: E702
                            s_.y1 += shift[1]; s_.y2 += shift[1]  # noqa: E702
                            s_.attrs["aligned_shift"] = round(float(mean_off - r[0]), 3)
                            r[0] = mean_off
            cl.sort(key=lambda r: r[1])
            cur: list = []

            def flush():
                if not cur:
                    return
                if len(cur) == 1:
                    out.append(cur[0][3])
                    return
                w = np.array([max(r[2] - r[1], 1e-6) for r in cur])
                off = float(np.average([r[0] for r in cur], weights=w))
                t0, t1 = min(r[1] for r in cur), max(r[2] for r in cur)
                th = float(np.average([r[3].thickness for r in cur], weights=w))
                conf = float(np.average([r[3].confidence for r in cur], weights=w))
                p, q = u * t0 + n * off, u * t1 + n * off
                base = cur[0][3]
                m = Segment(float(p[0]), float(p[1]), float(q[0]), float(q[1]), th, kind, layer, conf,
                            base.source, attrs={"merged_from": len(cur)})
                for r in cur:
                    for k, v in r[3].attrs.items():
                        m.attrs.setdefault(k, v)
                m.attrs["merged_from"] = len(cur)
                if base.orientation == "h" or abs(ang) < 1e-9:
                    m.y1 = m.y2 = (m.y1 + m.y2) / 2
                elif abs(ang - 90) < 1e-9:
                    m.x1 = m.x2 = (m.x1 + m.x2) / 2
                out.append(m.normalised())

            for r in cl:
                if cur:
                    end = max(c[2] for c in cur)
                    thick_ok = True
                    if kind == "wall":
                        t_a = np.median([c[3].thickness for c in cur])
                        thick_ok = abs(r[3].thickness - t_a) / max(t_a, r[3].thickness) <= thick_rel_tol
                    gap = r[1] - end
                    if gap <= gap_tol and thick_ok:
                        if gap > 0:
                            mid = u * (end + gap / 2) + n * r[0]
                            bridged.append({"x": float(mid[0]), "y": float(mid[1]), "gap": float(gap), "kind": kind})
                        cur.append(r)
                        continue
                    flush()
                    cur = []
                cur.append(r)
            flush()
    return out, bridged


# --------------------------------------------------------------------------- line chaining
def chain_lines(segs: list[Segment], angle_tol: float, offset_tol: float, max_gap: float, min_coverage: float,
                min_chain_len: float) -> tuple[list[Segment], dict]:
    """Join broken / fragmented thin lines lying on one straight line into a single line.

    Pieces are grouped by direction (within ``angle_tol``) and by perpendicular
    offset (within ``offset_tol``), sorted along the line and chained while each gap
    is <= ``max_gap``.  A chain is accepted only when it has >= 2 pieces, is at
    least ``min_chain_len`` long and ink covers >= ``min_coverage`` of its length -
    so isolated text strokes and real openings (gaps > max_gap) are left alone.
    """
    lines = [s for s in segs if s.kind == "line" and s.length > 0]
    rest = [s for s in segs if not (s.kind == "line" and s.length > 0)]
    if len(lines) < 2:
        return segs, {"chains": 0, "pieces_joined": 0}
    from shapely import LineString as _LS

    index = SegmentIndex(lines)

    def crossed(a: np.ndarray, b: np.ndarray, ang_deg: float) -> bool:
        """True when a non-parallel line crosses the gap a-b (a grid / wall crossing)."""
        chord = _LS([tuple(a), tuple(b)])
        for k in index.query(min(a[0], b[0]) - 2, min(a[1], b[1]) - 2, max(a[0], b[0]) + 2, max(a[1], b[1]) + 2):
            o = lines[k]
            d = abs(o.angle - ang_deg) % 180
            if min(d, 180 - d) > 30 and o.length > max_gap / 4 and \
                    chord.intersects(_LS([(o.x1, o.y1), (o.x2, o.y2)])):
                return True
        return False
    # --- angle clusters (0/180 wrap handled by folding angles near 180 to negative)
    def fold(a):  # near-horizontal pieces on both sides of 0/180 end up together
        return a - 180.0 if a > 170.0 else a

    # Greedy clustering, longest pieces first.  A short piece's measured angle is
    # unreliable, so its tolerance widens to atan(2 * offset_tol / length), capped at
    # 10 degrees; collinearity is still enforced by the offset grouping below.
    clusters: list[list[Segment]] = []
    cl_angle: list[float] = []
    buckets: dict[int, list[int]] = defaultdict(list)
    for s in sorted(lines, key=lambda s: -s.length):
        a = fold(s.angle)
        tol = min(10.0, max(angle_tol, math.degrees(math.atan2(2 * offset_tol, max(s.length, 1e-6)))))
        best, best_d = None, None
        for b in range(int(math.floor(a - tol)) - 1, int(math.ceil(a + tol)) + 2):
            for ci in buckets.get(b, ()):
                dd = abs(cl_angle[ci] - a)
                if dd <= tol and (best is None or dd < best_d):
                    best, best_d = ci, dd
        if best is None:
            clusters.append([s])
            cl_angle.append(a)
            buckets[int(round(a))].append(len(clusters) - 1)
        else:
            clusters[best].append(s)
    out: list[Segment] = []
    n_chains = joined = 0
    for ci, cl in enumerate(clusters):
        ang = cl_angle[ci] if len(cl) == 1 else float(
            np.average([fold(s.angle) for s in cl], weights=[s.length ** 2 for s in cl]))
        u, n = _frame(ang)
        rec = []
        for s in cl:
            p, q = np.array([s.x1, s.y1]), np.array([s.x2, s.y2])
            t0, t1 = sorted((float(p @ u), float(q @ u)))
            rec.append(((float(p @ n) + float(q @ n)) / 2, t0, t1, s))
        rec.sort(key=lambda r: r[0])
        groups: list[list] = []
        for r in rec:  # offset clusters, span limited to 2 x offset_tol
            if groups and r[0] - groups[-1][0][0] <= 2 * offset_tol and r[0] - groups[-1][-1][0] <= offset_tol:
                groups[-1].append(r)
            else:
                groups.append([r])
        for g in groups:
            g.sort(key=lambda r: r[1])
            chain: list = []

            def flush():
                nonlocal n_chains, joined
                if not chain:
                    return
                start, end = chain[0][1], max(r[2] for r in chain)
                span = end - start
                covered, cur_s, cur_e = 0.0, chain[0][1], chain[0][2]
                for r in chain[1:]:
                    if r[1] > cur_e:
                        covered += cur_e - cur_s
                        cur_s, cur_e = r[1], r[2]
                    else:
                        cur_e = max(cur_e, r[2])
                covered += cur_e - cur_s
                cov = covered / span if span > 0 else 1.0
                real = sum(1 for r in chain if not r[3].attrs.get("candidate"))
                if len(chain) >= 2 and real >= 1 and span >= min_chain_len and cov >= min_coverage:
                    w = np.array([r[2] - r[1] for r in chain]) + 1e-6
                    off = float(np.average([r[0] for r in chain], weights=w))
                    p, q = u * start + n * off, u * end + n * off
                    th = float(np.average([r[3].thickness for r in chain], weights=w))
                    conf = float(np.average([r[3].confidence for r in chain], weights=w)) * min(1.0, 0.5 + cov / 2)
                    gaps = [max(0.0, b[1] - max(x[2] for x in chain[:k + 1])) for k, b in enumerate(chain[1:])]
                    m = Segment(float(p[0]), float(p[1]), float(q[0]), float(q[1]), th, "line", chain[0][3].layer,
                                conf, "chained", attrs={"chained_from": len(chain), "coverage": round(cov, 3),
                                                        "max_gap_px": round(max(gaps, default=0.0), 2)})
                    if abs(ang) < 1e-9:
                        m.y1 = m.y2 = (m.y1 + m.y2) / 2
                    elif abs(ang - 90) < 1e-9:
                        m.x1 = m.x2 = (m.x1 + m.x2) / 2
                    out.append(m.normalised())
                    n_chains += 1
                    joined += len(chain)
                else:
                    out.extend(r[3] for r in chain)

            for r in g:
                if chain:
                    end = max(x[2] for x in chain)
                    gap = r[1] - end
                    ok = gap <= max_gap
                    if not ok and gap <= 2 * max_gap:  # allow a longer gap only at a crossing
                        off = (chain[-1][0] + r[0]) / 2
                        ok = crossed(u * end + n * off, u * r[1] + n * off, ang % 180)
                    if not ok:
                        flush()
                        chain = []
                chain.append(r)
            flush()
    return rest + out, {"chains": n_chains, "pieces_joined": joined}


# --------------------------------------------------------------------------- endpoint snapping
def _line_intersection(p, r, q, s):
    """Intersection of p + t r and q + u s; returns (point, t, u) or None if parallel."""
    rxs = r[0] * s[1] - r[1] * s[0]
    if abs(rxs) < 1e-9:
        return None
    qp = q - p
    t = (qp[0] * s[1] - qp[1] * s[0]) / rxs
    u = (qp[0] * r[1] - qp[1] * r[0]) / rxs
    return p + t * r, t, u


def snap_endpoints(segs: list[Segment], snap: float, min_angle_deg: float = 20.0,
                   use_thickness: bool = True) -> list[dict]:
    """Extend / trim free ends onto the nearest non-parallel segment (L and T joints)."""
    moves: list[dict] = []
    index = SegmentIndex(segs)
    max_t = max((s.thickness for s in segs), default=0.0)
    for i, s in enumerate(segs):
        for end in (0, 1):
            p = np.array([s.x1, s.y1]) if end == 0 else np.array([s.x2, s.y2])
            other_end = np.array([s.x2, s.y2]) if end == 0 else np.array([s.x1, s.y1])
            d = p - other_end
            L = float(np.linalg.norm(d))
            if L < 1e-6:
                continue
            d /= L
            best = None
            reach = 2.0 * (snap + (max_t + s.thickness if use_thickness else 0.0))
            for j in index.near(float(p[0]), float(p[1]), reach):
                o = segs[j]
                if j == i:
                    continue
                diff = abs(s.angle - o.angle) % 180
                if min(diff, 180 - diff) < min_angle_deg:
                    continue
                q = np.array([o.x1, o.y1])
                v = np.array([o.x2 - o.x1, o.y2 - o.y1])
                lo = float(np.linalg.norm(v))
                if lo < 1e-6:
                    continue
                res = _line_intersection(other_end, d, q, v / lo)
                if res is None:
                    continue
                x, t, u = res
                extra = (o.thickness / 2 + s.thickness / 2) if use_thickness else 0.0
                move = abs(t - L)
                if move > snap + extra:
                    continue
                # the intersection must lie on (or just past the end of) the other segment
                if u < -(snap + extra) or u > lo + snap + extra:
                    continue
                if t < 0.5 * L:  # never collapse more than half the segment
                    continue
                if best is None or move < best[0]:
                    best = (move, x, j, u, lo)
            if best is not None:
                move, x, j, u, lo = best
                if move > 1e-6:
                    moves.append({"segment": i, "end": end, "to": j, "move": float(move),
                                  "x": float(x[0]), "y": float(x[1])})
                if end == 0:
                    s.x1, s.y1 = float(x[0]), float(x[1])
                else:
                    s.x2, s.y2 = float(x[0]), float(x[1])
                s.attrs[f"joint_{end}"] = j
                s.attrs.setdefault("snap_moves", []).append(round(float(move), 2))
    return moves


# --------------------------------------------------------------------------- thickness families
def thickness_families(walls: list[Segment], rel_tol: float) -> list[dict]:
    if not walls:
        return []
    ws = sorted(walls, key=lambda w: w.thickness)
    fams: list[list[Segment]] = [[ws[0]]]
    for w in ws[1:]:
        ref = float(np.median([x.thickness for x in fams[-1]]))
        if abs(w.thickness - ref) / ref <= rel_tol:
            fams[-1].append(w)
        else:
            fams.append([w])
    out = []
    for k, fam in enumerate(fams):
        lengths = np.array([w.length for w in fam])
        value = float(np.average([w.thickness for w in fam], weights=lengths + 1e-6))
        for w in fam:
            w.attrs["thickness_measured"] = round(w.thickness, 3)
            w.attrs["thickness_family"] = k
            w.thickness = value
        out.append({"family": k, "thickness": value, "walls": len(fam), "total_length": float(lengths.sum())})
    return out


# --------------------------------------------------------------------------- dedupe
def remove_degenerate(segs: list[Segment], min_len: float) -> tuple[list[Segment], int]:
    keep = [s for s in segs if s.length >= min_len]
    return keep, len(segs) - len(keep)


def drop_lines_inside_walls(lines: list[Segment], walls: list[Segment]) -> tuple[list[Segment], int]:
    """Thin segments lying entirely inside a solid wall are tracing artefacts."""
    out = []
    dropped = 0
    index = SegmentIndex(walls)
    for s in lines:
        mid = np.array([(s.x1 + s.x2) / 2, (s.y1 + s.y2) / 2])
        inside = False
        for k in index.near(float(mid[0]), float(mid[1]), 1.0):
            w = walls[k]
            p, q = np.array([w.x1, w.y1]), np.array([w.x2, w.y2])
            v = q - p
            L = float(np.linalg.norm(v))
            if L < 1e-6:
                continue
            u = v / L
            t = float((mid - p) @ u)
            off = abs(float((mid - p) @ np.array([-u[1], u[0]])))
            if -1 <= t <= L + 1 and off < w.thickness / 2 - 0.5:
                diff = abs(s.angle - w.angle) % 180
                if min(diff, 180 - diff) < 10 and s.length < L + 2:
                    inside = True
                    break
        if inside:
            dropped += 1
        else:
            out.append(s)
    return out, dropped


# --------------------------------------------------------------------------- driver
def correct(drawing: Drawing, cfg: CorrectConfig, vector_source: bool = False,
            min_line_length_mm: float = 3.0) -> None:
    mm = drawing.mm
    walls = [s for s in drawing.segments if s.kind == "wall"]
    lines = [s for s in drawing.segments if s.kind != "wall"]
    angle_tol = cfg.angle_tolerance_deg if not vector_source else min(cfg.angle_tolerance_deg, 0.2)
    n_snap = snap_angles(walls, angle_tol) + snap_angles(lines, angle_tol)
    chain_stats = {"chains": 0, "pieces_joined": 0}
    if cfg.chain_lines and not vector_source:
        lines, chain_stats = chain_lines(lines, cfg.line_chain_angle_deg, mm(cfg.line_chain_offset_mm),
                                         mm(cfg.line_chain_max_gap_mm), cfg.line_chain_min_coverage,
                                         mm(min_line_length_mm))
        # second pass: chains now have accurate directions, so neighbouring chains and
        # leftover short pieces whose own angle was too noisy can be joined
        lines, st2 = chain_lines(lines, cfg.line_chain_angle_deg, mm(cfg.line_chain_offset_mm),
                                 mm(cfg.line_chain_max_gap_mm), cfg.line_chain_min_coverage,
                                 mm(min_line_length_mm))
        chain_stats = {"chains": chain_stats["chains"] + st2["chains"],
                       "pieces_joined": chain_stats["pieces_joined"] + st2["pieces_joined"]}
    gap = mm(cfg.merge_gap_mm) if not vector_source else mm(0.05)
    off = mm(cfg.collinear_offset_mm) if not vector_source else mm(0.05)
    walls, bridged_w = merge_collinear(walls, off, gap, cfg.thickness_cluster_tolerance * 2)
    lines, bridged_l = merge_collinear(lines, off, gap)
    lines, dropped_inside = drop_lines_inside_walls(lines, walls) if not vector_source else (lines, 0)
    fams = thickness_families(walls, cfg.thickness_cluster_tolerance)
    wall_moves = snap_endpoints(walls, mm(cfg.snap_distance_mm))
    line_moves = snap_endpoints(lines, mm(cfg.snap_distance_mm) if not vector_source else mm(0.05),
                                use_thickness=False)
    walls, nd_w = remove_degenerate(walls, mm(0.5) if not vector_source else mm(0.01))
    lines, nd_l = remove_degenerate(lines, mm(0.3) if not vector_source else mm(0.01))
    # fragments that did not become part of a real line: drop them when a longer line
    # already covers them (pieces at crossings), otherwise they are annotation (text strokes)
    # candidate strokes (from annotation blobs) that did not extend a real line are discarded:
    # their ink is still in the annotation mask and is traced as an outline
    lines = [s_ for s_ in lines if not s_.attrs.get("candidate")]
    n_unchained = n_redundant = 0
    long_ = [s_ for s_ in lines if not (s_.attrs.get("fragment") and s_.length < mm(min_line_length_mm))]
    lidx = SegmentIndex(long_)
    keep_lines = []
    tol_off = mm(cfg.line_chain_offset_mm) + 1.0
    for s_ in lines:
        if s_.attrs.get("fragment") and s_.length < mm(min_line_length_mm):
            redundant = False
            for k in lidx.near((s_.x1 + s_.x2) / 2, (s_.y1 + s_.y2) / 2, s_.length + tol_off):
                o = long_[k]
                d = abs(o.angle - s_.angle) % 180
                if min(d, 180 - d) > cfg.line_chain_angle_deg * 2:
                    continue
                p, q = np.array([o.x1, o.y1]), np.array([o.x2, o.y2])
                u_ = (q - p) / max(o.length, 1e-9)
                n_ = np.array([-u_[1], u_[0]])
                ends = [np.array([s_.x1, s_.y1]), np.array([s_.x2, s_.y2])]
                if all(abs(float((e - p) @ n_)) <= tol_off and -tol_off <= float((e - p) @ u_) <= o.length + tol_off
                       for e in ends):
                    redundant = True
                    break
            if redundant:
                n_redundant += 1
                continue
            s_.layer = LAYER_ANNOTATION
            n_unchained += 1
        keep_lines.append(s_)
    lines = keep_lines
    drawing.segments = walls + lines
    for b in bridged_w:
        if b["gap"] > mm(cfg.merge_gap_mm) * 0.6:
            drawing.flag(b["x"], b["y"], "bridged-gap",
                         f"wall gap of {b['gap']:.1f} px bridged as a scan break", "info")
    drawing.log("correct", angle_snapped=n_snap, line_chains=chain_stats["chains"],
                fragments_chained=chain_stats["pieces_joined"], fragments_to_annotation=n_unchained, fragments_redundant=n_redundant, bridged_wall_gaps=len(bridged_w), bridged_line_gaps=len(bridged_l),
                wall_endpoint_moves=len(wall_moves), line_endpoint_moves=len(line_moves),
                max_wall_move_px=round(max([m["move"] for m in wall_moves], default=0.0), 2),
                lines_inside_walls_dropped=dropped_inside, degenerate_removed=nd_w + nd_l,
                thickness_families=[{**f, "thickness": round(f["thickness"], 2)} for f in fams])
