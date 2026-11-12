"""Quality validation.

Two levels:

1. **Source agreement** (always available): the exported clean PDF is
   rasterised back into the working frame and compared with the binarised
   source - ink precision / recall within a tolerance band, symmetric chamfer
   distances, and an overlay image (red = source ink missing from the output,
   blue = output ink not supported by the source).  This measures geometric
   alignment, false-positive and missing geometry - it does not prove
   dimensional correctness.
2. **Ground truth** (when a truth JSON is supplied, e.g. synthetic sheets or
   hand-digitised references): wall precision/recall by length, endpoint
   displacement, thickness error, opening detection/classification and scale
   error, in pixels and real millimetres.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pymupdf

from .model import Drawing, Segment


# --------------------------------------------------------------------------- source agreement
def render_pdf_to_frame(pdf_path: str | Path, drawing: Drawing) -> np.ndarray:
    a, b, c, d, e, f = drawing.px_to_pt
    with pymupdf.open(pdf_path) as doc:
        page = doc[0]
        clip = pymupdf.Rect(e, f, e + a * drawing.width, f + d * drawing.height)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1 / a, 1 / d), clip=clip, colorspace=pymupdf.csGRAY, alpha=False)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, : pix.width]
    out = np.full((drawing.height, drawing.width), 255, np.uint8)
    h, w = min(img.shape[0], drawing.height), min(img.shape[1], drawing.width)
    out[:h, :w] = img[:h, :w]
    return (out < 128).astype(np.uint8)


def ink_metrics(source: np.ndarray, recon: np.ndarray, tol_px: float) -> dict[str, float]:
    src_dt = cv2.distanceTransform((1 - source).astype(np.uint8), cv2.DIST_L2, 5)
    rec_dt = cv2.distanceTransform((1 - recon).astype(np.uint8), cv2.DIST_L2, 5)
    n_src, n_rec = int(source.sum()), int(recon.sum())
    if n_src == 0 or n_rec == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "source_ink_px": n_src, "output_ink_px": n_rec}
    d_rec_to_src = src_dt[recon > 0]
    d_src_to_rec = rec_dt[source > 0]
    p = float((d_rec_to_src <= tol_px).mean())
    r = float((d_src_to_rec <= tol_px).mean())
    return {
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
        "output_to_source_mean_px": round(float(d_rec_to_src.mean()), 3),
        "output_to_source_p95_px": round(float(np.percentile(d_rec_to_src, 95)), 3),
        "source_to_output_mean_px": round(float(d_src_to_rec.mean()), 3),
        "source_to_output_p95_px": round(float(np.percentile(d_src_to_rec, 95)), 3),
        "source_ink_px": n_src,
        "output_ink_px": n_rec,
        "tolerance_px": round(tol_px, 2),
    }


def overlay_image(source: np.ndarray, recon: np.ndarray, tol_px: float) -> np.ndarray:
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * int(math.ceil(tol_px)) + 1,) * 2)
    src_d = cv2.dilate(source, k)
    rec_d = cv2.dilate(recon, k)
    img = np.full(source.shape + (3,), 255, np.uint8)
    img[(source > 0) & (rec_d > 0)] = (150, 150, 150)  # agreement (grey)
    img[(recon > 0) & (src_d > 0) & (source == 0)] = (90, 90, 90)
    img[(source > 0) & (rec_d == 0)] = (0, 0, 230)  # missing in output (red, BGR)
    img[(recon > 0) & (src_d == 0)] = (230, 80, 0)  # extra in output (blue)
    return img


def comparison_image(original: np.ndarray, recon: np.ndarray, overlay: np.ndarray, max_width: int) -> np.ndarray:
    a = cv2.cvtColor(original, cv2.COLOR_GRAY2BGR)
    b = cv2.cvtColor(((1 - recon) * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    h = max(a.shape[0], b.shape[0], overlay.shape[0])

    def pad(x):
        return cv2.copyMakeBorder(x, 0, h - x.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))

    sep = np.full((h, 12, 3), 60, np.uint8)
    row = np.hstack([pad(a), sep, pad(b), sep, pad(overlay)])
    scale = min(1.0, max_width / row.shape[1])
    if scale < 1:
        row = cv2.resize(row, (int(row.shape[1] * scale), int(row.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    bar = np.full((60, row.shape[1], 3), 255, np.uint8)
    w3 = row.shape[1] // 3
    for i, label in enumerate(["ORIGINAL (source raster)", "RECONSTRUCTED (clean vector PDF)",
                               "OVERLAY  grey=match  red=missing  blue=extra"]):
        cv2.putText(bar, label, (i * w3 + 12, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA)
    return np.vstack([bar, row])


# --------------------------------------------------------------------------- ground truth
def _seg_from_truth(w: dict) -> Segment:
    (x1, y1), (x2, y2) = w["p1"], w["p2"]
    return Segment(x1, y1, x2, y2, w.get("thickness_px", 1.0), "wall")


def _match(gt: Segment, det: Segment, dist_tol: float, ang_tol: float = 3.0) -> float:
    """Return overlap length of det on gt if they describe the same wall, else 0."""
    d = abs(gt.angle - det.angle) % 180
    if min(d, 180 - d) > ang_tol:
        return 0.0
    p, q = np.array([gt.x1, gt.y1]), np.array([gt.x2, gt.y2])
    L = float(np.linalg.norm(q - p))
    if L == 0:
        return 0.0
    u = (q - p) / L
    n = np.array([-u[1], u[0]])
    a, b = np.array([det.x1, det.y1]), np.array([det.x2, det.y2])
    if max(abs(float((a - p) @ n)), abs(float((b - p) @ n))) > dist_tol:
        return 0.0
    t0, t1 = sorted([float((a - p) @ u), float((b - p) @ u)])
    return max(0.0, min(L, t1) - max(0.0, t0))


def _rescale_truth(truth: dict[str, Any], k: float) -> dict[str, Any]:
    t = json.loads(json.dumps(truth))
    for w in t.get("walls", []):
        w["p1"] = [v * k for v in w["p1"]]
        w["p2"] = [v * k for v in w["p2"]]
        w["thickness_px"] = w.get("thickness_px", 1.0) * k
    for o in t.get("openings", []):
        o["p1"] = [v * k for v in o["p1"]]
        o["p2"] = [v * k for v in o["p2"]]
    if t.get("mm_per_px_real"):
        t["mm_per_px_real"] /= k
    return t


def truth_metrics(drawing: Drawing, truth: dict[str, Any], tol_px: float) -> dict[str, Any]:
    if truth.get("dpi") and abs(truth["dpi"] - drawing.dpi) / drawing.dpi > 0.001:
        truth = _rescale_truth(truth, drawing.dpi / truth["dpi"])  # e.g. vector input in PDF points
    gt_walls = [_seg_from_truth(w) for w in truth.get("walls", [])]
    det = drawing.walls()
    mm_real = truth.get("mm_per_px_real")
    res: dict[str, Any] = {}
    gt_len = sum(w.length for w in gt_walls)
    det_len = sum(w.length for w in det)
    matched_gt = 0.0
    disp: list[float] = []
    thick_err: list[float] = []
    det_used = np.zeros(len(det))
    for g in gt_walls:
        tol = tol_px + g.thickness / 2
        ovs = [_match(g, d, tol) for d in det]
        for k, ov in enumerate(ovs):
            det_used[k] += ov
        matched_gt += min(sum(ovs), g.length)
        if ovs and max(ovs) / g.length > 0.5:
            best_d = det[int(np.argmax(ovs))]
            thick_err.append(abs(best_d.thickness - g.thickness))
            # endpoint displacement: each GT endpoint to the nearest detected wall endpoint
            ends = [(d.x1, d.y1) for d in det] + [(d.x2, d.y2) for d in det]
            for e in ((g.x1, g.y1), (g.x2, g.y2)):
                disp.append(min(math.dist(e, x) for x in ends))
    matched_det = float(sum(min(u, d.length) for u, d in zip(det_used, det)))
    res["walls"] = {
        "gt_count": len(gt_walls),
        "detected_count": len(det),
        "recall_by_length": round(matched_gt / gt_len, 4) if gt_len else None,
        "precision_by_length": round(matched_det / det_len, 4) if det_len else None,
        "endpoint_displacement_px": _stats(disp),
        "thickness_error_px": _stats(thick_err),
    }
    if mm_real:
        res["walls"]["endpoint_displacement_real_mm"] = _stats([v * mm_real for v in disp])
        res["walls"]["thickness_error_real_mm"] = _stats([v * mm_real for v in thick_err])
    # openings
    gt_open = truth.get("openings", [])
    hits, kind_ok, width_err = 0, 0, []
    used = set()
    for o in gt_open:
        m = np.mean([o["p1"], o["p2"]], axis=0)
        w = math.dist(o["p1"], o["p2"])
        best = None
        for k, d in enumerate(drawing.openings):
            if k in used:
                continue
            dm = np.mean([d.p1, d.p2], axis=0)
            dist = float(np.linalg.norm(dm - m))
            if dist <= 0.5 * w and (best is None or dist < best[0]):
                best = (dist, k, d)
        if best:
            used.add(best[1])
            hits += 1
            kind_ok += int(best[2].kind == o["kind"])
            width_err.append(abs(best[2].width - w))
    res["openings"] = {
        "gt_count": len(gt_open),
        "detected_count": len(drawing.openings),
        "matched": hits,
        "kind_correct": kind_ok,
        "false_positives": len(drawing.openings) - hits,
        "width_error_px": _stats(width_err),
    }
    if mm_real and drawing.scale.calibrated:
        res["scale"] = {"truth_mm_per_px": mm_real, "used_mm_per_px": drawing.scale.mm_per_unit,
                        "relative_error": round(abs(drawing.scale.mm_per_unit - mm_real) / mm_real, 6)}
    return res


def _stats(v: list[float]) -> dict[str, float] | None:
    if not v:
        return None
    a = np.asarray(v, dtype=float)
    return {"n": int(a.size), "mean": round(float(a.mean()), 3), "max": round(float(a.max()), 3),
            "p95": round(float(np.percentile(a, 95)), 3)}


def write_markdown(report: dict[str, Any], path: str | Path) -> None:
    lines = ["# archvectra validation report", ""]
    src = report.get("source", {})
    lines += [f"- Input: `{src.get('file')}` page {src.get('page')} - classified **{src.get('kind')}**",
              f"- Working resolution: {report.get('dpi', 0):.1f} units/inch; method: {src.get('raster_method', '-')}",
              f"- Scale: {report.get('scale', {}).get('source')} "
              f"({'calibrated' if report.get('scale', {}).get('calibrated') else 'NOT calibrated'})", ""]
    for note in report.get("scale", {}).get("notes", []):
        lines.append(f"  - {note}")
    lines += ["", "## Reconstruction summary", "", "```json", json.dumps(report.get("summary", {}), indent=1), "```", ""]
    for key, title in (("ink_all", "Source agreement - all ink"), ("ink_geometry", "Source agreement - geometry only")):
        m = report.get(key)
        if m:
            lines += [f"## {title}", "", "| metric | value |", "|---|---|"]
            lines += [f"| {k} | {v} |" for k, v in m.items()]
            lines.append("")
    if report.get("truth"):
        lines += ["## Ground-truth comparison", "", "```json", json.dumps(report["truth"], indent=1), "```", ""]
    flags = report.get("flags_by_code", {})
    if flags:
        lines += ["## Review flags", "", "| code | count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in flags.items()]
        lines.append("")
    lines += ["## Interpretation", "",
              "Source-agreement metrics show how well the output reproduces the scanned ink within the stated "
              "tolerance. They do not prove dimensional accuracy; that requires a calibrated scale and ground-"
              "truth or field measurements. Items listed under review flags were not resolved automatically.", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
