"""Stage C - geometry extraction on controlled rasters."""

import math

import cv2
import numpy as np

from archvectra.config import ExtractConfig
from archvectra.extract import classify_path, extract, fit_circle, trace_skeleton


def _canvas(w=1200, h=900):
    return np.zeros((h, w), np.uint8)


def test_thick_and_thin_strokes_are_separated():
    img = _canvas()
    cv2.rectangle(img, (100, 100), (1000, 124), 1, -1)  # 25 px wall at 300 dpi = 2.1 mm
    cv2.line(img, (100, 400), (1000, 400), 1, 3)  # thin line
    ex = extract(img, ExtractConfig(), 300)
    walls = [s for s in ex.segments if s.kind == "wall"]
    lines = [s for s in ex.segments if s.kind == "line"]
    assert len(walls) == 1 and len(lines) == 1
    w = walls[0]
    assert abs(w.y1 - 112.5) < 1 and abs(w.thickness - 25) < 1.5
    assert abs(w.x1 - 100) < 2 and abs(w.x2 - 1001) < 2
    assert abs(lines[0].y1 - 400) < 1.5 and lines[0].length > 890


def test_text_sized_blobs_become_annotation_but_columns_do_not():
    img = _canvas()
    cv2.putText(img, "ROOM", (300, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 1, 3)
    cv2.rectangle(img, (700, 500), (740, 540), 1, -1)  # 41 px solid square = column
    ex = extract(img, ExtractConfig(), 300)
    assert ex.annotation_mask[270:310, 300:420].sum() > 100
    assert any(p.layer == "A-COLS" for p in ex.polygons)
    assert ex.annotation_mask[500:541, 700:741].sum() == 0


def test_diagonal_thick_wall():
    img = _canvas()
    cv2.line(img, (200, 200), (800, 700), 1, 16)
    ex = extract(img, ExtractConfig(), 300)
    walls = [s for s in ex.segments if s.kind == "wall"]
    assert len(walls) == 1
    w = walls[0]
    assert abs(w.angle - math.degrees(math.atan2(500, 600))) < 1.5
    assert abs(w.thickness - 16) < 2.5


def test_arc_is_fitted_and_separated_from_leaf():
    img = _canvas()
    hinge, r = (400, 600), 200
    cv2.line(img, hinge, (400, 400), 1, 3)  # leaf
    cv2.ellipse(img, hinge, (r, r), 0, -90, 0, 1, 3)  # swing
    ex = extract(img, ExtractConfig(), 300)
    assert len(ex.arcs) == 1
    a = ex.arcs[0]
    assert abs(a.cx - 400) < 3 and abs(a.cy - 600) < 3 and abs(a.r - r) < 3
    assert 80 < a.sweep < 95
    assert any(abs(s.length - 200) < 6 for s in ex.segments)


def test_circle_fit_exact():
    t = np.linspace(0, math.pi / 2, 50)
    pts = np.column_stack([10 + 30 * np.cos(t), -5 + 30 * np.sin(t)])
    cx, cy, r, rms = fit_circle(pts)
    assert abs(cx - 10) < 1e-6 and abs(cy + 5) < 1e-6 and abs(r - 30) < 1e-6 and rms < 1e-9


def test_polyline_path_with_corner_splits_into_two_segments():
    pts = np.array([(x, 0) for x in range(0, 100)] + [(99, y) for y in range(1, 80)], float)
    segs, arcs, polys = classify_path(pts, 1.0, 10, 1.0, 25, 2.0, True, "t")
    assert len(segs) == 2 and not arcs


def test_skeleton_tracer_finds_branches():
    sk = np.zeros((50, 50), np.uint8)
    sk[25, 5:45] = 1
    sk[5:25, 25] = 1
    paths = trace_skeleton(sk)
    lengths = sorted(len(p) for p in paths)
    assert len(paths) == 3 and lengths[-1] >= 19
