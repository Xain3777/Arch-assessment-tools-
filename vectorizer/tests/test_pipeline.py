"""End-to-end regression on synthetic sheets with ground truth.

Thresholds are deliberately below the values measured at the time of writing
(see docs/VALIDATION.md) so that the tests catch regressions, not noise.
"""

import json

import ezdxf
import pymupdf
import pytest

from archvec.config import Config
from archvec.pipeline import run


@pytest.fixture(scope="module")
def scan_run(scan_pdf, tmp_path_factory):
    path, truth = scan_pdf
    cfg = Config()
    cfg.scale.denominator = 100
    out = tmp_path_factory.mktemp("run_scan")
    return run(path, out, cfg, truth=path.with_suffix(".truth.json"))


def test_outputs_exist(scan_run):
    for key in ("pdf", "svg", "dxf", "review_pdf", "overlay", "comparison", "report", "model"):
        assert key in scan_run.outputs
    assert (scan_run.out_dir / "manifest.json").exists()
    assert (scan_run.out_dir / "00_source").iterdir()


def test_clean_pdf_is_vector_and_page_sized(scan_run, scan_pdf):
    with pymupdf.open(scan_run.outputs["pdf"]) as doc, pymupdf.open(scan_pdf[0]) as src:
        page = doc[0]
        assert page.rect == src[0].rect
        assert not page.get_images()
        assert sum(len(d["items"]) for d in page.get_drawings()) > 100
        layers = {v["name"] for v in doc.get_ocgs().values()}
        assert {"A-WALL", "A-DOOR", "A-GLAZ"} <= layers


def test_dxf_is_real_world_and_layered(scan_run):
    doc = ezdxf.readfile(scan_run.outputs["dxf"])
    assert doc.header["$INSUNITS"] == 4
    msp = doc.modelspace()
    centre = [e for e in msp.query('LINE[layer=="A-WALL-CNTR"]')]
    assert len(centre) >= 14
    # building is 14 m x 9 m: centreline extents in real mm
    xs = [p for e in centre for p in (e.dxf.start.x, e.dxf.end.x)]
    ys = [p for e in centre for p in (e.dxf.start.y, e.dxf.end.y)]
    assert abs((max(xs) - min(xs)) - 14000) < 60
    assert abs((max(ys) - min(ys)) - 9000) < 60
    assert len(msp.query('ARC[layer=="A-DOOR"]')) == 4
    assert centre[0].get_xdata("ARCHVEC")


def test_ground_truth_metrics(scan_run):
    t = scan_run.report["truth"]
    assert t["walls"]["recall_by_length"] > 0.98
    assert t["walls"]["precision_by_length"] > 0.98
    assert t["walls"]["endpoint_displacement_real_mm"]["max"] < 50
    assert t["openings"]["matched"] == 7 and t["openings"]["kind_correct"] == 7
    assert t["openings"]["false_positives"] == 0
    assert t["scale"]["relative_error"] < 0.001


def test_rooms_and_areas(scan_run):
    topo = next(h for h in scan_run.drawing.history if h["stage"] == "topology")
    assert topo["rooms"] == 4
    for got, want in zip(topo["room_areas_m2"], [24, 30, 32, 40]):
        assert abs(got - want) < 0.5


def test_source_agreement(scan_run):
    assert scan_run.report["ink_all"]["f1"] > 0.98
    assert scan_run.report["ink_geometry"]["precision"] > 0.98


def test_report_is_json(scan_run):
    rep = json.loads((scan_run.out_dir / "03_validation" / "report.json").read_text())
    assert rep["source"]["kind"] == "raster"


def test_vector_input_is_not_rasterised(vector_pdf, tmp_path):
    path, truth = vector_pdf
    cfg = Config()
    cfg.scale.denominator = 100
    res = run(path, tmp_path / "vec", cfg, truth=path.with_suffix(".truth.json"))
    assert res.report["source"]["kind"] == "vector"
    assert not (tmp_path / "vec" / "01_raster" / "binary.png").exists()
    t = res.report["truth"]["walls"]
    assert t["recall_by_length"] > 0.999 and t["endpoint_displacement_px"]["max"] < 0.01
    # windows have no glazing lines in this source: they must stay unclassified, not guessed
    kinds = sorted(o.kind for o in res.drawing.openings)
    assert kinds.count("door") == 4 and kinds.count("opening") == 3
    assert {t.text for t in res.drawing.texts} >= {"LIVING", "14000"}


def test_uncalibrated_dxf_is_unitless(vector_pdf, tmp_path):
    res = run(vector_pdf[0], tmp_path / "nc", Config())
    assert not res.drawing.scale.calibrated
    doc = ezdxf.readfile(res.outputs["dxf"])
    assert doc.header["$INSUNITS"] == 0
