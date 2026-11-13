"""Structural grid, dimension reading and rectification on a distorted scan.

The sheet has a 6 x 4 grid (spans 6000/4500/6000/4500/6000 x 5000/6000/5000 mm), a
column on every intersection, dimension chains and bubbles; the scan is stretched
1.2 % on its right half, shrunk 0.8 % vertically, sheared 0.2 deg, rotated 0.6 deg.
"""

import numpy as np
import pytest

from archvectra.config import Config
from archvectra.grid import Axis
from archvectra.rectify import SpanDim, _interp, choose_scale, infer_labels
from archvectra.synthetic import GRID_X_MM, GRID_Y_MM, write_grid_scan_pdf


def test_label_inference():
    axes = [Axis("v", float(i), 0.0, 0, 1) for i in range(4)]
    for a, lbl in zip(axes, ["1", None, "3", None]):
        a.label = lbl
    assert infer_labels(axes) == 2 and [a.label for a in axes] == ["1", "2", "3", "4"]
    axes = [Axis("h", float(i), 0.0, 0, 1) for i in range(4)]
    for a, lbl in zip(axes, [None, "B", None, "D"]):
        a.label = lbl
    infer_labels(axes)
    assert [a.label for a in axes] == ["A", "B", "C", "D"]
    axes = [Axis("h", float(i), 0.0, 0, 1) for i in range(3)]
    for a, lbl in zip(axes, ["A", "7", None]):  # inconsistent -> nothing guessed
        a.label = lbl
    assert infer_labels(axes) == 0 and axes[2].label is None


def test_unit_choice_and_outlier_rejection():
    paper = 25.4 / 300  # sheet mm per px at 300 dpi; 1:100 -> 8.4667 mm per px
    spans = [SpanDim("v", i, v * 1000 / 8.4667 / 1000) for i, v in enumerate([6000, 4500, 6000])]
    for sd, v in zip(spans, [6000, 4500, 6000]):
        sd.values = [v]
    spans.append(SpanDim("v", 3, 6000 / 8.4667))
    spans[-1].values = [9000]  # misread / not to scale
    sc = choose_scale(spans, paper, None, 0.05)
    assert sc["unit"] == "mm" and abs(sc["denominator"] - 100) < 0.5
    assert spans[-1].status == "disagrees" and sc["used"] == 3


def test_piecewise_map_extrapolates_linearly():
    p, P = np.array([0.0, 10.0, 20.0]), np.array([0.0, 12.0, 22.0])
    assert np.allclose(_interp(np.array([-5.0, 5.0, 15.0, 30.0]), p, P), [-6.0, 6.0, 17.0, 32.0])


@pytest.fixture(scope="module")
def grid_run(tmp_path_factory):
    pytest.importorskip("rapidocr_onnxruntime")
    from archvectra.pipeline import run

    d = tmp_path_factory.mktemp("grid")
    pdf = d / "grid.pdf"
    truth = write_grid_scan_pdf(pdf, dpi=300)
    return run(pdf, d / "out", Config()), truth


def test_grid_found_and_labelled(grid_run):
    res, _ = grid_run
    g = res.report["grid"]
    assert g["vertical_axes"] == 6 and g["horizontal_axes"] == 4
    assert g["labels"]["vertical"] == ["1", "2", "3", "4", "5", "6"]
    assert g["labels"]["horizontal"] == ["A", "B", "C", "D"]


def test_scale_read_from_dimensions(grid_run):
    res, _ = grid_run
    sc = res.drawing.scale
    assert sc.calibrated and sc.source.startswith("dimensions")
    assert abs(sc.denominator - 100) < 0.5
    used = [d for d in res.report["grid"]["dimension_spans"] if d["status"] == "used"]
    assert len(used) == 8


def test_distortion_corrected(grid_run):
    res, _ = grid_run
    d, g = res.drawing, res.report["grid"]
    k = d.scale.mm_per_unit
    X, Y = np.array(d.meta["grid"]["X"]), np.array(d.meta["grid"]["Y"])
    tx = np.concatenate([[0], np.cumsum(GRID_X_MM)])
    ty = np.concatenate([[0], np.cumsum(GRID_Y_MM)])
    err_after = max(np.abs((X - X[0]) * k - tx).max(), np.abs((Y - Y[0]) * k - ty).max())
    raw = np.concatenate([[0], np.cumsum([s["measured_px"] for s in g["dimension_spans"] if s["dir"] == "x"])]) * k
    err_before = np.abs(raw - tx).max()
    assert err_before > 100  # the scan really is distorted (mm)
    assert err_after < 5  # and it is corrected


def test_columns_on_every_intersection(grid_run):
    res, _ = grid_run
    d = res.drawing
    X, Y = d.meta["grid"]["X"], d.meta["grid"]["Y"]
    cols = [p for p in d.polygons if p.layer == "A-COLS"]
    cc = np.array([[np.mean([q[0] for q in p.exterior]), np.mean([q[1] for q in p.exterior])] for p in cols])
    for x in X:
        for y in Y:
            assert np.hypot(cc[:, 0] - x, cc[:, 1] - y).min() * d.scale.mm_per_unit < 10


def test_rooms_after_correction(grid_run):
    res, _ = grid_run
    topo = [h for h in res.drawing.history if h["stage"] == "topology"][-1]
    assert topo["room_areas_m2"] == pytest.approx([52.5, 115.5, 264.0], abs=0.5)


def test_dimension_text_is_editable(grid_run):
    res, _ = grid_run
    texts = {t.text for t in res.drawing.texts}
    assert {"6000", "4500", "5000", "27000"} <= texts
