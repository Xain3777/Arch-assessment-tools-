"""DXF export (ezdxf, R2010).

* Real-world millimetres when the scale is calibrated, otherwise sheet
  millimetres with ``$INSUNITS = 0`` (unitless) and a header note.
* Each entity carries ``ARCHVEC`` XDATA (kind, confidence, thickness, source)
  so AutoLISP tools can filter low-confidence geometry.
* Native DWG is *not* written by ezdxf; ``write_dwg`` converts through the
  ODA File Converter when it is installed (ezdxf.addons.odafc).
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.addons import odafc
from ezdxf.enums import TextEntityAlignment

from ..config import ExportConfig
from ..model import (
    LAYER_ANNOTATION,
    LAYER_OPENING,
    LAYER_REVIEW,
    LAYER_ROOM,
    LAYER_TEXT,
    LAYER_WALL,
    LAYER_WALL_CENTER,
    LAYERS,
    Drawing,
)
from ezdxf import colors as dxfcolors

from .common import Frame, collect_polygons, fill_style, parse_dashes, stroke_style

APPID = "ARCHVEC"
LINEWEIGHTS = {LAYER_WALL: 35, LAYER_WALL_CENTER: 13, LAYER_REVIEW: 13, LAYER_ROOM: 13}


def _xdata(entity, **kv) -> None:
    tags = []
    for k, v in kv.items():
        if isinstance(v, float):
            tags += [(1000, k), (1040, float(v))]
        else:
            tags += [(1000, f"{k}={v}")]
    entity.set_xdata(APPID, tags)


def write_dxf(drawing: Drawing, path: str | Path, cfg: ExportConfig) -> Path:
    path = Path(path)
    fr = Frame(drawing)
    doc = ezdxf.new("R2010", setup=True)
    doc.appids.add(APPID)
    calibrated = drawing.scale.calibrated
    doc.header["$INSUNITS"] = 4 if calibrated else 0
    doc.header["$MEASUREMENT"] = 1
    doc.header.custom_vars.append("ARCHVEC_UNITS", "real-world mm" if calibrated else "sheet mm (uncalibrated)")
    doc.header.custom_vars.append("ARCHVEC_SCALE_SOURCE", drawing.scale.source)
    if drawing.scale.denominator:
        doc.header.custom_vars.append("ARCHVEC_SCALE", f"1:{drawing.scale.denominator:.3f}")
    for name, (color, desc) in LAYERS.items():
        layer = doc.layers.add(name, color=color)
        layer.description = desc
        layer.dxf.lineweight = LINEWEIGHTS.get(name, 18)
        if name in (LAYER_ROOM, LAYER_OPENING):
            layer.off()
    msp = doc.modelspace()
    C = fr.cad  # noqa: N806
    keep = cfg.preserve_vector_style
    ltypes: dict[str, str] = {}
    lw_options = [0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100]

    def styled(item) -> dict:
        c, w, dsh = stroke_style(item, keep, 0.0)
        attrs: dict = {}
        if c is not None:
            attrs["true_color"] = dxfcolors.rgb2int(tuple(int(round(v * 255)) for v in c))
        if w:
            mm100 = fr.cad_len(w / fr.unit_to_pt) / fr.cad_factor * 100  # sheet hundredths of a mm
            attrs["lineweight"] = min(lw_options, key=lambda v: abs(v - mm100))
        pat = parse_dashes(dsh)
        if pat:
            if dsh not in ltypes:
                name = f"ARCHVEC_DASH{len(ltypes) + 1}"
                elems = [fr.cad_len(v / fr.unit_to_pt) for v in pat]
                if len(elems) % 2:
                    elems = elems * 2
                pattern = [sum(elems)] + [v if k % 2 == 0 else -v for k, v in enumerate(elems)]
                doc.linetypes.add(name, pattern=pattern, description=f"from PDF dash {dsh}")
                ltypes[dsh] = name
            attrs["linetype"] = ltypes[dsh]
        return attrs

    for poly in collect_polygons(drawing):
        if poly.layer == LAYER_ANNOTATION and not cfg.include_annotations:
            continue
        rings = [poly.exterior] + poly.holes
        for ring in rings:
            pl = msp.add_lwpolyline([C(*p) for p in ring], close=True, dxfattribs={"layer": poly.layer})
            _xdata(pl, kind="outline", confidence=float(poly.confidence), source=poly.source or "-")
        if poly.filled and (poly.layer != LAYER_WALL or cfg.wall_fill):
            hatch = msp.add_hatch(color=256, dxfattribs={"layer": poly.layer})
            fc = fill_style(poly, keep)
            if fc:
                hatch.set_solid_fill(rgb=tuple(int(round(v * 255)) for v in fc))
            else:
                hatch.set_solid_fill(color=256)
            for k, ring in enumerate(rings):
                hatch.paths.add_polyline_path([C(*p) for p in ring], is_closed=True, flags=1 if k == 0 else 16)
    for s in drawing.segments:
        if s.kind == "wall":
            e = msp.add_line(C(s.x1, s.y1), C(s.x2, s.y2), dxfattribs={"layer": LAYER_WALL_CENTER})
            _xdata(e, kind="wall-centreline", confidence=float(s.confidence), thickness=float(fr.cad_len(s.thickness)),
                   source=s.source or "-")
        else:
            e = msp.add_line(C(s.x1, s.y1), C(s.x2, s.y2), dxfattribs={"layer": s.layer, **styled(s)})
            _xdata(e, kind=s.kind, confidence=float(s.confidence), source=s.source or "-")
    for a in drawing.arcs:
        # working frame is y-down: mirror angles; a CCW DXF arc goes from -end to -start
        e = msp.add_arc(C(a.cx, a.cy), fr.cad_len(a.r), -a.end_deg, -a.start_deg, dxfattribs={"layer": a.layer, **styled(a)})
        _xdata(e, kind="arc", confidence=float(a.confidence), source=a.source or "-")
    for pl in drawing.polylines:
        e = msp.add_lwpolyline([C(*p) for p in pl.points], close=pl.closed, dxfattribs={"layer": pl.layer, **styled(pl)})
        _xdata(e, kind="polyline", confidence=float(pl.confidence), source=pl.source or "-")
    for o in drawing.openings:
        e = msp.add_line(C(*o.p1), C(*o.p2), dxfattribs={"layer": LAYER_OPENING})
        _xdata(e, kind=f"opening-{o.kind}", confidence=float(o.confidence), width=float(fr.cad_len(o.width)))
    for r in drawing.rooms:
        e = msp.add_lwpolyline([C(*p) for p in r.exterior], close=True, dxfattribs={"layer": LAYER_ROOM})
        _xdata(e, kind="room-candidate", confidence=float(r.confidence))
    if cfg.include_text:
        for t in drawing.texts:
            e = msp.add_text(t.text, height=fr.cad_len(t.size) * 0.75,
                             dxfattribs={"layer": LAYER_TEXT, "rotation": t.angle_deg})
            e.set_placement(C(t.x, t.y), align=TextEntityAlignment.LEFT)
    r = fr.cad_len(drawing.mm(2.0))
    for f in drawing.flags:
        c = msp.add_circle(C(f.x, f.y), r, dxfattribs={"layer": LAYER_REVIEW})
        _xdata(c, kind=f"flag-{f.code}", severity=f.severity, message=f.message[:200])
    doc.saveas(path)
    return path


def write_dwg(dxf_path: str | Path, dwg_path: str | Path, version: str = "R2018") -> Path:
    if not odafc.is_installed():
        raise RuntimeError("DWG export needs the ODA File Converter (https://www.opendesign.com/guestfiles/"
                           "oda_file_converter); install it or open the DXF in AutoCAD and SAVEAS DWG")
    doc = ezdxf.readfile(dxf_path)
    odafc.export_dwg(doc, str(dwg_path), version=version, replace=True)
    return Path(dwg_path)
