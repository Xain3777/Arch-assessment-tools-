"""Stage B - preprocessing: deskew accuracy, binarisation, speck removal, history."""

import cv2
import numpy as np
import pytest

from archvectra.config import PreprocessConfig
from archvectra.preprocess import estimate_skew, preprocess
from archvectra.synthetic import PlanSpec, degrade, render_clean


@pytest.fixture(scope="module")
def clean():
    return render_clean(PlanSpec(dpi=150))


@pytest.mark.parametrize("angle", [-2.5, -0.6, 0.0, 1.3])
def test_skew_is_recovered(clean, angle):
    img = degrade(clean, rotate_deg=angle, seed=3, specks=0, breaks=0)
    est, n = estimate_skew(img, 5.0)
    assert n >= 3
    # straightening rotation is the negative of the applied one
    assert abs(est + angle) < 0.1


def test_preprocess_straightens_and_binarises(clean):
    img = degrade(clean, rotate_deg=1.0, seed=1)
    res = preprocess(img, 150, PreprocessConfig())
    assert res.binary.dtype == np.uint8 and set(np.unique(res.binary)) <= {0, 1}
    assert abs(res.skew_deg + 1.0) < 0.1
    # binary should agree with the clean drawing after straightening
    ref = (clean < 128).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    agree = (res.binary & cv2.dilate(ref, k)).sum() / res.binary.sum()
    assert agree > 0.95  # remaining disagreement: simulated specks / JPEG-like noise
    ops = [h["op"] for h in res.history]
    assert ops[:2] == ["estimate_skew", "rotate"] and "remove_specks" in ops


def test_source_is_untouched_and_mapping_is_invertible(clean):
    img = degrade(clean, rotate_deg=1.5, seed=2)
    before = img.copy()
    res = preprocess(img, 150, PreprocessConfig())
    assert np.array_equal(img, before) and res.source is img
    x, y = 400.0, 300.0
    M = res.affine
    wx, wy = M[0, 0] * x + M[0, 1] * y + M[0, 2], M[1, 0] * x + M[1, 1] * y + M[1, 2]
    bx, by = res.to_source(wx, wy)
    assert abs(bx - x) < 1e-6 and abs(by - y) < 1e-6


def test_specks_are_removed():
    img = np.full((400, 400), 255, np.uint8)
    cv2.line(img, (20, 200), (380, 200), 0, 3)
    for x in range(30, 380, 40):
        cv2.circle(img, (x, 60), 1, 0, -1)
    res = preprocess(img, 300, PreprocessConfig(deskew=False, min_component_area_mm2=0.05))
    assert res.binary[50:70].sum() == 0  # specks gone
    assert res.binary[195:205].sum() > 300 * 2  # line kept


def test_adaptive_threshold_handles_uneven_paper(clean):
    img = degrade(clean, rotate_deg=0, seed=4)
    img = np.clip(img.astype(int) - np.linspace(0, 90, img.shape[1])[None, :], 0, 255).astype(np.uint8)
    res = preprocess(img, 150, PreprocessConfig(deskew=False, threshold="adaptive"))
    ink = res.binary.mean()
    assert 0.005 < ink < 0.1


def test_isolated_specks_removed_but_text_dots_kept():
    from archvectra.preprocess import remove_isolated_specks

    b = np.zeros((300, 300), np.uint8)
    cv2.circle(b, (250, 250), 2, 1, -1)  # isolated speck
    cv2.line(b, (50, 100), (50, 140), 1, 4)  # letter stem ...
    cv2.circle(b, (50, 88), 2, 1, -1)  # ... with its i-dot 8 px above
    out, removed = remove_isolated_specks(b, max_area_px=30, radius_px=12)
    assert removed == 1
    assert out[245:256, 245:256].sum() == 0
    assert out[85:92, 47:54].sum() > 0
