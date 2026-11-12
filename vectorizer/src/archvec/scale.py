"""Stage F - scale calibration.

Supported now: manual scale (1:N), known-distance calibration, and the
consistency check between them.  Scale-bar detection and reading dimension
text (OCR) are planned (docs/ROADMAP.md) - until then the system reports the
drawing as *uncalibrated* rather than guessing.
"""

from __future__ import annotations

import math

from .config import ScaleConfig
from .model import Scale


def build_scale(cfg: ScaleConfig, dpi: float) -> Scale:
    paper = 25.4 / dpi
    sc = Scale(paper_mm_per_unit=paper)
    nominal = paper * cfg.denominator if cfg.denominator else None
    measured = None
    if cfg.known_distance_px and cfg.known_distance_mm:
        x1, y1, x2, y2 = cfg.known_distance_px
        d = math.hypot(x2 - x1, y2 - y1)
        if d <= 0:
            raise ValueError("scale.known_distance_px has zero length")
        measured = cfg.known_distance_mm / d
    if measured is not None:
        sc.mm_per_unit, sc.source = measured, "known-distance"
        sc.denominator = measured / paper
        if nominal is not None:
            dev = abs(measured - nominal) / nominal
            sc.notes.append(f"known distance implies 1:{sc.denominator:.1f}; nominal 1:{cfg.denominator:g} "
                            f"(deviation {dev * 100:.2f}%)")
            if dev > 0.02:
                sc.notes.append("WARNING: deviation above 2% - sheet may be printed/scanned at a different size")
    elif nominal is not None:
        sc.mm_per_unit, sc.source, sc.denominator = nominal, "manual-denominator", cfg.denominator
        sc.notes.append("scale taken from the user-supplied ratio; it is only as accurate as the sheet "
                        "was printed/scanned at 100%")
    else:
        sc.notes.append("no scale information: geometry is exported in sheet millimetres and is NOT "
                        "dimensionally calibrated")
    return sc
