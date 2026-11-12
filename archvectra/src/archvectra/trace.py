"""Outline tracing of annotation / residual ink.

Text, symbols and any ink the geometric stages could not explain are kept as
filled outline polygons on the annotation layer, so nothing visible is lost and
nothing is mistaken for CAD linework.

Backends:
* ``potrace`` (GPL-2.0) - invoked as an external program (``-b geojson``) when
  it is on PATH; never linked, so the project licence is unaffected.
* ``contour`` - OpenCV contours + Douglas-Peucker (always available).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

from .model import LAYER_ANNOTATION, Polygon

log = logging.getLogger(__name__)


def potrace_available() -> str | None:
    return shutil.which("potrace")


def trace_contours(mask: np.ndarray, epsilon: float = 0.6, min_area: float = 4.0) -> list[Polygon]:
    out: list[Polygon] = []
    if not mask.any():
        return out
    cnts, hier = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return out
    hier = hier[0]
    for i, c in enumerate(cnts):
        if hier[i][3] != -1:  # holes are attached to their parent
            continue
        if cv2.contourArea(c) < min_area:
            continue
        ext = cv2.approxPolyDP(c, epsilon, True).reshape(-1, 2)
        if len(ext) < 3:
            continue
        holes = []
        k = hier[i][2]
        while k != -1:
            h = cv2.approxPolyDP(cnts[k], epsilon, True).reshape(-1, 2)
            if len(h) >= 3 and cv2.contourArea(cnts[k]) >= min_area / 2:
                holes.append([(float(x) + 0.5, float(y) + 0.5) for x, y in h])
            k = hier[k][0]
        out.append(Polygon([(float(x) + 0.5, float(y) + 0.5) for x, y in ext], holes, LAYER_ANNOTATION, True,
                           0.9, "contour"))
    return out


def trace_potrace(mask: np.ndarray, turd: int = 2) -> list[Polygon]:
    exe = potrace_available()
    if not exe:
        raise FileNotFoundError("potrace not found on PATH")
    h, w = mask.shape
    with tempfile.TemporaryDirectory() as td:
        pbm = Path(td) / "in.pbm"
        # PBM: 1 = black
        bits = np.packbits(mask.astype(np.uint8), axis=1)
        pbm.write_bytes(f"P4\n{w} {h}\n".encode() + bits.tobytes())
        out = Path(td) / "out.json"
        subprocess.run([exe, "-b", "geojson", "-t", str(turd), "-a", "0.8", "-O", "0.2", "-u", "4",
                        "-o", str(out), str(pbm)], check=True, capture_output=True)
        data = json.loads(out.read_text())
    polys: list[Polygon] = []
    for feat in data.get("features", []):
        g = feat.get("geometry", {})
        rings_sets = [g["coordinates"]] if g.get("type") == "Polygon" else g.get("coordinates", [])
        for rings in rings_sets:
            if not rings:
                continue
            conv = [[(float(x), float(h - y)) for x, y in r[:-1]] for r in rings]  # potrace y is up
            if len(conv[0]) >= 3:
                polys.append(Polygon(conv[0], [r for r in conv[1:] if len(r) >= 3], LAYER_ANNOTATION, True,
                                     0.9, "potrace"))
    return polys


def trace(mask: np.ndarray, backend: str = "auto") -> tuple[list[Polygon], str]:
    if backend in ("auto", "potrace") and potrace_available():
        try:
            return trace_potrace(mask), "potrace"
        except Exception as exc:  # noqa: BLE001 - fall back, but say so
            if backend == "potrace":
                raise
            log.warning("potrace failed (%s); falling back to contour tracing", exc)
    elif backend == "potrace":
        raise FileNotFoundError("annotation_backend = potrace but potrace is not installed")
    return trace_contours(mask), "contour"
