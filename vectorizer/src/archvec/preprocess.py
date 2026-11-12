"""Stage B - image preprocessing.

The source raster is never modified.  Every operation is recorded in
``history`` and the only geometric operation (deskew rotation) is kept as an
invertible 2x3 affine matrix, so any extracted coordinate can be mapped back
to the original scan.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from .config import PreprocessConfig, mm_to_px

log = logging.getLogger(__name__)


@dataclass
class PreprocessResult:
    source: np.ndarray  # untouched input (uint8 gray)
    gray: np.ndarray  # deskewed / denoised gray
    binary: np.ndarray  # uint8 {0,1}, ink = 1
    affine: np.ndarray  # 2x3, source px -> working px
    skew_deg: float
    threshold: float
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_source(self, x: float, y: float) -> tuple[float, float]:
        inv = cv2.invertAffineTransform(self.affine)
        return (float(inv[0, 0] * x + inv[0, 1] * y + inv[0, 2]),
                float(inv[1, 0] * x + inv[1, 1] * y + inv[1, 2]))


def estimate_skew(gray: np.ndarray, max_skew_deg: float = 5.0) -> tuple[float, int]:
    """Estimate drawing skew from long near-orthogonal line segments (LSD).

    Returns (angle_deg, n_lines).  The angle is the rotation that, passed to
    ``cv2.getRotationMatrix2D``, straightens the image.
    """
    h, w = gray.shape
    f = min(1.0, 2500.0 / max(h, w))
    small = cv2.resize(gray, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA) if f < 1 else gray
    lsd = cv2.createLineSegmentDetector()
    lines = lsd.detect(small)[0]
    if lines is None:
        return 0.0, 0
    lines = lines.reshape(-1, 4)
    dx, dy = lines[:, 2] - lines[:, 0], lines[:, 3] - lines[:, 1]
    length = np.hypot(dx, dy)
    ang = np.degrees(np.arctan2(dy, dx))
    dev = (ang + 45.0) % 90.0 - 45.0  # deviation from nearest axis
    min_len = 0.04 * max(small.shape)
    keep = (np.abs(dev) <= max_skew_deg) & (length >= min_len)
    if keep.sum() < 3:
        keep = (np.abs(dev) <= max_skew_deg) & (length >= min_len / 3)
    if keep.sum() < 3:
        return 0.0, int(keep.sum())
    d, wgt = dev[keep], length[keep]
    order = np.argsort(d)
    cum = np.cumsum(wgt[order])
    median = float(d[order][np.searchsorted(cum, cum[-1] / 2)])
    # refine: weighted mean of inliers around the median
    inl = np.abs(d - median) < 0.3
    angle = float(np.average(d[inl], weights=wgt[inl])) if inl.any() else median
    return angle, int(keep.sum())


def remove_isolated_specks(binary: np.ndarray, max_area_px: float, radius_px: float) -> tuple[np.ndarray, int]:
    """Remove small blobs that have no other ink within ``radius_px``.

    Text dots, decimal points and hatch dots are kept because other ink is nearby;
    isolated dust/toner specks are removed."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    small = stats[:, cv2.CC_STAT_AREA] <= max_area_px
    small[0] = False
    if not small.any():
        return binary, 0
    big_mask = (~small)[labels].astype(np.uint8) & binary
    r = max(1, int(round(radius_px)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    near_big = cv2.dilate(big_mask, k)
    out = binary.copy()
    removed = 0
    for i in np.nonzero(small)[0]:
        x, y, w, h = stats[i, :4]
        sub = labels[y:y + h, x:x + w] == i
        if near_big[y:y + h, x:x + w][sub].any():
            continue
        # small blobs close to each other (dotted lines, stipple) support each other
        x0, y0 = max(0, x - r), max(0, y - r)
        win = labels[y0:y + h + r + 1, x0:x + w + r + 1]
        others = np.unique(win[(win != i) & (win != 0)])
        if any(small[o] for o in others):
            continue
        out[y:y + h, x:x + w][sub] = 0
        removed += 1
    return out, removed


def preprocess(gray: np.ndarray, dpi: float, cfg: PreprocessConfig, allow_deskew: bool = True) -> PreprocessResult:
    if gray.dtype != np.uint8 or gray.ndim != 2:
        raise ValueError("preprocess expects a 2-D uint8 grayscale image")
    history: list[dict[str, Any]] = []
    img = gray
    h, w = img.shape
    affine = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    skew = 0.0

    if cfg.perspective:
        history.append({"op": "perspective", "status": "not implemented - skipped"})

    if cfg.deskew and allow_deskew:
        skew, n = estimate_skew(img, cfg.max_skew_deg)
        history.append({"op": "estimate_skew", "angle_deg": round(skew, 4), "lines_used": n})
        if abs(skew) >= 0.03:
            affine = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), skew, 1.0)
            img = cv2.warpAffine(img, affine, (w, h), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=255)
            history.append({"op": "rotate", "angle_deg": round(skew, 4), "center": [w / 2.0, h / 2.0]})
        else:
            skew = 0.0
    elif cfg.deskew:
        history.append({"op": "deskew", "status": "disabled for this input"})

    if cfg.denoise == "median" and cfg.median_ksize >= 3:
        k = cfg.median_ksize | 1
        img = cv2.medianBlur(img, k)
        history.append({"op": "median_blur", "ksize": k})
    elif cfg.denoise == "nlmeans":
        img = cv2.fastNlMeansDenoising(img, None, h=12, templateWindowSize=7, searchWindowSize=21)
        history.append({"op": "nlmeans", "h": 12})

    if cfg.clahe:
        img = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(img)
        history.append({"op": "clahe", "clip": 2.0})

    if cfg.threshold == "adaptive":
        block = max(3, int(mm_to_px(cfg.adaptive_block_mm, dpi)) | 1)
        binary = cv2.adaptiveThreshold(img, 1, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
                                       block, cfg.adaptive_c)
        thr = float("nan")
        # suppress adaptive-threshold noise in blank areas: require global darkness too
        otsu, _ = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        binary &= (img < min(250, otsu + 40)).astype(np.uint8)
        history.append({"op": "adaptive_threshold", "block_px": block, "C": cfg.adaptive_c})
    else:
        thr, _ = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        binary = (img <= thr).astype(np.uint8)  # cv2 Otsu: pixels > thr are background
        history.append({"op": "otsu_threshold", "threshold": float(thr)})

    if cfg.close_gaps_mm > 0:
        k = max(1, int(round(mm_to_px(cfg.close_gaps_mm, dpi))))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
        history.append({"op": "close_gaps", "kernel_px": k})

    min_area = mm_to_px(1.0, dpi) ** 2 * cfg.min_component_area_mm2
    if min_area >= 1:
        n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        small = np.where(stats[:, cv2.CC_STAT_AREA] < min_area)[0]
        small = small[small != 0]
        if len(small):
            binary[np.isin(labels, small)] = 0
        history.append({"op": "remove_specks", "min_area_px": round(min_area, 1), "removed": int(len(small))})

    if cfg.isolated_speck_area_mm2 > 0:
        binary, removed = remove_isolated_specks(binary, mm_to_px(1.0, dpi) ** 2 * cfg.isolated_speck_area_mm2,
                                                 mm_to_px(cfg.isolation_radius_mm, dpi))
        history.append({"op": "remove_isolated_specks", "max_area_mm2": cfg.isolated_speck_area_mm2,
                        "radius_mm": cfg.isolation_radius_mm, "removed": removed})

    ink = float(binary.mean())
    history.append({"op": "summary", "ink_fraction": round(ink, 5)})
    if ink > 0.5:
        log.warning("more than half of the page is ink - check threshold / inversion")
    return PreprocessResult(gray, img, binary, affine, skew, float(thr), history)
