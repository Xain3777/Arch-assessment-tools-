"""Internal drawing representation.

Everything is stored in the *working frame*: pixel coordinates of the working
raster (x to the right, y downwards).  For vector PDFs the working frame is PDF
points (72 per inch).  ``Drawing.px_to_pt`` maps the working frame to PDF page
points so that exports reproduce the original page geometry exactly.

Each primitive carries a layer, a confidence in [0, 1] and the name of the
method that produced it, so downstream tools (review UI, AutoCAD) can tell
measured geometry from inferred geometry.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

# Canonical CAD layers ------------------------------------------------------
LAYER_WALL = "A-WALL"
LAYER_WALL_CENTER = "A-WALL-CNTR"
LAYER_COLUMN = "A-COLS"
LAYER_SOLID = "A-SOLID"
LAYER_LINE = "A-DETL"
LAYER_ARC = "A-DETL-ARC"
LAYER_DOOR = "A-DOOR"
LAYER_GLAZING = "A-GLAZ"
LAYER_OPENING = "A-OPEN"
LAYER_ROOM = "A-AREA-BDRY"
LAYER_ANNOTATION = "A-ANNO"
LAYER_TEXT = "A-ANNO-TEXT"
LAYER_REVIEW = "Z-REVIEW"

LAYERS = {
    # name: (ACI colour, description)
    LAYER_WALL: (7, "Walls (solid / outline)"),
    LAYER_WALL_CENTER: (8, "Wall centrelines with measured thickness"),
    LAYER_COLUMN: (5, "Columns"),
    LAYER_SOLID: (9, "Other solid regions"),
    LAYER_LINE: (7, "Thin linework"),
    LAYER_ARC: (3, "Arcs and curves"),
    LAYER_DOOR: (3, "Door leaves and swings"),
    LAYER_GLAZING: (4, "Window glazing lines"),
    LAYER_OPENING: (6, "Detected opening chords (doors, windows) - reference"),
    LAYER_ROOM: (30, "Room boundary candidates (wall centrelines)"),
    LAYER_ANNOTATION: (2, "Annotation and untraced ink (outlines)"),
    LAYER_TEXT: (2, "Text objects from vector PDFs"),
    LAYER_REVIEW: (1, "Items flagged for manual review"),
}


@dataclass
class Segment:
    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float = 1.0
    kind: str = "line"  # "wall" | "line" | "wall-edge"
    layer: str = LAYER_LINE
    confidence: float = 1.0
    source: str = ""
    id: int = -1
    attrs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.x1, self.y1, self.x2, self.y2 = float(self.x1), float(self.y1), float(self.x2), float(self.y2)
        self.thickness = float(self.thickness)

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def angle(self) -> float:
        """Direction in degrees, normalised to [0, 180)."""
        return math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1)) % 180.0

    @property
    def orientation(self) -> str:
        if self.y1 == self.y2:
            return "h"
        if self.x1 == self.x2:
            return "v"
        return "d"

    def endpoints(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return (self.x1, self.y1), (self.x2, self.y2)

    def normalised(self) -> "Segment":
        """Return self with endpoints ordered (left->right, or top->bottom)."""
        if (self.x1, self.y1) > (self.x2, self.y2):
            self.x1, self.y1, self.x2, self.y2 = self.x2, self.y2, self.x1, self.y1
        return self


@dataclass
class Arc:
    cx: float
    cy: float
    r: float
    start_deg: float  # working frame (y down): angle = atan2(y - cy, x - cx)
    end_deg: float  # sweep runs from start to end with increasing angle
    thickness: float = 1.0
    layer: str = LAYER_ARC
    confidence: float = 1.0
    source: str = ""
    id: int = -1
    attrs: dict[str, Any] = field(default_factory=dict)

    @property
    def sweep(self) -> float:
        return (self.end_deg - self.start_deg) % 360.0 or 360.0

    def points(self, max_step_deg: float = 3.0) -> list[tuple[float, float]]:
        n = max(2, int(math.ceil(self.sweep / max_step_deg)) + 1)
        out = []
        for i in range(n):
            a = math.radians(self.start_deg + self.sweep * i / (n - 1))
            out.append((self.cx + self.r * math.cos(a), self.cy + self.r * math.sin(a)))
        return out


@dataclass
class Polygon:
    """Closed outline, optionally with holes (filled with even-odd rule)."""

    exterior: list[tuple[float, float]]
    holes: list[list[tuple[float, float]]] = field(default_factory=list)
    layer: str = LAYER_SOLID
    filled: bool = True
    confidence: float = 1.0
    source: str = ""
    id: int = -1
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Polyline:
    points: list[tuple[float, float]]
    closed: bool = False
    thickness: float = 1.0
    layer: str = LAYER_LINE
    confidence: float = 1.0
    source: str = ""
    id: int = -1
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Text:
    x: float  # baseline origin, working frame
    y: float
    text: str
    size: float  # font size in working-frame units
    angle_deg: float = 0.0
    layer: str = LAYER_TEXT
    source: str = "pdf-text"


@dataclass
class Opening:
    kind: str  # "door" | "window" | "opening"
    p1: tuple[float, float]  # jamb points on the wall centreline
    p2: tuple[float, float]
    width: float
    wall_thickness: float
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    id: int = -1


@dataclass
class ReviewFlag:
    x: float
    y: float
    code: str
    message: str
    severity: str = "warning"  # "info" | "warning" | "error"


@dataclass
class Scale:
    """Real-world scale.  ``mm_per_unit`` converts working-frame units to real mm."""

    paper_mm_per_unit: float  # always known (from DPI or PDF points)
    mm_per_unit: float | None = None  # real-world mm per unit, None when unknown
    source: str = "none"
    denominator: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def calibrated(self) -> bool:
        return self.mm_per_unit is not None


@dataclass
class Drawing:
    width: int
    height: int
    dpi: float  # working-frame units per inch
    px_to_pt: tuple[float, float, float, float, float, float]  # affine (a, b, c, d, e, f)
    page_size_pt: tuple[float, float]
    scale: Scale
    source_kind: str = "raster"
    segments: list[Segment] = field(default_factory=list)
    arcs: list[Arc] = field(default_factory=list)
    polygons: list[Polygon] = field(default_factory=list)
    polylines: list[Polyline] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)
    rooms: list[Polygon] = field(default_factory=list)
    flags: list[ReviewFlag] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def mm(self, value_mm: float) -> float:
        """Paper millimetres -> working-frame units."""
        return value_mm * self.dpi / 25.4

    def flag(self, x: float, y: float, code: str, message: str, severity: str = "warning") -> None:
        self.flags.append(ReviewFlag(float(x), float(y), code, message, severity))

    def log(self, stage: str, **info: Any) -> None:
        self.history.append({"stage": stage, **info})

    def renumber(self) -> None:
        for collection in (self.segments, self.arcs, self.polygons, self.polylines, self.openings, self.rooms):
            for i, item in enumerate(collection):
                item.id = i

    def walls(self) -> list[Segment]:
        return [s for s in self.segments if s.kind == "wall"]

    def to_dict(self) -> dict[str, Any]:
        self.renumber()
        d = asdict(self)
        d["scale"]["calibrated"] = self.scale.calibrated
        return d

    def summary(self) -> dict[str, Any]:
        kinds: dict[str, int] = {}
        for s in self.segments:
            kinds[s.kind] = kinds.get(s.kind, 0) + 1
        openings: dict[str, int] = {}
        for o in self.openings:
            openings[o.kind] = openings.get(o.kind, 0) + 1
        return {
            "segments": len(self.segments),
            "segments_by_kind": kinds,
            "arcs": len(self.arcs),
            "polygons": len(self.polygons),
            "polylines": len(self.polylines),
            "texts": len(self.texts),
            "openings": openings,
            "rooms": len(self.rooms),
            "review_flags": len(self.flags),
        }
