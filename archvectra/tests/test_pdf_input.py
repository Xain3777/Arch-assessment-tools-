"""Stage A - PDF analysis, raster acquisition and vector extraction."""

import numpy as np
import pymupdf
import pytest

from archvectra.pdf_input import PdfInputError, analyze_pdf, extract_vectors, load_raster


def test_scan_is_classified_raster(scan_pdf):
    path, _ = scan_pdf
    (info,) = analyze_pdf(path)
    assert info.kind == "raster"
    assert len(info.images) == 1
    assert info.image_coverage > 0.95
    assert info.images[0].axis_aligned
    assert abs(info.images[0].effective_dpi - 300) < 1


def test_vector_is_classified_vector(vector_pdf):
    path, _ = vector_pdf
    (info,) = analyze_pdf(path)
    assert info.kind == "vector"
    assert info.vector_items > 10 and not info.images


def test_hybrid_and_empty_classification(tmp_path, scan_pdf):
    doc = pymupdf.open()
    doc.new_page()
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(0, 0, 200, 200), filename=None, stream=_png())
    sh = page.new_shape()
    for i in range(60):
        sh.draw_line((300, 10 + i * 5), (500, 10 + i * 5))
    sh.finish(color=(0, 0, 0))
    sh.commit()
    p = tmp_path / "mixed.pdf"
    doc.save(p)
    kinds = [i.kind for i in analyze_pdf(p)]
    assert kinds == ["empty", "hybrid"]


def _png():
    import cv2

    ok, buf = cv2.imencode(".png", np.full((50, 50), 128, np.uint8))
    return buf.tobytes()


def test_native_image_is_used_without_resampling(scan_pdf):
    path, truth = scan_pdf
    rp = load_raster(path, 0, dpi=150, prefer_native=True)
    assert rp.method == "native-image"
    assert rp.gray.shape == (truth["image_size"][1], truth["image_size"][0])
    assert abs(rp.dpi - 300) < 0.5  # requested 150 dpi is ignored in favour of the scan's own pixels
    a, b, c, d, e, f = rp.px_to_pt
    assert b == 0 and c == 0 and abs(a - 72 / 300) < 1e-3


def test_render_fallback(vector_pdf):
    path, _ = vector_pdf
    rp = load_raster(path, 0, dpi=100)
    assert rp.method == "rendered"
    assert abs(rp.dpi - 100) < 0.5
    assert rp.gray.dtype == np.uint8 and rp.gray.min() < 50


def test_bad_page_raises(scan_pdf):
    with pytest.raises(PdfInputError):
        load_raster(scan_pdf[0], 5, 300)


def test_vector_extraction_keeps_paths_text_and_style(vector_pdf):
    path, _ = vector_pdf
    vc = extract_vectors(path, 0)
    assert vc.stats["fills"] >= 15  # every wall piece becomes its own filled polygon
    assert vc.stats["curves"] >= 4  # door swings
    assert {t.text for t in vc.texts} >= {"LIVING", "KITCHEN", "14000"}
    assert all(s.attrs["style"]["stroke"] == (0.0, 0.0, 0.0) for s in vc.segments)


def test_large_tiled_scan_is_rendered_at_reduced_dpi(tmp_path):
    """A big sheet made of many image tiles must not fail; resolution is lowered to fit."""
    import cv2

    doc = pymupdf.open()
    page = doc.new_page(width=3400, height=2400)  # larger than A0 landscape
    tile = np.full((200, 200), 255, np.uint8)
    cv2.line(tile, (0, 100), (199, 100), 0, 4)
    ok, buf = cv2.imencode(".png", tile)
    for i in range(13):
        for j in range(8):  # 104 tiles, 200 px over 261 x 300 pt -> ~55-48 dpi native
            page.insert_image(pymupdf.Rect(i * 3400 / 13, j * 300, (i + 1) * 3400 / 13, (j + 1) * 300),
                              stream=buf.tobytes())
    p = tmp_path / "tiled.pdf"
    doc.save(p)
    (info,) = analyze_pdf(p)
    assert info.kind == "raster" and len(info.images) == 104
    rp = load_raster(p, 0, dpi=300, max_pixels=20_000_000, min_dpi=10)
    assert rp.method == "rendered"
    assert rp.gray.size <= 20_000_000 * 1.01
    with pytest.raises(PdfInputError):
        load_raster(p, 0, dpi=300, max_pixels=20_000_000, min_dpi=150)
