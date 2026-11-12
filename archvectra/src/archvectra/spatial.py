"""Bounding-box spatial index over segments (Shapely STRtree)."""

from __future__ import annotations

import numpy as np
from shapely import STRtree, box

from .model import Segment


class SegmentIndex:
    def __init__(self, segs: list[Segment]):
        self.segs = segs
        boxes = [box(min(s.x1, s.x2), min(s.y1, s.y2), max(s.x1, s.x2), max(s.y1, s.y2)) for s in segs]
        self.tree = STRtree(boxes) if boxes else None

    def query(self, x0: float, y0: float, x1: float, y1: float) -> list[int]:
        if self.tree is None:
            return []
        idx = self.tree.query(box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        return sorted(int(i) for i in np.asarray(idx).ravel())

    def near(self, x: float, y: float, r: float) -> list[int]:
        return self.query(x - r, y - r, x + r, y + r)
