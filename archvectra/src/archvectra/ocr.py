"""Reading numbers and grid labels on the drawing (OCR).

Uses RapidOCR (PaddleOCR PP-OCR models in ONNX format, Apache-2.0; ~14 MB, runs
offline on the CPU).  This is the one place where a learned model clearly beats
hand-written rules: reading dimension values ("6000", "4.50") and grid labels
("A", "3").  Geometry is never taken from the model - only text values, which are
then cross-checked against the measured drawing before they are used.

Text is located geometrically (annotation blobs grouped into words) and only
groups at plausible places (between grid axes, inside grid bubbles) are read, so
OCR time stays small even on very large sheets.  Each crop is tried upright and
rotated by +-90 degrees; the most confident reading wins.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

log = logging.getLogger(__name__)

_ENGINE = None
_ENGINE_FAILED = False


def available() -> bool:
    return _engine() is not None


def _engine():
    global _ENGINE, _ENGINE_FAILED
    if _ENGINE is None and not _ENGINE_FAILED:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _ENGINE = RapidOCR()
        except Exception as exc:  # noqa: BLE001 - OCR is optional
            log.warning("OCR not available (%s); dimension text will not be read", exc)
            _ENGINE_FAILED = True
    return _ENGINE


@dataclass
class TextGroup:
    x: int
    y: int
    w: int
    h: int
    text: str = ""
    score: float = 0.0
    angle: int = 0  # 0 = horizontal, 90 = reads bottom-to-top, -90 = top-to-bottom
    value: float | None = None
    attrs: dict = field(default_factory=dict)

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def group_text(anno_mask: np.ndarray, join_px: int) -> list[TextGroup]:
    """Group annotation blobs into words/labels (characters closer than ``join_px``)."""
    if not anno_mask.any():
        return []
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * join_px + 1, 2 * join_px + 1))
    joined = cv2.dilate(anno_mask, k)
    n, _, st, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        # shrink back by the dilation
        out.append(TextGroup(int(x + join_px), int(y + join_px), int(max(1, w - 2 * join_px)),
                             int(max(1, h - 2 * join_px))))
    return out


def _prep(crop_ink: np.ndarray, target_h: int = 48) -> np.ndarray:
    """Ink mask crop -> dark text on white, padded, scaled to the recogniser's height."""
    img = ((1 - crop_ink) * 255).astype(np.uint8)
    pad = max(6, img.shape[0] // 3)
    img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    s = target_h / img.shape[0]
    if s != 1:
        img = cv2.resize(img, (max(8, int(img.shape[1] * s)), target_h),
                         interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    return img


def _read(img: np.ndarray) -> tuple[str, float]:
    eng = _engine()
    if eng is None:
        return "", 0.0
    bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img
    try:
        # recogniser only: the crop is already one line of text (the combined call
        # re-runs text detection, which mis-crops short labels)
        res, _ = eng.text_recognizer([bgr])
    except Exception as exc:  # noqa: BLE001
        log.debug("OCR failed on a crop: %s", exc)
        return "", 0.0
    if not res:
        return "", 0.0
    text, score = res[0][0], res[0][1]
    return str(text).strip().replace(" ", ""), float(score)


def read_group(binary: np.ndarray, g: TextGroup, rotations=(0, 90, -90), pattern: re.Pattern | None = None) -> TextGroup:
    """OCR one group; tries upright and rotated crops, keeps the best (pattern-matching) reading."""
    m = 2
    y0, x0 = max(0, g.y - m), max(0, g.x - m)
    crop = binary[y0:g.y + g.h + m, x0:g.x + g.w + m]
    if crop.size == 0:
        return g
    best = ("", 0.0, 0)
    for rot in rotations:
        c = crop
        if rot == 90:  # text reading bottom-to-top -> rotate clockwise to make it upright
            c = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
        elif rot == -90:
            c = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if rot == 0 and crop.shape[0] > 2.5 * crop.shape[1] and len(rotations) > 1:
            continue  # tall group: not horizontal text
        if rot != 0 and crop.shape[1] > 2.5 * crop.shape[0]:
            continue  # wide group: not vertical text
        text, score = _read(_prep(c))
        ok = bool(pattern.fullmatch(text)) if pattern is not None else bool(text)
        if ok and score > best[1]:
            best = (text, score, rot)
    g.text, g.score, g.angle = best
    return g


NUMBER_RE = re.compile(r"\d{1,3}(?:[.,]\d{1,3})?|\d{2,6}")
LABEL_RE = re.compile(r"[A-Za-z]{1,2}\d?|\d{1,2}[A-Za-z]?")


def parse_number(text: str) -> float | None:
    if not text or not NUMBER_RE.fullmatch(text):
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None
