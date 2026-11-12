"""Synthetic architectural test sheets with exact ground truth.

Generates a 1:100 floor plan on an A4 landscape sheet, either as a simulated
scan (rotation, blur, uneven paper, noise, specks, broken strokes, JPEG,
embedded as a full-page image) or as a clean vector PDF.  The ground truth
(wall centrelines, thicknesses, openings, scale) is written next to it and is
used by the regression tests and the validation framework.

Ground-truth coordinates are in pixels of the *unrotated* sheet at ``dpi``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pymupdf

A4_LANDSCAPE_MM = (297.0, 210.0)


@dataclass
class PlanSpec:
    scale: float = 100.0  # 1:100
    dpi: int = 300
    origin_mm: tuple[float, float] = (45.0, 45.0)  # top-left of the building on the sheet
    thin_mm: float = 0.25  # thin stroke width on paper


# Building definition in real metres (x right, y down) --------------------------------
OUTER_T = 0.25
INNER_T = 0.12
WALLS = [  # (x1, y1, x2, y2, thickness)
    (0, 0, 14, 0, OUTER_T), (14, 0, 14, 9, OUTER_T), (14, 9, 0, 9, OUTER_T), (0, 9, 0, 0, OUTER_T),
    (6, 0, 6, 9, INNER_T),
    (0, 5, 6, 5, INNER_T),
    (6, 4, 14, 4, INNER_T),
]
DIAGONAL_WALL = (8.0, 5.6, 10.6, 8.0, INNER_T)
COLUMN = (3.0, 2.5, 0.4)  # centre x, y, size
DOORS = [  # wall index, start, end along wall axis (metres), swing side (+1/-1)
    (4, 1.5, 2.4, +1),
    (5, 2.0, 2.9, -1),
    (2, 9.0, 10.0, -1),
    (6, 5.0, 5.9, +1),
]
WINDOWS = [
    (0, 2.0, 3.5),
    (1, 6.0, 7.5),
    (0, 9.0, 10.5),
]
LABELS = [("LIVING", 9.0, 2.2), ("BED 1", 2.0, 7.0), ("KITCHEN", 1.6, 3.6)]


class _Sheet:
    def __init__(self, spec: PlanSpec):
        self.spec = spec
        self.px_per_mm = spec.dpi / 25.4
        self.w = int(round(A4_LANDSCAPE_MM[0] * self.px_per_mm))
        self.h = int(round(A4_LANDSCAPE_MM[1] * self.px_per_mm))

    def P(self, x_m: float, y_m: float) -> tuple[float, float]:  # noqa: N802
        f = 1000.0 / self.spec.scale * self.px_per_mm
        return (self.spec.origin_mm[0] * self.px_per_mm + x_m * f, self.spec.origin_mm[1] * self.px_per_mm + y_m * f)

    def L(self, metres: float) -> float:  # noqa: N802
        return 1000.0 / self.spec.scale * self.px_per_mm * metres


def _wall_rect(sheet: _Sheet, x1, y1, x2, y2, t, ext=True):
    """Corner polygon (px) of a wall; ends extended by t/2 to close corners."""
    a, b = np.array(sheet.P(x1, y1)), np.array(sheet.P(x2, y2))
    d = (b - a) / np.linalg.norm(b - a)
    n = np.array([-d[1], d[0]])
    ht = sheet.L(t) / 2
    e = ht if ext else 0.0
    a2, b2 = a - d * e, b + d * e
    return np.array([a2 + n * ht, b2 + n * ht, b2 - n * ht, a2 - n * ht])


def _axis_point(wall, s):
    x1, y1, x2, y2, _ = wall
    L = math.hypot(x2 - x1, y2 - y1)
    return x1 + (x2 - x1) * s / L, y1 + (y2 - y1) * s / L


def build_ground_truth(spec: PlanSpec) -> dict:
    sheet = _Sheet(spec)
    gt_walls = []
    for wi, w in enumerate(WALLS):
        x1, y1, x2, y2, t = w
        L = math.hypot(x2 - x1, y2 - y1)
        cuts = sorted([(s, e) for (i, s, e, *_) in DOORS + [(i, s, e) for i, s, e in WINDOWS] if i == wi])
        pos = 0.0
        pieces = []
        for s, e in cuts:
            pieces.append((pos, s))
            pos = e
        pieces.append((pos, L))
        for s, e in pieces:
            if e - s > 1e-6:
                p, q = sheet.P(*_axis_point(w, s)), sheet.P(*_axis_point(w, e))
                gt_walls.append({"p1": p, "p2": q, "thickness_px": sheet.L(t), "thickness_m": t, "wall": wi})
    x1, y1, x2, y2, t = DIAGONAL_WALL
    gt_walls.append({"p1": sheet.P(x1, y1), "p2": sheet.P(x2, y2), "thickness_px": sheet.L(t), "thickness_m": t,
                     "wall": "diagonal"})
    openings = []
    for i, s, e, side in DOORS:
        openings.append({"kind": "door", "p1": sheet.P(*_axis_point(WALLS[i], s)),
                         "p2": sheet.P(*_axis_point(WALLS[i], e)), "width_m": e - s})
    for i, s, e in WINDOWS:
        openings.append({"kind": "window", "p1": sheet.P(*_axis_point(WALLS[i], s)),
                         "p2": sheet.P(*_axis_point(WALLS[i], e)), "width_m": e - s})
    cx, cy, size = COLUMN
    return {
        "scale_denominator": spec.scale,
        "dpi": spec.dpi,
        "mm_per_px_real": 25.4 / spec.dpi * spec.scale,
        "image_size": [sheet.w, sheet.h],
        "walls": gt_walls,
        "openings": openings,
        "columns": [{"center": sheet.P(cx, cy), "size_px": sheet.L(size)}],
        "known_distance": {"p1": sheet.P(0, -1.0), "p2": sheet.P(14, -1.0), "mm": 14000.0},
    }


def render_clean(spec: PlanSpec) -> np.ndarray:
    """Clean drawing (uint8, white background)."""
    sheet = _Sheet(spec)
    img = np.full((sheet.h, sheet.w), 255, np.uint8)
    thin = max(1, int(round(spec.thin_mm * sheet.px_per_mm)))
    black = 0

    for w in WALLS:
        cv2.fillPoly(img, [np.round(_wall_rect(sheet, *w)).astype(np.int32)], black, cv2.LINE_AA)
    cv2.fillPoly(img, [np.round(_wall_rect(sheet, *DIAGONAL_WALL, ext=False)).astype(np.int32)], black, cv2.LINE_AA)
    cx, cy, size = COLUMN
    p, q = sheet.P(cx - size / 2, cy - size / 2), sheet.P(cx + size / 2, cy + size / 2)
    cv2.rectangle(img, tuple(np.round(p).astype(int)), tuple(np.round(q).astype(int)), black, -1)

    def cut(wi, s, e):
        x1, y1, x2, y2, t = WALLS[wi]
        a, b = _axis_point(WALLS[wi], s), _axis_point(WALLS[wi], e)
        poly = _wall_rect(sheet, a[0], a[1], b[0], b[1], t * 1.15, ext=False)
        cv2.fillPoly(img, [np.round(poly).astype(np.int32)], 255)

    for i, s, e, side in DOORS:
        cut(i, s, e)
    for i, s, e in WINDOWS:
        cut(i, s, e)
    # door leaves and swings
    for i, s, e, side in DOORS:
        x1, y1, x2, y2, t = WALLS[i]
        hinge = np.array(sheet.P(*_axis_point(WALLS[i], s)))
        other = np.array(sheet.P(*_axis_point(WALLS[i], e)))
        d = (other - hinge) / np.linalg.norm(other - hinge)
        n = np.array([-d[1], d[0]]) * side
        r = np.linalg.norm(other - hinge)
        tip = hinge + n * r
        cv2.line(img, tuple(np.round(hinge).astype(int)), tuple(np.round(tip).astype(int)), black, thin, cv2.LINE_AA)
        a0 = math.degrees(math.atan2(d[1], d[0]))
        a1 = math.degrees(math.atan2(n[1], n[0]))
        start, end = (a0, a1) if (a1 - a0) % 360 < 180 else (a1, a0)
        if end < start:
            end += 360
        cv2.ellipse(img, tuple(np.round(hinge).astype(int)), (int(round(r)), int(round(r))), 0, start, end,
                    black, thin, cv2.LINE_AA)
    # windows: two glazing lines inside the opening
    for i, s, e in WINDOWS:
        x1, y1, x2, y2, t = WALLS[i]
        a, b = np.array(sheet.P(*_axis_point(WALLS[i], s))), np.array(sheet.P(*_axis_point(WALLS[i], e)))
        d = (b - a) / np.linalg.norm(b - a)
        n = np.array([-d[1], d[0]])
        for off in (-0.3, 0.3):
            o = n * sheet.L(t) * off
            cv2.line(img, tuple(np.round(a + o).astype(int)), tuple(np.round(b + o).astype(int)), black, thin, cv2.LINE_AA)
        for p in (a, b):  # jamb lines
            o = n * sheet.L(t) * 0.5
            cv2.line(img, tuple(np.round(p - o).astype(int)), tuple(np.round(p + o).astype(int)), black, thin, cv2.LINE_AA)
    # dimension line with ticks and text
    a, b = np.array(sheet.P(0, -1.0)), np.array(sheet.P(14, -1.0))
    cv2.line(img, tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int)), black, thin, cv2.LINE_AA)
    for p in (a, b):
        cv2.line(img, tuple(np.round(p + (-12, 12)).astype(int)), tuple(np.round(p + (12, -12)).astype(int)), black, thin)
        cv2.line(img, tuple(np.round(p + (0, -25)).astype(int)), tuple(np.round(p + (0, 40)).astype(int)), black, thin)
    fs = 1.2 * spec.dpi / 300
    mid = (a + b) / 2
    cv2.putText(img, "14000", (int(mid[0] - 70 * fs), int(mid[1] - 14)), cv2.FONT_HERSHEY_SIMPLEX, fs, black, 3, cv2.LINE_AA)
    for text, x, y in LABELS:
        p = sheet.P(x, y)
        cv2.putText(img, text, (int(p[0]), int(p[1])), cv2.FONT_HERSHEY_SIMPLEX, fs, black, 3, cv2.LINE_AA)
    cv2.putText(img, "PLAN 1:100", (int(sheet.P(0, 10.6)[0]), int(sheet.P(0, 10.6)[1])),
                cv2.FONT_HERSHEY_SIMPLEX, fs, black, 3, cv2.LINE_AA)
    return img


def degrade(img: np.ndarray, rotate_deg: float = 0.8, seed: int = 7, noise: float = 10.0,
            specks: int = 400, breaks: int = 60) -> np.ndarray:
    """Simulate a scan: rotation, blur, uneven paper, noise, specks, broken strokes."""
    rng = np.random.default_rng(seed)
    out = img.copy()
    h, w = out.shape
    # broken strokes: small white nicks on ink pixels
    ys, xs = np.nonzero(out < 128)
    if len(ys) and breaks:
        idx = rng.choice(len(ys), size=min(breaks, len(ys)), replace=False)
        for i in idx:
            cv2.circle(out, (int(xs[i]), int(ys[i])), int(rng.integers(1, 3)), 255, -1)
    if rotate_deg:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), rotate_deg, 1.0)
        out = cv2.warpAffine(out, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=255)
    out = cv2.GaussianBlur(out, (0, 0), 0.8).astype(np.float32)
    # uneven paper tone
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    out = out - 25 * (xx / w) - 15 * (yy / h)
    out += rng.normal(0, noise, out.shape).astype(np.float32)
    out = np.clip(out, 0, 255).astype(np.uint8)
    for _ in range(specks):
        cv2.circle(out, (int(rng.integers(0, w)), int(rng.integers(0, h))), int(rng.integers(1, 3)),
                   int(rng.integers(0, 90)), -1)
    return out


def write_scan_pdf(path: str | Path, spec: PlanSpec | None = None, rotate_deg: float = 0.8, seed: int = 7,
                   jpeg_quality: int = 80) -> dict:
    spec = spec or PlanSpec()
    path = Path(path)
    img = degrade(render_clean(spec), rotate_deg=rotate_deg, seed=seed)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    doc = pymupdf.open()
    wpt, hpt = A4_LANDSCAPE_MM[0] / 25.4 * 72, A4_LANDSCAPE_MM[1] / 25.4 * 72
    page = doc.new_page(width=wpt, height=hpt)
    page.insert_image(page.rect, stream=buf.tobytes())
    doc.save(path)
    doc.close()
    gt = build_ground_truth(spec)
    gt["scan"] = {"rotate_deg": rotate_deg, "seed": seed, "jpeg_quality": jpeg_quality}
    path.with_suffix(".truth.json").write_text(json.dumps(gt, indent=1))
    return gt


def write_vector_pdf(path: str | Path, spec: PlanSpec | None = None) -> dict:
    """Same plan as native vector content (filled walls, stroked lines, real text)."""
    spec = spec or PlanSpec()
    sheet = _Sheet(spec)
    k = 72.0 / spec.dpi  # px -> pt
    doc = pymupdf.open()
    page = doc.new_page(width=A4_LANDSCAPE_MM[0] / 25.4 * 72, height=A4_LANDSCAPE_MM[1] / 25.4 * 72)
    sh = page.new_shape()
    gt = build_ground_truth(spec)
    for w in gt["walls"]:
        p, q = np.array(w["p1"]) * k, np.array(w["p2"]) * k
        d = (q - p) / np.linalg.norm(q - p)
        n = np.array([-d[1], d[0]]) * w["thickness_px"] * k / 2
        pts = [pymupdf.Point(*(p + n)), pymupdf.Point(*(q + n)), pymupdf.Point(*(q - n)), pymupdf.Point(*(p - n))]
        sh.draw_polyline(pts + [pts[0]])
    sh.finish(color=None, fill=(0, 0, 0), width=0)
    for i, s, e, side in DOORS:
        hinge = np.array(sheet.P(*_axis_point(WALLS[i], s))) * k
        other = np.array(sheet.P(*_axis_point(WALLS[i], e))) * k
        d = (other - hinge) / np.linalg.norm(other - hinge)
        n = np.array([-d[1], d[0]]) * side
        r = np.linalg.norm(other - hinge)
        sh.draw_line(pymupdf.Point(*hinge), pymupdf.Point(*(hinge + n * r)))
        sh.draw_sector(pymupdf.Point(*hinge), pymupdf.Point(*other),
                       90 if side < 0 else -90, fullSector=False)
    sh.finish(color=(0, 0, 0), width=spec.thin_mm / 25.4 * 72)
    page.insert_text(pymupdf.Point(*(np.array(sheet.P(6, -1.2)) * k)), "14000", fontsize=9)
    for text, x, y in LABELS:
        page.insert_text(pymupdf.Point(*(np.array(sheet.P(x, y)) * k)), text, fontsize=9)
    sh.commit()
    doc.save(path)
    doc.close()
    Path(path).with_suffix(".truth.json").write_text(json.dumps(gt, indent=1))
    return gt
