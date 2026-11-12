"""Stage E - geometry correction must be conservative and traceable."""

from archvectra.config import CorrectConfig
from archvectra.correct import merge_collinear, snap_angles, snap_endpoints, thickness_families
from archvectra.model import Drawing, Scale, Segment
from archvectra.semantics import find_openings


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


def test_broken_scan_line_becomes_one_continuous_line():
    """A straight line broken into many pieces by poor scanning -> one line; real gaps stay open."""
    import cv2
    import numpy as np

    from archvectra.config import Config
    from archvectra.correct import correct
    from archvectra.extract import extract

    rng = np.random.default_rng(1)
    img = np.zeros((600, 2400), np.uint8)
    x = 100
    while x < 1100:  # first run: pieces 6-40 px, gaps 3-25 px, slight jitter (300 dpi)
        L = int(rng.integers(6, 40))
        y = 300 + int(rng.integers(-1, 2))
        cv2.line(img, (x, y), (x + L, y), 1, 3)
        x += L + int(rng.integers(3, 25))
    x = 1250  # 150 px (12.7 mm) gap = a real opening, then a second broken run
    while x < 2300:
        L = int(rng.integers(6, 40))
        cv2.line(img, (x, 300), (x + L, 300), 1, 3)
        x += L + int(rng.integers(3, 25))
    for k in range(5):  # isolated "1"-like text strokes far apart must NOT become a line
        cv2.line(img, (300 + k * 300, 450), (300 + k * 300, 480), 1, 3)
    cfg = Config()
    ex = extract(img, cfg.extract, 300)
    d = Drawing(2400, 600, 300.0, (1, 0, 0, 1, 0, 0), (2400, 600), Scale(25.4 / 300))
    d.segments, d.arcs = ex.segments, ex.arcs
    correct(d, cfg.correct)
    long_lines = sorted((s for s in d.segments if s.kind == "line" and s.layer == "A-DETL" and s.length > 300),
                        key=lambda s: s.x1)
    assert len(long_lines) == 2, [(round(s.x1), round(s.x2)) for s in long_lines]
    a, b = long_lines
    assert a.y1 == a.y2 and abs(a.y1 - 300) < 2
    assert a.x1 < 110 and a.x2 > 1080 and b.x1 > 1240  # opening between them preserved
    assert not [s for s in d.segments if s.layer == "A-DETL" and abs(s.y1 - 465) < 20 and s.length > 40]
