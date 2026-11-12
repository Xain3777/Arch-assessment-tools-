"""Configuration system.

All geometric tolerances are expressed in **millimetres on the drawing sheet**
("paper mm").  They are converted to pixels with the effective resolution of the
working raster, so the same configuration behaves consistently whether a sheet is
processed at 200 or 600 DPI.  Paper millimetres are tied to drawing scale: at
1:100 a 200 mm wall is 2 mm on paper, at 1:50 it is 4 mm.  Adjust the wall and
opening ranges when the drawing scale differs from the defaults (1:100).

Configuration is read from TOML (stdlib ``tomllib``) and can be overridden from
the command line with dotted keys, e.g. ``--set correct.snap_distance_mm=1.5``.
"""

from __future__ import annotations

import dataclasses
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class InputConfig:
    page: int = 0
    dpi: int = 300  # used when a page has to be rendered
    prefer_native_image: bool = True  # use the embedded scan at native resolution when possible
    max_pixels: int = 100_000_000  # larger sheets are rendered at a lower DPI (~3 GB RAM at this size)
    min_dpi_warning: int = 200  # warn when the effective resolution is below this


@dataclass
class PreprocessConfig:
    deskew: bool = True
    max_skew_deg: float = 5.0
    denoise: str = "median"  # "none" | "median" | "nlmeans"
    median_ksize: int = 3
    clahe: bool = False  # contrast enhancement for faded scans
    threshold: str = "otsu"  # "otsu" | "adaptive"
    adaptive_block_mm: float = 6.0
    adaptive_c: int = 12
    min_component_area_mm2: float = 0.05  # specks smaller than this are removed (0.22 mm square)
    isolated_speck_area_mm2: float = 0.25  # blobs up to this size are removed when isolated
    isolation_radius_mm: float = 1.5  # ... i.e. no other ink within this distance (keeps i-dots, decimal points)
    close_gaps_mm: float = 0.0  # morphological closing to repair broken strokes (0 = off)
    perspective: bool = False  # reserved: perspective correction is not implemented yet


@dataclass
class ExtractConfig:
    min_line_length_mm: float = 3.0
    wall_min_thickness_mm: float = 0.9  # strokes at least this thick are treated as solid walls
    text_max_size_mm: float = 4.5  # isolated blobs smaller than this are annotation
    rdp_epsilon_mm: float = 0.2  # Douglas-Peucker tolerance for traced centrelines
    detect_curves: bool = True
    arc_max_residual_mm: float = 0.25
    arc_min_sweep_deg: float = 25.0
    column_max_size_mm: float = 8.0  # compact solid blobs up to this size are columns


@dataclass
class CorrectConfig:
    angle_tolerance_deg: float = 2.0  # near-orthogonal lines are snapped to 0/90 degrees
    collinear_offset_mm: float = 0.35
    merge_gap_mm: float = 0.8  # gaps up to this are scan breaks and are bridged
    snap_distance_mm: float = 1.5  # endpoint-to-line snapping radius (corners, T-joints)
    opening_min_mm: float = 5.0  # wall gaps in [min, max] are openings (0.5–2.5 m at 1:100)
    opening_max_mm: float = 25.0
    thickness_cluster_tolerance: float = 0.18  # relative tolerance for wall-thickness families
    door_arc_radius_tolerance: float = 0.25  # |r - opening width| / width
    pair_double_line_walls: bool = True
    double_wall_min_mm: float = 0.8
    double_wall_max_mm: float = 4.0


@dataclass
class ScaleConfig:
    denominator: float | None = None  # e.g. 100 for 1:100; None = unknown
    known_distance_px: list[float] | None = None  # [x1, y1, x2, y2] in working-image pixels
    known_distance_mm: float | None = None  # real-world length of that measurement
    units: str = "mm"


@dataclass
class ExportConfig:
    formats: list[str] = field(default_factory=lambda: ["pdf", "svg", "dxf"])
    line_width_mm: float = 0.18
    wall_outline_width_mm: float = 0.25
    wall_fill: bool = True  # fill solid walls (poché) as in the source
    include_annotations: bool = True
    annotation_backend: str = "auto"  # "auto" | "potrace" | "contour"
    include_text: bool = True  # vector PDFs: re-emit real text objects
    preserve_vector_style: bool = True  # vector PDFs: keep source colour, width and dash pattern
    review_pdf: bool = True
    dwg: bool = False  # requires ODA File Converter (see docs)


@dataclass
class ValidationConfig:
    tolerance_mm: float = 0.4
    enabled: bool = True
    comparison_max_width_px: int = 3600


@dataclass
class Config:
    input: InputConfig = field(default_factory=InputConfig)
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    extract: ExtractConfig = field(default_factory=ExtractConfig)
    correct: CorrectConfig = field(default_factory=CorrectConfig)
    scale: ScaleConfig = field(default_factory=ScaleConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)

    # ------------------------------------------------------------------ io
    @classmethod
    def load(cls, path: str | Path | None = None, overrides: list[str] | None = None) -> "Config":
        cfg = cls()
        if path:
            with open(path, "rb") as fh:
                cfg.update(tomllib.load(fh))
        for item in overrides or []:
            cfg.set_dotted(item)
        return cfg

    def update(self, data: dict[str, Any]) -> None:
        for section, values in data.items():
            if not hasattr(self, section) or not isinstance(values, dict):
                raise ValueError(f"unknown configuration section [{section}]")
            target = getattr(self, section)
            names = {f.name for f in dataclasses.fields(target)}
            for key, value in values.items():
                if key not in names:
                    raise ValueError(f"unknown configuration key {section}.{key}")
                setattr(target, key, value)

    def set_dotted(self, item: str) -> None:
        if "=" not in item or "." not in item.split("=", 1)[0]:
            raise ValueError(f"override must look like section.key=value, got {item!r}")
        key, raw = item.split("=", 1)
        section, name = key.strip().split(".", 1)
        raw = raw.strip()
        current_value = getattr(getattr(self, section, None), name, None)
        if raw.lower() in ("none", "null", "") and not isinstance(current_value, str):
            value = None
        else:
            try:
                value = tomllib.loads(f"v = {raw}")["v"]
            except tomllib.TOMLDecodeError:
                value = raw  # bare string such as adaptive
        if isinstance(value, int) and not isinstance(value, bool):
            current = getattr(getattr(self, section, None), name, None)
            if isinstance(current, float):
                value = float(value)
        self.update({section: {name: value}})

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def mm_to_px(mm: float, dpi: float) -> float:
    return mm * dpi / 25.4


def px_to_mm(px: float, dpi: float) -> float:
    return px * 25.4 / dpi
