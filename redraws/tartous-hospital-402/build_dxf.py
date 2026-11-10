"""
Redraw of sheet 402 / drawing 165 - Tartous Hospital project
"Section A-A and detail sections" (scanned / photographed original, 1982).

Model space is drawn 1:1 in CENTIMETRES (all dimensions on the original are in cm).
Paper space layout "SHEET-165" reproduces the original A1 sheet with scaled viewports:
    Section A-A 1:100, Detail B 1:50, Plans 1.1/2.2/3.3 1:50, Section C-C 1:10, Groove detail 1:10.

Everything that had to be scaled from the photo (no written number) or inferred is
flagged on layer Z-INFERRED (magenta) and listed in NOTES.md.
"""
import math
import ezdxf
from ezdxf import units
from ezdxf.enums import TextEntityAlignment, MTextEntityAlignment

doc = ezdxf.new("R2018", setup=True)
doc.units = units.CM
doc.header["$INSUNITS"] = 5
doc.header["$MEASUREMENT"] = 1
doc.header["$LTSCALE"] = 1.0
doc.header["$PSLTSCALE"] = 1
msp = doc.modelspace()

if "ARIAL" not in doc.styles:
    doc.styles.add("ARIAL", font="arial.ttf")

# ----------------------------------------------------------------- layers
LAYERS = {
    "A-WALL-CUT": (7, 50, "Continuous"),
    "A-SLAB-CUT": (7, 50, "Continuous"),
    "A-POCHE": (8, 0, "Continuous"),
    "A-FLOR-FNSH": (7, 18, "Continuous"),
    "A-ELEV": (8, 13, "Continuous"),
    "A-ELEV-DOOR": (8, 18, "Continuous"),
    "A-GLAZ": (4, 18, "Continuous"),
    "A-STAIR": (7, 35, "Continuous"),
    "A-STAIR-BEYOND": (8, 18, "Continuous"),
    "A-HRAL": (8, 18, "Continuous"),
    "A-HATCH": (8, 9, "Continuous"),
    "A-GRND": (8, 18, "Continuous"),
    "A-GRID": (1, 18, "CENTER"),
    "A-GRID-BUBL": (1, 25, "Continuous"),
    "A-ANNO-DIMS": (3, 18, "Continuous"),
    "A-ANNO-LEVL": (3, 18, "Continuous"),
    "A-ANNO-TEXT": (7, 25, "Continuous"),
    "A-ANNO-TITL": (7, 35, "Continuous"),
    "A-SECT-MARK": (2, 25, "DASHDOT"),
    "A-DETL-CALL": (2, 18, "DASHED"),
    "A-HIDDEN": (8, 13, "DASHED"),
    "A-SHEET": (7, 50, "Continuous"),
    "A-TTLB": (7, 25, "Continuous"),
    "Z-INFERRED": (6, 25, "Continuous"),
    "VPORT": (8, 13, "Continuous"),
}
for name, (color, lw, lt) in LAYERS.items():
    lay = doc.layers.add(name, color=color, linetype=lt)
    lay.dxf.lineweight = lw
doc.layers.get("VPORT").dxf.plot = 0

# ----------------------------------------------------------------- dimstyles
for nm, sc in (("DIM-100", 10), ("DIM-50", 5), ("DIM-10", 1)):
    ds = doc.dimstyles.new(nm)
    ds.dxf.dimtxt = 2.0
    ds.dxf.dimscale = sc
    ds.dxf.dimasz = 1.5
    ds.dxf.dimblk = "ARCHTICK"
    ds.dxf.dimexo = 1.0
    ds.dxf.dimexe = 1.0
    ds.dxf.dimgap = 0.6
    ds.dxf.dimdec = 0
    ds.dxf.dimtad = 1
    ds.dxf.dimtih = 0
    ds.dxf.dimtoh = 0
    ds.dxf.dimclrd = 3
    ds.dxf.dimclre = 3
    ds.dxf.dimclrt = 7
    ds.dxf.dimtxsty = "ARIAL"
    ds.dxf.dimtmove = 2       # move text freely, no leader
    ds.dxf.dimatfit = 3


class Ctx:
    """Drawing context: offset + annotation scale (cm per paper-mm)."""

    def __init__(self, ox, oy, k, dimstyle):
        self.ox, self.oy, self.k, self.ds = ox, oy, k, dimstyle

    def p(self, x, y):
        return (self.ox + x, self.oy + y)

    def pts(self, seq):
        return [self.p(x, y) for x, y in seq]

    # -- geometry
    def line(self, a, b, layer, **kw):
        return msp.add_line(self.p(*a), self.p(*b), dxfattribs={"layer": layer, **kw})

    def pline(self, seq, layer, close=False, **kw):
        return msp.add_lwpolyline(self.pts(seq), close=close, dxfattribs={"layer": layer, **kw})

    def rect(self, x0, y0, x1, y1, layer, **kw):
        return self.pline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, close=True, **kw)

    def hatch(self, boundary, pattern="SOLID", scale=1.0, angle=0.0, layer="A-HATCH",
              holes=(), color=None):
        attrs = {"layer": layer}
        if color is not None:
            attrs["color"] = color
        h = msp.add_hatch(dxfattribs=attrs)
        if pattern == "SOLID":
            h.set_solid_fill(color=color if color is not None else 8)
        else:
            h.set_pattern_fill(pattern, scale=scale, angle=angle)
        h.paths.add_polyline_path(self.pts(boundary), is_closed=True)
        for hole in holes:
            h.paths.add_polyline_path(self.pts(hole), is_closed=True)
        return h

    def cut(self, boundary, layer="A-WALL-CUT", fill=True, holes=()):
        """Cut element: poche fill + heavy outline (+ holes outlined)."""
        if fill:
            self.hatch(boundary, "SOLID", layer="A-POCHE", holes=holes, color=8)
        self.pline(boundary, layer, close=True)
        for hole in holes:
            self.pline(hole, layer, close=True)

    def cutrect(self, x0, y0, x1, y1, layer="A-WALL-CUT", fill=True):
        self.cut([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, fill)

    # -- annotation
    def text(self, s, x, y, h_mm=2.5, layer="A-ANNO-TEXT", align=TextEntityAlignment.LEFT,
             rot=0.0, color=None):
        attrs = {"layer": layer, "style": "ARIAL", "height": h_mm * self.k, "rotation": rot}
        if color is not None:
            attrs["color"] = color
        t = msp.add_text(s, dxfattribs=attrs)
        t.set_placement(self.p(x, y), align=align)
        return t

    def mtext(self, s, x, y, h_mm=2.5, layer="A-ANNO-TEXT",
              attach=MTextEntityAlignment.TOP_LEFT, width=None, color=None):
        attrs = {"layer": layer, "style": "ARIAL", "char_height": h_mm * self.k}
        if width:
            attrs["width"] = width
        if color is not None:
            attrs["color"] = color
        m = msp.add_mtext(s, dxfattribs=attrs)
        m.set_location(self.p(x, y), attachment_point=attach)
        return m

    def dim_chain(self, pts_, at, vertical=True, layer="A-ANNO-DIMS", color=None):
        """Chain of linear dims. vertical: pts_ are y values, dim line at x=at."""
        attrs = {"layer": layer}
        if color is not None:
            attrs["color"] = color
        for a, b in zip(pts_[:-1], pts_[1:]):
            if vertical:
                p1, p2, base, ang = self.p(at, a), self.p(at, b), self.p(at, (a + b) / 2), 90
            else:
                p1, p2, base, ang = self.p(a, at), self.p(b, at), self.p((a + b) / 2, at), 0
            ov = {}
            if color is not None:
                ov = {"dimclrd": color, "dimclre": color, "dimclrt": color}
            d = msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=ang, dimstyle=self.ds,
                                   override=ov, dxfattribs=attrs)
            d.render()

    def level(self, x, y, label, side=1, layer="A-ANNO-LEVL"):
        """Level marker: triangle on the line y, label above; side=+1 text to the right."""
        k = self.k
        s = 1.6 * k
        self.pline([(x, y), (x - s, y + 1.8 * s), (x + s, y + 1.8 * s)], layer, close=True)
        self.line((x, y), (x, y + 4.5 * k), layer)
        self.line((x, y + 4.5 * k), (x + side * 11 * k, y + 4.5 * k), layer)
        al = TextEntityAlignment.BOTTOM_LEFT if side > 0 else TextEntityAlignment.BOTTOM_RIGHT
        self.text(label, x + side * 0.8 * k, y + 5.0 * k, 2.2, layer, al)

    def bubble(self, x, y, label, r_mm=4.5):
        r = r_mm * self.k
        msp.add_circle(self.p(x, y), r, dxfattribs={"layer": "A-GRID-BUBL"})
        self.text(label, x, y, 3.5, "A-GRID-BUBL", TextEntityAlignment.MIDDLE_CENTER)
        return r

    def breakline(self, a, b, layer="A-ELEV"):
        """Straight break line with a zig-zag in the middle."""
        (x0, y0), (x1, y1) = a, b
        L = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        nx, ny = -uy, ux
        z = 1.8 * self.k
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        pts_ = [(x0, y0), (mx - ux * z, my - uy * z), (mx - ux * z * 0.3 + nx * z * 1.5, my - uy * z * 0.3 + ny * z * 1.5),
                (mx + ux * z * 0.3 - nx * z * 1.5, my + uy * z * 0.3 - ny * z * 1.5), (mx + ux * z, my + uy * z), (x1, y1)]
        self.pline(pts_, layer)

    def title(self, en, ar, scale, x, y):
        self.text(en, x, y, 5.0, "A-ANNO-TITL", TextEntityAlignment.BOTTOM_CENTER)
        self.text(f"{ar}   {scale}", x, y - 8.5 * self.k, 3.5, "A-ANNO-TITL",
                  TextEntityAlignment.BOTTOM_CENTER)
        w = 0.5 * len(en) * 5.0 * self.k * 0.55
        self.line((x - w, y - 1.5 * self.k), (x + w, y - 1.5 * self.k), "A-ANNO-TITL")


def ribbed_slab(c, x0, x1, bot, top, solid_zones=(), block_w=20.0, pitch=33.0, cover_top=8.0,
                cover_bot=5.0, fill=True):
    """Hollow-block (hourdi) ribbed RC slab in section: poche with white block voids."""
    holes = []
    bh_top, bh_bot = top - cover_top, bot + cover_bot
    if bh_top - bh_bot > 4:
        x = x0 + 12
        while x + block_w < x1 - 12:
            mid = x + block_w / 2
            if not any(a - 5 <= mid <= b + 5 for a, b in solid_zones):
                holes.append([(x, bh_bot), (x + block_w, bh_bot), (x + block_w, bh_top), (x, bh_top)])
            x += pitch
    c.cut([(x0, bot), (x1, bot), (x1, top), (x0, top)], "A-SLAB-CUT", fill, holes)


def window_elev(c, x0, x1, y0, y1, transom=None, layer="A-ELEV"):
    c.rect(x0, y0, x1, y1, layer)
    c.rect(x0 + 4, y0 + 4, x1 - 4, y1 - 4, layer)
    if transom:
        c.line((x0 + 4, transom), (x1 - 4, transom), layer)


def door_elev(c, x0, x1, y0, h=210):
    c.rect(x0, y0, x1, y0 + h, "A-ELEV-DOOR")
    c.rect(x0 + 5, y0, x1 - 5, y0 + h - 5, "A-ELEV-DOOR")
    hx = x1 - 12
    c.line((hx, y0 + 100), (hx - 8, y0 + 100), "A-ELEV-DOOR")


def glazing_cut(c, x_out, x_in, y0, y1):
    """Window cut in section: frame at head/sill, two glass lines."""
    c.rect(x_out, y0, x_in, y0 + 5, "A-GLAZ")
    c.rect(x_out, y1 - 5, x_in, y1, "A-GLAZ")
    m = (x_out + x_in) / 2
    c.line((m - 1, y0 + 5), (m - 1, y1 - 5), "A-GLAZ")
    c.line((m + 1, y0 + 5), (m + 1, y1 - 5), "A-GLAZ")


def stair_flight(c, xa, ya, xb, yb, n, cut=True, waist=15.0):
    """Flight between (xa,ya) [lower end] and (xb,yb) [upper end]; n risers."""
    rise = (yb - ya) / n
    run = (xb - xa) / (n - 1)   # first riser at xa, last riser at xb
    prof = [(xa, ya)]
    x, y = xa, ya
    for i in range(n):
        y += rise
        prof.append((x, y))
        if i < n - 1:
            x += run
            prof.append((x, y))
    # underside parallel to the pitch line
    ang = math.atan2(yb - ya, xb - xa)
    off = waist / math.cos(ang)
    under = [(xb, yb - rise - off + rise), (xa, ya - off)]
    if cut:
        poly = prof + [(xb, yb - off), (xa + (0 if xb > xa else 0), ya - off)]
        c.cut(poly, "A-STAIR")
    else:
        # beyond: nosing line + underside + end risers, thin
        c.line((xa, ya + rise), (xb, yb), "A-STAIR-BEYOND")
        c.line((xa, ya - off), (xb, yb - off), "A-STAIR-BEYOND")
        c.line((xa, ya - off), (xa, ya + rise), "A-STAIR-BEYOND")
    # handrail 90 above pitch line (measured at nosings)
    c.line((xa, ya + rise + 90), (xb, yb + 90), "A-HRAL")
    c.line((xa, ya + rise + 82), (xb, yb + 82), "A-HRAL")
    c.line((xa, ya + rise), (xa, ya + rise + 90), "A-HRAL")
    c.line((xb, yb), (xb, yb + 90), "A-HRAL")


# =================================================================== SECTION A-A  (1:100)
aa = Ctx(0, 0, 10, "DIM-100")      # X = cm from grid 6, Y = level in cm

GRID = {"6": 0, "5": 465, "4": 855, "3": 1425, "2": 1790, "1": 2270}   # scaled (see notes)
F = [195, 545, 885, 1255, 1605, 1943]          # floor levels (F = finish, roof = structural B)
LAND = [370, 715, 1070, 1430, 1780]            # half landings

FAC_O, FAC_I = -8, 12          # upper facade wall faces
CORE_L0, CORE_L1 = 1955, 1985  # core left wall
CORE_R0, CORE_R1 = 2593, 2618  # core right wall
BAS_L0, BAS_L1 = 1670, 1695    # basement left wall
GF_GLZ = 150                   # ground floor glazing set-back
PAR_O, PAR_I = -111, -91       # roof parapet

# grid lines + bubbles
for g, x in GRID.items():
    r = aa.bubble(x, -76, g)
    aa.line((x, -76 + r), (x, 2140), "A-GRID")

# ---- roof
cols = [(GRID["4"] - 12.5, GRID["4"] + 12.5), (GRID["3"] - 12.5, GRID["3"] + 12.5)]
ribbed_slab(aa, PAR_O, CORE_L0, 1905, 1943, solid_zones=[(FAC_O, FAC_I + 20)] + cols)
aa.cutrect(PAR_O, 1943, PAR_I, 2055)
aa.line((PAR_I, 2055), (CORE_L0, 2055), "A-ELEV")         # parapet beyond
aa.line((PAR_I, 2045), (CORE_L0, 2045), "A-ELEV")
# ---- 2nd floor (+1605)
ribbed_slab(aa, FAC_O, CORE_L0, 1555, 1593, solid_zones=[(FAC_O, FAC_I + 20)] + cols)
aa.line((FAC_I, 1605), (CORE_L0, 1605), "A-FLOR-FNSH")
aa.cut([(FAC_O, 1545), (FAC_I, 1545), (FAC_I, 1555), (FAC_O, 1555)])          # edge beam downstand
aa.cut([(-120, 1510), (-110, 1510), (-110, 1545), (FAC_O, 1545), (FAC_O, 1555), (-120, 1555)])  # canopy
# ---- 1st floor (+1255)
ribbed_slab(aa, FAC_O, CORE_L0, 1205, 1243, solid_zones=[(FAC_O, FAC_I + 20)] + cols + [(GF_GLZ - 10, GF_GLZ + 25)])
aa.line((FAC_I, 1255), (CORE_L0, 1255), "A-FLOR-FNSH")
# ---- facade walls / windows (heights from the written facade chain)
for y0, y1 in ((1605, 1695), (1850, 1905), (1243, 1345), (1500, 1545)):
    aa.cutrect(FAC_O, y0, FAC_I, y1)
glazing_cut(aa, FAC_O + 2, FAC_I - 2, 1695, 1850)
glazing_cut(aa, FAC_O + 2, FAC_I - 2, 1345, 1500)
# ground floor facade (set back)
aa.cutrect(GF_GLZ, 885, GF_GLZ + 15, 975)
glazing_cut(aa, GF_GLZ + 2, GF_GLZ + 13, 975, 1205)
# ---- ground floor slab on grade (+885) and basement
aa.cutrect(-30, 865, BAS_L0, 885, "A-SLAB-CUT")
aa.cutrect(-30, 800, -15, 865, "A-WALL-CUT")                      # edge ground beam
aa.hatch([(-15, 840), (BAS_L0, 840), (BAS_L0, 865), (-15, 865)], "GRAVEL", 2.0)
aa.line((-15, 840), (BAS_L0, 840), "A-GRND")
aa.cutrect(BAS_L1, 865, CORE_L0, 885, "A-SLAB-CUT")
aa.cutrect(BAS_L1, 525, CORE_L0, 545, "A-SLAB-CUT")
aa.cutrect(BAS_L1, 175, CORE_R0, 195, "A-SLAB-CUT")
aa.hatch([(BAS_L1, 150), (CORE_R0, 150), (CORE_R0, 175), (BAS_L1, 175)], "GRAVEL", 2.0)
aa.line((BAS_L1, 150), (CORE_R0, 150), "A-GRND")
# walls
aa.cutrect(BAS_L0, 82, BAS_L1, 865)
aa.cutrect(CORE_L0, 82, CORE_L1, 2387)
aa.cutrect(CORE_R0, 82, CORE_R1, 2387)
for x0, x1 in ((BAS_L0, BAS_L1), (CORE_L0, CORE_L1), (CORE_R0, CORE_R1)):
    aa.breakline((x0 - 15, 82), (x1 + 15, 82), "A-WALL-CUT")
# core roof slab
aa.cutrect(CORE_L1, 2255, CORE_R0, 2275, "A-SLAB-CUT")
aa.line((CORE_L0, 2387), (CORE_R1, 2387), "A-WALL-CUT")
# columns (cut) at grids 4 & 3 on each storey
for x0, x1 in cols:
    for y0, y1 in ((885, 1205), (1255, 1555), (1605, 1905)):
        aa.cutrect(x0, y0, x1, y1)

# exterior ground
aa.line((-320, 870), (-30, 870), "A-GRND")
aa.hatch([(-320, 800), (-30, 800), (-30, 870), (-320, 870)], "EARTH", 6.0)
aa.line((CORE_R1, 870), (2900, 870), "A-GRND")
aa.hatch([(CORE_R1, 800), (2900, 800), (2900, 870), (CORE_R1, 870)], "EARTH", 6.0)
aa.hatch([(CORE_R1, 82), (CORE_R1 + 60, 82), (CORE_R1 + 60, 800), (CORE_R1, 800)], "EARTH", 6.0)
aa.hatch([(BAS_L0 - 60, 82), (BAS_L0, 82), (BAS_L0, 840), (BAS_L0 - 60, 840)], "EARTH", 6.0)

# ---- suspended ceilings + partitions (cut)
for fl in (1605, 1255):
    c_bot = fl + 240
    aa.cutrect(1680, c_bot, CORE_L0, c_bot + 10, "A-WALL-CUT", fill=False)
    aa.cutrect(391, c_bot, 590, c_bot + 10, "A-WALL-CUT", fill=False)
    aa.cutrect(1670, fl, 1680, fl + 300 - (12 if fl == 1255 else 0), "A-WALL-CUT", fill=False)
    aa.cutrect(391, fl, 401, c_bot, "A-WALL-CUT", fill=False)
    # elevation beyond
    door_elev(aa, 425, 505, fl)
    window_elev(aa, 690, 798, fl + 85, fl + 240, transom=fl + 190)
    window_elev(aa, 1504, 1612, fl + 85, fl + 240, transom=fl + 190)
    aa.line((656, fl), (656, c_bot), "A-ELEV")
# ground floor beyond
for x0 in (615, 1090):
    door_elev(aa, x0, x0 + 110, 885)
door_elev(aa, 1455, 1530, 885)
door_elev(aa, 1875, 1945, 885)
for x in (523, 897, 1487, 1554, 1712):
    aa.line((x, 885), (x, 1205), "A-ELEV")
# basement room doors
for fl in (195, 545):
    door_elev(aa, 1787, 1877, fl)

# ---- staircase (core)
ST_FLOOR_END = 2160    # end of floor landing / first riser
ST_LAND = 2418         # start of half landing
stair_risers = {}
for i in range(5):
    lo, mid, hi = F[i], LAND[i], F[i + 1]
    n1 = max(9, round((mid - lo) / 17.5))
    n2 = max(9, round((hi - mid) / 17.5))
    stair_risers[(lo, mid)] = n1
    stair_risers[(mid, hi)] = n2
    # beyond flight: floor (left) -> landing (right)
    stair_flight(aa, ST_FLOOR_END, lo, ST_LAND, mid, n1, cut=False)
    # cut flight: landing (right) -> floor (left): draw as rising leftwards
    stair_flight(aa, ST_LAND, mid, ST_FLOOR_END, hi, n2, cut=True)
    # half landing slab (cut)
    aa.cutrect(ST_LAND, mid - 20, CORE_R0, mid, "A-STAIR")
for fl in F[1:]:
    aa.cutrect(CORE_L1, fl - 20, ST_FLOOR_END, fl, "A-STAIR")
# core doors (elevation, far wall)
for fl in F[:5]:
    door_elev(aa, 2011, 2121, fl)

# ---- detail B callout
aa.rect(-150, 820, 260, 2120, "A-DETL-CALL")
aa.text("B", -150, 2135, 5.0, "A-ANNO-TITL")

# ---- dimensions
aa.dim_chain([885, 975, 1205, 1255, 1345, 1500, 1510, 1545, 1605, 1695, 1850, 1905, 2055], -230)
aa.dim_chain([885, 1205, 1255, 1555, 1593, 1605, 1905, 1943, 2055], 300)
aa.dim_chain([195, 525, 545, 865, 885, 1205, 1255, 1495, 1505, 1555, 1605, 1845, 1855, 1905, 1943, 2055], 1770)
# grid spacing: scaled from the drawing -> flagged
aa.dim_chain(list(GRID.values())[::-1][::-1], -190, vertical=False, layer="Z-INFERRED", color=6)

# ---- levels
for y, s in ((2055, "+2055"), (1943, "+1943 B"), (1605, "+1605 F"), (1255, "+1255 F"), (885, "+885 F")):
    aa.level(1300, y, s)
for y, s in ((2387, "+2387"), (2275, "+2275 B")):
    aa.level(2560, y, s)
for y in LAND:
    aa.level(2450, y, f"+{y} F")
aa.level(2450, 195, "+195 F")
for y in (545, 195):
    aa.level(1720, y, f"+{y} F", side=-1)

aa.title("SECTION A-A", "المقطع A-A", "1:100", 900, -300)

# =================================================================== DETAIL B  (1:50)
b = Ctx(4000, 0, 5, "DIM-50")       # X = cm from upper facade face, Y = level
# roof
ribbed_slab(b, -46, 240, 1905, 1943, solid_zones=[(-46, 30)])
b.cut([(-46, 1943), (-25, 1943), (-25, 2045), (-17, 2045), (-17, 2055), (-46, 2055)])
b.line((-17, 1955), (240, 1955), "A-FLOR-FNSH")
b.line((-17, 2055), (240, 2055), "A-ELEV")
b.line((-17, 2045), (240, 2045), "A-ELEV")
b.breakline((240, 1890), (240, 1960), "A-SLAB-CUT")
# 2nd floor
b.cutrect(-4, 1850, 17, 1905)
glazing_cut(b, -2, 12, 1695, 1850)
b.cutrect(-4, 1605, 17, 1695)
ribbed_slab(b, -4, 240, 1555, 1593, solid_zones=[(-4, 50)])
b.line((17, 1605), (240, 1605), "A-FLOR-FNSH")
b.cut([(-4, 1545), (17, 1545), (17, 1555), (-4, 1555)])
b.cut([(-62, 1510), (-50, 1510), (-50, 1545), (-4, 1545), (-4, 1555), (-62, 1555)])
b.cutrect(-4, 1500, 17, 1545)
b.breakline((240, 1540), (240, 1615), "A-SLAB-CUT")
for x in (62, 75):
    b.line((x, 1605), (x, 1850), "A-ELEV")
    b.line((x, 1255), (x, 1500), "A-ELEV")
# 1st floor
glazing_cut(b, -10, 6, 1345, 1500)
b.cutrect(-12, 1243, 8, 1345)
b.cutrect(-17, 1205, -12, 1345, fill=False)          # cladding
ribbed_slab(b, -12, 240, 1205, 1243, solid_zones=[(-12, 68)])
b.line((8, 1255), (240, 1255), "A-FLOR-FNSH")
b.breakline((240, 1190), (240, 1265), "A-SLAB-CUT")
# ground floor
b.cutrect(183, 885, 198, 975)
glazing_cut(b, 185, 196, 975, 1205)
b.cutrect(-21, 865, 240, 885, "A-SLAB-CUT")
b.line((-21, 877), (240, 877), "A-FLOR-FNSH")
b.hatch([(-21, 800), (240, 800), (240, 865), (-21, 865)], "GRAVEL", 1.0)
b.cutrect(-35, 815, -21, 885)
b.line((-120, 870), (-35, 870), "A-GRND")
b.hatch([(-120, 800), (-35, 800), (-35, 870), (-120, 870)], "EARTH", 3.0)
# section cut marks
for y, s, x0, x1 in ((2120, "3", -116, 108), (1794, "2", -75, 100), (1449, "1", -75, 95)):
    b.line((x0, y), (x1, y), "A-SECT-MARK")
    b.text(s, x0, y + 3, 3.5, "A-ANNO-TEXT")
    b.text(s, x1, y + 3, 3.5, "A-ANNO-TEXT", TextEntityAlignment.BOTTOM_RIGHT)
# grid 6
r = b.bubble(37, 723, "6")
b.line((37, 723 + r), (37, 880), "A-GRID")
# dims
b.dim_chain([870, 885, 975, 1205, 1255, 1345, 1500, 1510, 1545, 1605, 1695, 1850, 1905, 2055], -100)
b.dim_chain([885, 1205, 1255, 1555, 1593, 1605, 1905, 1943, 2055], 180)
b.dim_chain([-17, -12, 8, 63], 1404, vertical=False)
b.dim_chain([-12, 8, 68], 1184, vertical=False)
for y, s in ((2055, "+2055"), (1943, "+1943 B"), (1605, "+1605 F"), (1255, "+1255 F"), (885, "+885 F")):
    b.level(215, y, s)
b.title("DETAIL B", "التفصيلة B", "1:50", 60, 640)

# =================================================================== SECTION C-C  (1:10)
cc = Ctx(5200, 0, 1, "DIM-10")      # X = cm from outer concrete face of parapet, Y = level
cc.cut([(0, 1905), (0, 2055), (30, 2052), (30, 2040), (15, 2040), (15, 1943), (99, 1943), (99, 1905)],
       "A-WALL-CUT", fill=False)
cc.hatch([(0, 1905), (0, 2055), (30, 2052), (30, 2040), (15, 2040), (15, 1943), (99, 1943), (99, 1905)],
         "AR-CONC", 0.05)
cc.hatch([(0, 1905), (0, 2055), (30, 2052), (30, 2040), (15, 2040), (15, 1943), (99, 1943), (99, 1905)],
         "ANSI31", 0.6)
cc.breakline((99, 1898), (99, 1950), "A-SLAB-CUT")
cc.pline([(-2, 1905), (-2, 2057), (32, 2054), (32, 2038), (17, 2038), (17, 1985)], "A-FLOR-FNSH")  # render
cc.pline([(-22, 1905), (-22, 2055)], "A-HIDDEN")      # element beyond (dashed on original)
# drip groove under the coping
cc.rect(26, 2040, 28, 2038.5, "A-WALL-CUT")
# waterproofing upstand with cant
wp = [(17, 1985), (19, 1985), (19, 1966)]
for i in range(1, 10):
    a = math.radians(180 + 90 * i / 9)
    wp.append((29 + 10 * math.cos(a), 1966 + 10 * math.sin(a)))
wp += [(99, 1956)]
cc.pline(wp, "A-STAIR", const_width=0.35)
# roof build-up
for y in (1950, 1954, 1956, 1960):
    cc.line((17 if y < 1956 else 29, y), (99, y), "A-FLOR-FNSH")
cc.hatch([(17, 1943), (99, 1943), (99, 1950), (17, 1950)], "AR-SAND", 0.12)
cc.hatch([(17, 1950), (99, 1950), (99, 1954), (17, 1954)], "ANSI37", 0.35)
cc.hatch([(29, 1956), (99, 1956), (99, 1960), (29, 1960)], "AR-SAND", 0.06)
for x in range(38, 99, 15):
    cc.line((x, 1956), (x, 1960), "A-FLOR-FNSH")
# layer labels (original Arabic labels illegible -> typical build-up, flagged)
labels = ["Tiles on mortar bed (4)", "Waterproofing membrane, upturned 30 with cant",
          "Thermal insulation (4)", "Screed to falls (7)", "RC ribbed slab (38)"]
ys = [1958, 1955, 1952, 1946, 1925]
for i, (s, y) in enumerate(zip(labels, ys)):
    tx, ty = 115, 2015 - i * 7
    cc.pline([(70 + i * 5, y), (70 + i * 5, ty), (tx - 1, ty)], "Z-INFERRED")
    cc.text(s, tx, ty, 2.2, "Z-INFERRED", TextEntityAlignment.MIDDLE_LEFT)
cc.text("Layer names inferred - original Arabic labels illegible in scan", 115, 2025, 2.0,
        "Z-INFERRED", TextEntityAlignment.MIDDLE_LEFT)
cc.dim_chain([-22, -2, 0, 30, 32], 2070, vertical=False)
cc.dim_chain([-22, -2, 0, 15, 17], 2030, vertical=False)
cc.dim_chain([1943, 2055], -32)
cc.dim_chain([2040, 2055], 42)
cc.dim_chain([1905, 1943, 1950, 1954, 1956, 1960], 108)
cc.level(60, 1943, "+1943 B")
cc.level(-12, 2055, "+2055", side=-1)
cc.title("SECTION C-C", "المقطع C-C", "1:10", 45, 1880)

# =================================================================== GROOVE DETAIL (1:10)
gr = Ctx(6200, 1000, 1, "DIM-10")   # plan: X = cm from groove axis, Y = 0 at facade face
shape = [(-49, 0), (-10, 0), (-10, -20), (10, -20), (10, 0), (44, 0), (44, -15), (25, -15),
         (25, -35), (-25, -35), (-25, -15), (-49, -15)]
gr.pline(shape, "A-WALL-CUT", close=True)
gr.hatch(shape, "ANSI31", 0.6)
gr.breakline((-49, 3), (-49, -18), "A-WALL-CUT")
gr.breakline((44, 3), (44, -18), "A-WALL-CUT")
for seq in ([(-48, -35), (-40, -35), (-40, -50), (40, -50), (40, -35), (48, -35)],):
    gr.pline(seq, "A-ELEV")
gr.line((0, 18), (0, -68), "A-SECT-MARK")
for y, s in ((18, "C"), (-68, "C")):
    gr.line((0, y), (8, y), "A-SECT-MARK")
    gr.text(s, 10, y, 4.0, "A-ANNO-TEXT", TextEntityAlignment.MIDDLE_LEFT)
gr.dim_chain([-10, 10], 10, vertical=False)
gr.dim_chain([-40, 40], -60, vertical=False)
gr.dim_chain([-50, -35, -20, 0], -5)
gr.title("PLAN DETAIL - FACADE GROOVE", "مسقط تفصيلة الفرزة في الواجهات", "1:10", 0, -90)

# =================================================================== PLANS 3.3 / 2.2 / 1.1 (1:50)
p3 = Ctx(0, -1600, 5, "DIM-50")
r = p3.bubble(536, 0, "6")
p3.line((-70, 0), (536 - r, 0), "A-GRID")
r = p3.bubble(0, -242, "C")
p3.line((0, 40), (0, -242 + r), "A-GRID")
p3.line((-66, -120), (565, -120), "A-WALL-CUT")
p3.line((-66, -150), (565, -150), "A-WALL-CUT")
p3.breakline((-66, -110), (-66, -160), "A-WALL-CUT")
p3.breakline((565, -110), (565, -160), "A-WALL-CUT")
p3.dim_chain([-150, -120, 0], 300)
p3.dim_chain([-150, 0], 345)
p3.title("PLAN 3.3", "المسقط 3.3", "1:50", 250, -300)

p2 = Ctx(1200, -1600, 5, "DIM-50")
p2.cutrect(-7.5, 56, 7.5, 170)
p2.hatch([(-7.5, 56), (7.5, 56), (7.5, 170), (-7.5, 170)], "ANSI31", 2.0)
p2.cutrect(-12.5, 0, 12.5, 56)
p2.line((-25, 170), (25, 170), "A-WALL-CUT")
p2.pline([(-20, 0), (-20, -15), (-10, -15), (-10, -21)], "A-ELEV")
p2.pline([(20, 0), (20, -15), (10, -15), (10, -21)], "A-ELEV")
for y in (0, -6):
    p2.line((-87, y), (-20, y), "A-GLAZ")
    p2.line((20, y), (229, y), "A-GLAZ")
    p2.line((482, y), (590, y), "A-GLAZ")
p2.rect(229, 0, 482, -21, "A-WALL-CUT")
p2.hatch([(229, 0), (482, 0), (482, -21), (229, -21)], "ANSI31", 2.0)
for x0, x1 in ((-87, -10), (10, 229), (482, 590)):
    p2.line((x0, -19), (x1, -19), "A-ELEV")
    p2.line((x0, -74 if x1 != 590 else -74), (x1, -74), "A-ELEV")
for x in (-10, 10, 229, 482):
    p2.line((x, -19), (x, -74), "A-ELEV")
p2.line((-87, -128), (590, -128), "A-HIDDEN")
p2.breakline((-67, 10), (-67, -90), "A-ELEV")
p2.breakline((574, 10), (574, -90), "A-ELEV")
r = p2.bubble(0, -160, "C")
p2.line((0, -21), (0, -160 + r), "A-GRID")
p2.title("PLAN 2.2", "المسقط 2.2", "1:50", 250, -300)

p1 = Ctx(2400, -1600, 5, "DIM-50")
p1.cutrect(-7.5, 65, 7.5, 175)
p1.hatch([(-7.5, 65), (7.5, 65), (7.5, 175), (-7.5, 175)], "ANSI31", 2.0)
p1.line((-25, 175), (25, 175), "A-WALL-CUT")
p1.cutrect(-12.5, 10, 12.5, 65)
p1.pline([(-20, 10), (-20, 0), (-10, 0), (-10, -10), (10, -10), (10, 0), (20, 0), (20, 10)], "A-WALL-CUT")
p1.line((-10, -10), (-10, -70), "A-ELEV")
p1.line((10, -10), (10, -70), "A-ELEV")
for y in (10, 0):
    p1.line((-100, y), (-20, y), "A-GLAZ")
    p1.line((20, y), (240, y), "A-GLAZ")
p1.line((240, 0), (240, 20), "A-GLAZ")
p1.line((260, 0), (260, 20), "A-GLAZ")
p1.rect(260, 0, 480, 20, "A-WALL-CUT")
p1.hatch([(260, 0), (480, 0), (480, 20), (260, 20)], "ANSI31", 2.0)
p1.line((-100, -25), (-10, -25), "A-ELEV")
p1.line((10, -25), (480, -25), "A-ELEV")
p1.line((-100, -60), (480, -60), "A-HIDDEN")
p1.breakline((-100, 30), (-100, -70), "A-ELEV")
p1.breakline((495, 30), (495, -70), "A-ELEV")
r = p1.bubble(0, -112, "C")
p1.line((0, -70), (0, -112 + r), "A-GRID")
p1.dim_chain([-70, -10, 0, 10, 35, 65], 77)
p1.dim_chain([-20, -10, 10, 20], -45, vertical=False)
p1.dim_chain([20, 240, 260, 480], -85, vertical=False)
p1.dim_chain([-12.5, 12.5], 80, vertical=False)
p1.dim_chain([-7.5, 7.5], 150, vertical=False)
p1.dim_chain([-60, -15, 0, 20], 510)
p1.title("PLAN 1.1", "المسقط 1.1", "1:50", 200, -300)

# =================================================================== PAPER SPACE SHEET (A1)
psp = doc.layouts.new("SHEET-165")
psp.page_setup(size=(841, 594), margins=(0, 0, 0, 0), units="mm")
for vp in list(psp.viewports()):
    pass


def P(px, py):
    """original rectified-photo pixel -> paper mm (frame 800 x 583 mm)."""
    return (20.5 + px / 6.0, 588.5 - py / 6.0)


pa = dict(layer="A-SHEET")
psp.add_lwpolyline([(20.5, 5.5), (820.5, 5.5), (820.5, 588.5), (20.5, 588.5)], close=True, dxfattribs=pa)
psp.add_lwpolyline([(10, 3), (831, 3), (831, 591), (10, 591)], close=True,
                   dxfattribs={"layer": "A-SHEET", "lineweight": 13})


def viewport(px0, py0, px1, py1, model_center, scale_cm_per_mm):
    (x0, y1), (x1, y0) = P(px0, py0), P(px1, py1)
    w, h = x1 - x0, y1 - y0
    vp = psp.add_viewport(center=((x0 + x1) / 2, (y0 + y1) / 2), size=(w, h),
                          view_center_point=model_center, view_height=h * scale_cm_per_mm,
                          dxfattribs={"layer": "VPORT"})
    vp.dxf.flags |= 16384  # display locked
    return vp


# model centres = px-box centres mapped through each drawing's own px->model transform
def aa_m(px, py):
    return ((px - 645) / 0.6, 885 + (1602 - py) / 0.6)


def b_m(px, py):
    return (4000 + (px - 3270) / 1.2, 885 + (2145 - py) / 1.2)


def cc_m(px, py):
    return (5200 + (px - 4065) / 6.0, 1943 + (1440 - py) / 6.0)


def gr_m(px, py):
    return (6200 + (px - 2725) / 6.0, 1000 + (740 - py) / 6.0)


viewport(330, 640, 2700, 2330, aa_m((330 + 2700) / 2, (640 + 2330) / 2), 10)
viewport(3020, 600, 3900, 2520, b_m((3020 + 3900) / 2, (600 + 2520) / 2), 5)
viewport(3880, 560, 4720, 1990, cc_m((3880 + 4720) / 2, (560 + 1990) / 2), 1)
viewport(2380, 600, 3060, 1440, gr_m((2380 + 3060) / 2, (600 + 1440) / 2), 1)
viewport(420, 2520, 1360, 3180, (p3.ox + 250, p3.oy - 90), 5)
viewport(1560, 2520, 2600, 3180, (p2.ox + 250, p2.oy - 90), 5)
viewport(2740, 2520, 3700, 3180, (p1.ox + 200, p1.oy - 70), 5)

# ---- title block (paper space, mm)
tb = dict(layer="A-TTLB")
TX0, TX1 = P(4080, 0)[0], P(4797, 0)[0]


def tb_row(py0, py1, heavy=False):
    (x0, y1), (x1, y0) = P(4080, py0), P(4797, py1)
    psp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True,
                       dxfattribs={"layer": "A-TTLB", "lineweight": 50 if heavy else 25})
    return x0, y0, x1, y1


def tb_text(s, x, y, h, align=TextEntityAlignment.MIDDLE_CENTER):
    t = psp.add_text(s, dxfattribs={"layer": "A-TTLB", "style": "ARIAL", "height": h})
    t.set_placement((x, y), align=align)


x0, y0, x1, y1 = tb_row(2537, 2682, True)
cx = (x0 + x1) / 2 - 8
tb_text("الجمهورية العربية السورية", cx, y1 - 5, 3.0)
tb_text("الشركة العامة للدراسات والاستشارات الفنية", cx, y1 - 11, 3.0)
tb_text("SYRIAN ARAB REPUBLIC - GENERAL CO. FOR ENGINEERING STUDIES & CONSULTATIONS", cx, y1 - 17, 1.6)
tb_text("DAMASCUS", cx, y1 - 21, 1.8)
for i in range(4):  # logo outline
    psp.add_lwpolyline([(x1 - 22 + i * 2, y0 + 3 + i * 2), (x1 - 3 - i * 2, y0 + 3 + i * 2),
                        (x1 - 3 - i * 2, y1 - 3 - i * 2), (x1 - 22 + i * 2, y1 - 3 - i * 2)], dxfattribs=tb)
x0, y0, x1, y1 = tb_row(2699, 2816)
tb_text("CLIENT / اسم صاحب العمل", x1 - 2, y1 - 2.5, 1.6, TextEntityAlignment.TOP_RIGHT)
tb_text("محافظة طرطوس", (x0 + x1) / 2, (y0 + y1) / 2 + 1.5, 4.0)
tb_text("TARTOUS GOVERNORATE", (x0 + x1) / 2, y0 + 3, 2.2)
x0, y0, x1, y1 = tb_row(2816, 2937)
tb_text("PROJECT / اسم المشروع", x1 - 2, y1 - 2.5, 1.6, TextEntityAlignment.TOP_RIGHT)
tb_text("مشروع مشفى طرطوس", (x0 + x1) / 2, (y0 + y1) / 2 + 1.5, 4.0)
tb_text("TARTOUS HOSPITAL PROJECT", (x0 + x1) / 2, y0 + 3, 2.2)
x0, y0, x1, y1 = tb_row(2937, 2995)
for frac in (0.23, 0.42, 0.78):
    psp.add_line((x0 + (x1 - x0) * frac, y0), (x0 + (x1 - x0) * frac, y1), dxfattribs=tb)
tb_text("PROJECT No. 452", x0 + (x1 - x0) * 0.60, (y0 + y1) / 2, 2.4)
tb_text("PHASE: FINAL", x0 + (x1 - x0) * 0.115, (y0 + y1) / 2, 2.0)
tb_text("المرحلة النهائية", x0 + (x1 - x0) * 0.325, (y0 + y1) / 2, 2.0)
tb_text("رقم المشروع", x0 + (x1 - x0) * 0.89, (y0 + y1) / 2, 2.0)
x0, y0, x1, y1 = tb_row(3012, 3100, True)
tb_text("SECTION / WING (القسم)", x1 - 2, y1 - 2.5, 1.6, TextEntityAlignment.TOP_RIGHT)
tb_text("MEDICAL SECTION  -  القسم الطبي", (x0 + x1) / 2, (y0 + y1) / 2 - 1, 3.2)
x0, y0, x1, y1 = tb_row(3100, 3187, True)
tb_text("DRAWING TITLE / اسم المخطط", x1 - 2, y1 - 2.5, 1.6, TextEntityAlignment.TOP_RIGHT)
tb_text("المقطع A-A ومقاطع تفصيلية", (x0 + x1) / 2, (y0 + y1) / 2 + 1, 3.4)
tb_text("SECTION A-A AND DETAIL SECTIONS", (x0 + x1) / 2, y0 + 2.5, 2.2)
x0, y0, x1, y1 = tb_row(3203, 3262)
tb_text("DESIGNED / تصميم", x1 - 2, (y0 + y1) / 2, 1.8, TextEntityAlignment.MIDDLE_RIGHT)
tb_text("CHECKED / تدقيق", x0 + 40, (y0 + y1) / 2, 1.8, TextEntityAlignment.MIDDLE_RIGHT)
x0, y0, x1, y1 = tb_row(3262, 3320)
tb_text("DRAWN / رسم", x1 - 2, (y0 + y1) / 2, 1.8, TextEntityAlignment.MIDDLE_RIGHT)
tb_text("APPROVED / اعتماد", x0 + 40, (y0 + y1) / 2, 1.8, TextEntityAlignment.MIDDLE_RIGHT)
(x0, y1), (xm, y0) = P(4080, 3332), P(4430, 3495)
psp.add_lwpolyline([(x0, y0), (xm, y0), (xm, y1), (x0, y1)], close=True,
                   dxfattribs={"layer": "A-TTLB", "lineweight": 50})
psp.add_line(((x0 + xm) / 2, y0), ((x0 + xm) / 2, y1), dxfattribs=tb)
psp.add_line((x0, y1 - 8), (xm, y1 - 8), dxfattribs=tb)
tb_text("DATE / التاريخ", (x0 + (x0 + xm) / 2) / 2, y1 - 4, 1.8)
tb_text("SCALES / المقاييس", ((x0 + xm) / 2 + xm) / 2, y1 - 4, 1.8)
tb_text("1982 / 09 / 15", (x0 + (x0 + xm) / 2) / 2, (y0 + y1 - 8) / 2, 2.6)
tb_text("1/100 , 1/50 , 1/10", ((x0 + xm) / 2 + xm) / 2, (y0 + y1 - 8) / 2, 2.6)
(xm2, y1), (x1, y0) = P(4450, 3332), P(4797, 3495)
psp.add_lwpolyline([(xm2, y0), (x1, y0), (x1, y1), (xm2, y1)], close=True,
                   dxfattribs={"layer": "A-TTLB", "lineweight": 50})
psp.add_line((xm2, y1 - 8), (x1, y1 - 8), dxfattribs=tb)
tb_text("DRAWING No. / رقم المخطط", (xm2 + x1) / 2, y1 - 4, 1.8)
tb_text("165", (xm2 + x1) / 2, (y0 + y1 - 8) / 2, 6.0)

# redraw note
t = psp.add_mtext("REDRAWN FROM PHOTOGRAPHED ORIGINAL (2026-11-10). Dimensions in cm, levels in cm.\\P"
                  "Magenta (layer Z-INFERRED) = scaled from the drawing or inferred - verify on site.",
                  dxfattribs={"layer": "Z-INFERRED", "style": "ARIAL", "char_height": 2.2, "width": 200})
t.set_location(P(330, 3420), attachment_point=MTextEntityAlignment.TOP_LEFT)

doc.set_modelspace_vport(height=4000, center=(3000, 700))
out = __import__("sys").argv[1] if len(__import__("sys").argv) > 1 else "tartous_402_section_AA_details.dxf"
doc.saveas(out)
print("saved", out)
