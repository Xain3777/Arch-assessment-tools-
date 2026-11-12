"""Stage E - geometry correction must be conservative and traceable."""

from archvec.config import CorrectConfig
from archvec.correct import merge_collinear, snap_angles, snap_endpoints, thickness_families
from archvec.model import Drawing, Scale, Segment
from archvec.semantics import find_openings


def W(x1, y1, x2, y2, t=10.0):  # noqa: N802
    return Segment(x1, y1, x2, y2, t, "wall", "A-WALL")


def test_scan_breaks_are_bridged_but_openings_are_not():
    segs = [W(0, 0, 100, 0), W(102, 0.6, 200, 0.6), W(300, 0, 400, 0)]
    out, bridged = merge_collinear(segs, offset_tol=2, gap_tol=5)
    spans = sorted((s.x1, s.x2) for s in out)
    assert spans == [(0, 200), (300, 400)]
    assert len(bridged) == 1 and abs(bridged[0]["gap"] - 2) < 1e-6


def test_parallel_offset_walls_are_not_merged():
    out, _ = merge_collinear([W(0, 0, 100, 0), W(50, 20, 150, 20)], offset_tol=2, gap_tol=5)
    assert len(out) == 2


def test_duplicates_collapse():
    out, _ = merge_collinear([W(0, 0, 100, 0), W(10, 0.3, 90, 0.3)], offset_tol=2, gap_tol=5)
    assert len(out) == 1 and out[0].length == 100


def test_angle_snap_only_within_tolerance():
    near = Segment(0, 0, 100, 1.0)  # 0.57 deg
    far = Segment(0, 0, 100, 20.0)  # 11 deg - genuine diagonal
    n = snap_angles([near, far], 2.0)
    assert n == 1 and near.y1 == near.y2 and far.y2 != far.y1


def test_l_corner_is_closed_and_t_joint_snapped():
    h = W(5, 0, 200, 0)  # stops at the face of the vertical wall
    v = W(0, -5, 0, 300)
    stem = W(100, 5, 100, 150)  # T-stem stops at the face of h
    moves = snap_endpoints([h, v, stem], snap=6)
    assert (h.x1, h.y1) == (0, 0)
    assert (v.x1, v.y1) == (0, 0)
    assert (stem.x1, stem.y1) == (100, 0)
    assert len(moves) == 3


def test_far_endpoints_are_not_snapped():
    h = W(50, 0, 200, 0)
    v = W(0, -5, 0, 300)
    snap_endpoints([h, v], snap=6)
    assert h.x1 == 50  # 50 px away - never invented


def test_thickness_families():
    walls = [W(0, 0, 100, 0, 10), W(0, 50, 100, 50, 10.8), W(0, 90, 100, 90, 20.5), W(0, 99, 100, 99, 19.6)]
    fams = thickness_families(walls, 0.15)
    assert len(fams) == 2
    assert walls[0].thickness == walls[1].thickness
    assert walls[0].attrs["thickness_measured"] == 10.0


def _drawing(segs):
    d = Drawing(1000, 1000, 254.0, (1, 0, 0, 1, 0, 0), (1000, 1000), Scale(0.1))  # 10 px per mm
    d.segments = segs
    return d


def test_gap_becomes_opening_and_short_gap_is_flagged():
    cfg = CorrectConfig()
    a, b, c = W(0, 0, 100, 0), W(190, 0, 400, 0), W(430, 0, 600, 0)  # 90 px (9 mm) and 30 px (3 mm)
    d = _drawing([a, b, c])
    find_openings(d, cfg)
    assert len(d.openings) == 1 and abs(d.openings[0].width - 90) < 1e-6
    assert d.openings[0].kind == "opening"  # no evidence -> unclassified, never filled
    codes = [f.code for f in d.flags]
    assert "short-gap" in codes and "unclassified-opening" in codes
    assert len(d.walls()) == 3  # nothing was invented or removed
