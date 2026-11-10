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
    "A-WALL-CUT": (7, 30, "Continuous"),
    "A-SLAB-CUT": (7, 30, "Continuous"),
    "A-POCHE": (8, 0, "Continuous"),
    "A-FLOR-FNSH": (7, 13, "Continuous"),
    "A-ELEV": (7, 9, "Continuous"),
    "A-ELEV-DOOR": (7, 9, "Continuous"),
    "A-GLAZ": (7, 9, "Continuous"),
    "A-STAIR": (7, 25, "Continuous"),
    "A-STAIR-BEYOND": (7, 13, "Continuous"),
    "A-STAIR-FNSH": (7, 9, "Continuous"),
    "A-HRAL": (7, 13, "Continuous"),
    "A-HATCH": (8, 5, "Continuous"),
    "A-GRND": (8, 13, "Continuous"),
    "A-GRID": (1, 9, "CENTER"),
    "A-GRID-BUBL": (1, 13, "Continuous"),
    "A-ANNO-DIMS": (3, 9, "Continuous"),
    "A-ANNO-LEVL": (3, 9, "Continuous"),
    "A-ANNO-TEXT": (7, 18, "Continuous"),
    "A-ANNO-TITL": (7, 35, "Continuous"),
    "A-SECT-MARK": (2, 18, "DASHDOT"),
    "A-DETL-CALL": (2, 13, "DASHED"),
    "A-HIDDEN": (8, 9, "DASHED"),
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
        h.dxf.lineweight = 0
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


def ribbed_slab(c, x0, x1, bot, top, solid_zones=(), block_w=34.0, pitch=54.0, cover_top=8.0,
                cover_bot=4.0, fill=True, plain_bands=(), start=None):
    """Hollow-block (hourdi) ribbed RC slab in section: poche with white block voids."""
    holes = []
    bh_top, bh_bot = top - cover_top, bot + cover_bot
    if bh_top - bh_bot > 4:
        x = x0 + 12 if start is None else start
        while x + block_w < x1 - 12:
            mid = x + block_w / 2
            if not any(a - 5 <= mid <= b + 5 for a, b in list(solid_zones) + list(plain_bands)):
                holes.append([(x, bh_bot), (x + block_w, bh_bot), (x + block_w, bh_top), (x, bh_top)])
            x += pitch
    for a, b in plain_bands:   # slab drawn as a plain outlined band on the original (no blocks)
        holes.append([(a, bot + 5), (b, bot + 5), (b, top - 5), (a, top - 5)])
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


def stair_flight(c, x_low, y_low, x_high, y_high, n, cut=True, waist=12.0, finish=3.0, hide=None,
                 show_soffit=False):
    """One straight flight in section, as drawn on the original.

    (x_low, y_low): foot of the first riser; (x_high, y_high): top of the last riser.
    n risers, n-1 treads. Cut flight: stepped finish line over a poche waist.
    Beyond flight: handrail + string (underside) only, thin.
    """
    d = 1 if x_high > x_low else -1
    rise = (y_high - y_low) / n
    run = abs(x_high - x_low) / (n - 1)
    prof = [(x_low, y_low)]
    x, y = x_low, y_low
    for i in range(n):
        y += rise
        prof.append((x, y))
        if i < n - 1:
            x += d * run
            prof.append((x, y))
    cosa = run / math.hypot(run, rise)
    # line through the inner (root) corners, then the soffit parallel to it
    def soffit(xx):
        return y_low + (xx - x_low) * (y_high - rise - y_low) / (x_high - x_low) - finish - waist / cosa
    def nosing(xx):
        return y_low + rise + (xx - x_low) * (y_high - y_low - rise) / (x_high - x_low)
    def seg(xa, ya, xb, yb, layer):
        """Line, clipped where it passes behind the cut flight in front (hide = its soffit)."""
        if hide is not None:
            fa, fb = ya - hide(xa), yb - hide(xb)
            if fa >= 0 and fb >= 0:
                return
            if fa > 0 or fb > 0:
                t = fa / (fa - fb)
                xm, ym = xa + t * (xb - xa), ya + t * (yb - ya)
                if fa > 0:
                    xa, ya = xm, ym
                else:
                    xb, yb = xm, ym
        c.line((xa, ya), (xb, yb), layer)

    x_top_post = x_high + d * 20      # post on the floor / landing beyond the top riser
    x_bot_post = x_low - d * 20       # post on the landing / floor before the first riser
    if cut:
        struct = [(px, py - finish) for px, py in prof]
        poly = struct + [(x_high, soffit(x_high)), (x_low, soffit(x_low))]
        c.cut(poly, "A-STAIR")
        c.pline(prof, "A-STAIR-FNSH")
        for h in (90, 100):
            c.line((x_low - d * 17, nosing(x_low - d * 17) + h), (x_top_post, y_high + h), "A-HRAL")
        c.line((x_low - d * 17, nosing(x_low - d * 17) + 90), (x_low - d * 17, nosing(x_low - d * 17) + 100), "A-HRAL")
        c.line((x_low - d * 17, nosing(x_low - d * 17) + 50), (x_high, y_high + 50), "A-HRAL")
        c.line((x_high, y_high + 50), (x_top_post, y_high + 50), "A-HRAL")
        c.line((x_top_post, y_high), (x_top_post, y_high + 100), "A-HRAL")
        c.line((x_low - d * 17, y_low), (x_low - d * 17, nosing(x_low - d * 17) + 90), "A-HRAL")
    else:
        # beyond flight: handrail pair + mid rail, post at the floor end, soffit line
        for h in (50, 90, 100):
            seg(x_bot_post, nosing(x_bot_post) + h, x_high, y_high + h, "A-STAIR-BEYOND")
        c.line((x_bot_post, y_low), (x_bot_post, nosing(x_bot_post) + 100), "A-STAIR-BEYOND")
        c.line((x_bot_post, nosing(x_bot_post) + 50), (x_bot_post + d * 0, nosing(x_bot_post) + 50), "A-STAIR-BEYOND")
        # soffit: visible from where it rises out of the floor
        if show_soffit:
            k = (soffit(x_high) - soffit(x_low)) / (x_high - x_low)
            x0 = x_low + (y_low - soffit(x_low)) / k
            seg(x0, y_low, x_high, soffit(x_high), "A-STAIR-BEYOND")
    return soffit


# =================================================================== SECTION A-A  (1:100)
aa = Ctx(0, 0, 10, "DIM-100")      # X = cm from grid 6, Y = level in cm

GRID = {"6": 0, "5": 465, "4": 855, "3": 1425, "2": 1790, "1": 2270}   # scaled (see notes)
F = [195, 545, 885, 1255, 1605, 1943]          # floor levels (F = finish, roof = structural B)
LAND = [370, 715, 1070, 1430, 1780]            # half landings

FAC_O, FAC_I = -25, -4         # upper facade wall faces (21 cm)
CORE_L0, CORE_L1 = 1955, 1985  # core left wall
CORE_R0, CORE_R1 = 2593, 2618  # core right wall
BAS_L0, BAS_L1 = 1670, 1695    # basement left wall
GF_GLZ = 150                   # ground floor glazing set-back
PAR_O, PAR_I = -116, -102      # roof parapet (14 cm, coping 30)

# grid lines + bubbles
for g, x in GRID.items():
    r = aa.bubble(x, -76, g)
    aa.line((x, -76 + r), (x, 2140), "A-GRID")

# ---- roof
cols = [(841, 856), (1435, 1450)]          # 15 cm columns, positions scaled from the original
BEAMS = [(840, 922), (1365, 1455), (1755, 1840)]   # solid (no-block) beam zones in floor slabs
PLAIN = [(1455, 1755)]                      # plain band in floor slabs (corridor)
ribbed_slab(aa, PAR_O, CORE_L0, 1905, 1943, solid_zones=[(FAC_O, FAC_I + 20)] + cols)
aa.cut([(PAR_O, 1943), (PAR_I, 1943), (PAR_I, 2043), (PAR_O + 30, 2043), (PAR_O + 30, 2055), (PAR_O, 2055)])
aa.line((PAR_O + 30, 2055), (CORE_L0, 2055), "A-ELEV")    # parapet beyond
aa.line((PAR_O + 30, 2043), (CORE_L0, 2043), "A-ELEV")
# ---- 2nd floor (+1605)
ribbed_slab(aa, FAC_O, CORE_L0, 1555, 1593, solid_zones=[(FAC_O, FAC_I + 20)] + BEAMS, plain_bands=PLAIN)
aa.line((FAC_I, 1605), (CORE_L0, 1605), "A-FLOR-FNSH")
aa.cut([(FAC_O, 1545), (FAC_I, 1545), (FAC_I, 1555), (FAC_O, 1555)])          # edge beam downstand
aa.cut([(FAC_O - 58, 1510), (FAC_O - 46, 1510), (FAC_O - 46, 1543), (FAC_O, 1543), (FAC_O, 1555),
        (FAC_O - 58, 1555)])  # canopy 58 cm (as Detail B)
# ---- 1st floor (+1255)
ribbed_slab(aa, FAC_O, CORE_L0, 1205, 1243, solid_zones=[(FAC_O, FAC_I + 20)] + BEAMS + [(GF_GLZ - 10, GF_GLZ + 25)],
            plain_bands=PLAIN)
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
aa.cutrect(-30, 865, BAS_L0, 885, "A-SLAB-CUT", fill=False)
aa.line((-30, 877), (BAS_L0, 877), "A-FLOR-FNSH")
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
aa.cutrect(CORE_L1, 2260, CORE_R0, 2275, "A-SLAB-CUT")
aa.line((CORE_L0, 2387), (CORE_R1, 2387), "A-WALL-CUT")
# columns (cut) - 15 cm, dark on the original
for x0, x1 in cols:
    for y0, y1 in ((1255, 1555), (1605, 1905)):
        aa.cutrect(x0, y0, x1, y1)
aa.cutrect(841, 885, 856, 1205, fill=False)       # ground floor at grid 4: thin double line
aa.cutrect(1385, 885, 1400, 1205)                 # ground floor column (dark) left of grid 3
# waterproofing (dotted on original) on outer faces of basement walls
aa.line((BAS_L0 - 3, 82), (BAS_L0 - 3, 865), "A-HIDDEN")
aa.line((CORE_R1 + 3, 82), (CORE_R1 + 3, 870), "A-HIDDEN")

# exterior ground
aa.line((-320, 870), (-30, 870), "A-GRND")
aa.hatch([(-320, 800), (-30, 800), (-30, 870), (-320, 870)], "EARTH", 6.0)
aa.line((CORE_R1, 870), (2900, 870), "A-GRND")
aa.hatch([(CORE_R1, 800), (2900, 800), (2900, 870), (CORE_R1, 870)], "EARTH", 6.0)


# ---- suspended ceilings + partitions (cut)
for fl in (1605, 1255):
    c_bot = fl + 240
    aa.cutrect(1680, c_bot, CORE_L0, c_bot + 10, "A-WALL-CUT", fill=False)
    aa.cutrect(412, c_bot, 607, c_bot + 10, "A-WALL-CUT", fill=False)
    aa.cutrect(597, c_bot - 15, 607, c_bot, "A-WALL-CUT")          # bulkhead drop
    aa.cutrect(1670, fl, 1680, fl + 300 - (12 if fl == 1255 else 0), "A-WALL-CUT", fill=False)
    aa.cutrect(412, fl, 422, c_bot, "A-WALL-CUT", fill=False)
    # elevation beyond
    door_elev(aa, 425, 490, fl)
    window_elev(aa, 690, 806, fl + 82, fl + 238, transom=fl + 125)
    window_elev(aa, 1504, 1612, fl + 82, fl + 238, transom=fl + 125)
    for x in (42, 506, 606, 640, 656):
        aa.line((x, fl), (x, c_bot if x != 42 else fl + 300 - (12 if fl == 1255 else 0)), "A-ELEV")
aa.line((1686, 1255 + 60), (CORE_L0, 1255 + 60), "A-ELEV")     # counter line, 1st floor
# ground floor beyond
for x0 in (615, 1090):
    door_elev(aa, x0, x0 + 110, 885)
door_elev(aa, 1430, 1500, 885)
door_elev(aa, 1865, 1940, 885)
aa.cutrect(1690, 885, 1705, 1205)                 # ground floor partition (dark on original)
for x in (-8, 42, 420, 523, 898, 1530, 1755, 1835):
    aa.line((x, 885), (x, 1205), "A-ELEV")
# basement room doors
for fl in (195, 545):
    door_elev(aa, 1787, 1877, fl)

# ---- staircase (core) - dog-leg, 10 risers per flight, 9 treads x 30 = 270 run (read on original)
ST_FLOOR_END = 2163    # nosing of top riser at floor side
ST_LAND = ST_FLOOR_END + 270   # first riser at landing side
PLATE = 15             # floor plate / landing thickness (scaled ~15)
for i in range(5):
    lo, mid, hi = F[i], LAND[i], F[i + 1]
    # cut flight (in front): landing (right, low) up to floor (left)
    front = stair_flight(aa, ST_LAND, mid, ST_FLOOR_END, hi, 10, cut=True)
    # beyond flight: floor (left, low) up to landing (right), hidden behind the cut flight
    stair_flight(aa, ST_FLOOR_END, lo, ST_LAND, mid, 10, cut=False, hide=front, show_soffit=(i == 0))
    aa.cutrect(ST_LAND, mid - PLATE, CORE_R0, mid, "A-STAIR")
    aa.line((ST_LAND, mid - 3), (CORE_R0, mid - 3), "A-STAIR-FNSH")
for fl in F[1:]:
    aa.cutrect(CORE_L1, fl - PLATE, ST_FLOOR_END, fl, "A-STAIR")
    aa.line((CORE_L1, fl - 3), (ST_FLOOR_END, fl - 3), "A-STAIR-FNSH")
# core doors (elevation, far wall)
for fl in F[:5]:
    door_elev(aa, 2010, 2100, fl)

# ---- detail B callout
aa.rect(-150, 820, 260, 2120, "A-DETL-CALL")
aa.text("B", -150, 2135, 5.0, "A-ANNO-TITL")

# ---- dimensions
aa.dim_chain([885, 975, 1205, 1255, 1345, 1500, 1510, 1545, 1605, 1695, 1850, 1905, 2055], -230)
aa.dim_chain([885, 1205, 1255, 1555, 1593, 1605, 1905, 1937, 1943, 2055], 300)
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
b = Ctx(4000, 0, 5, "DIM-50")       # X = cm from outer face of upper facade wall, Y = level
RB = 245                            # right break line
# roof: parapet 14 + coping 30, overhang 105 (scaled), ribbed slab 32 + 6
ribbed_slab(b, -105, RB, 1905, 1943, solid_zones=[(-105, -64)], block_w=38, pitch=57, start=-62)
b.cut([(-105, 1943), (-91, 1943), (-91, 2043), (-75, 2043), (-75, 2055), (-105, 2055)])
b.line((-75, 2055), (RB, 2055), "A-ELEV")
b.line((-75, 2043), (RB, 2043), "A-ELEV")
b.breakline((RB, 1890), (RB, 1960), "A-SLAB-CUT")
# 2nd floor
b.cutrect(0, 1850, 21, 1905)
glazing_cut(b, 6, 19, 1695, 1850)
b.cutrect(0, 1605, 21, 1695)
ribbed_slab(b, 0, RB, 1555, 1593, solid_zones=[(0, 54)], block_w=38, pitch=57, start=56)
b.line((21, 1605), (RB, 1605), "A-FLOR-FNSH")
b.cut([(0, 1545), (21, 1545), (21, 1555), (0, 1555)])
b.cut([(-62, 1510), (-50, 1510), (-50, 1543), (0, 1543), (0, 1555), (-62, 1555)])
b.cutrect(0, 1500, 21, 1545)
b.breakline((RB, 1540), (RB, 1615), "A-SLAB-CUT")
b.line((79, 1605), (79, 1850), "A-ELEV")
b.line((79, 1255), (79, 1500), "A-ELEV")
# 1st floor: cladding 5 + concrete 20 (written), beam 20 + 60 (written)
glazing_cut(b, 6, 19, 1345, 1500)
b.cutrect(0, 1243, 20, 1345)
b.cutrect(-5, 1205, 0, 1345, fill=False)
ribbed_slab(b, 0, RB, 1205, 1243, solid_zones=[(0, 80)], block_w=38, pitch=57, start=82)
b.line((20, 1255), (RB, 1255), "A-FLOR-FNSH")
b.breakline((RB, 1190), (RB, 1265), "A-SLAB-CUT")
# ground floor
b.cutrect(188, 885, 202, 975)
glazing_cut(b, 189, 201, 975, 1205)
for x in (18, 78):
    b.line((x, 885), (x, 1205), "A-ELEV")
b.cutrect(-19, 865, RB, 885, "A-SLAB-CUT", fill=False)
b.line((-19, 877), (RB, 877), "A-FLOR-FNSH")
b.hatch([(-19, 800), (RB, 800), (RB, 865), (-19, 865)], "GRAVEL", 1.0)
b.cutrect(-33, 803, -19, 885)
b.line((-125, 870), (-33, 870), "A-GRND")
b.hatch([(-125, 800), (-33, 800), (-33, 870), (-125, 870)], "EARTH", 3.0)
# section cut marks
for y, s_, x0, x1 in ((2120, "3", -174, 104), (1794, "2", -70, 104), (1449, "1", -70, 101)):
    b.line((x0, y), (x1, y), "A-SECT-MARK")
    b.text(s_, x0, y + 3, 3.5, "A-ANNO-TEXT")
    b.text(s_, x1, y + 3, 3.5, "A-ANNO-TEXT", TextEntityAlignment.BOTTOM_RIGHT)
# grid 6
r = b.bubble(46, 715, "6")
b.line((46, 715 + r), (46, 1205), "A-GRID")
# dims
b.dim_chain([870, 885, 975, 1205, 1255, 1345, 1500, 1510, 1545, 1605, 1695, 1850, 1905, 2055], -125)
b.dim_chain([885, 1205, 1255, 1555, 1593, 1605, 1905, 1937, 1943, 2055], 174)
b.dim_chain([-5, 0, 20, 75], 1404, vertical=False)
b.dim_chain([0, 20, 80], 1184, vertical=False)
for y, s_ in ((2055, "+2055"), (1943, "+1943 B"), (1605, "+1605 F"), (1255, "+1255 F"), (885, "+885 F")):
    b.level(215, y, s_)
b.title("DETAIL B", "التفصيلة B", "1:50", 60, 640)

# =================================================================== SECTION C-C  (1:10)
cc = Ctx(5200, 0, 1, "DIM-10")      # X = cm from outer concrete face of parapet, Y = level
# written: coping 30 (+2 render), cap 13 concrete + 2/2 above + 2 below, wall 13 (+2 render each side),
# waterproofing upturn 34, roof build-up 8 / 2 / 2 / 4, slab 38, parapet 112 above +1943
UP = 1955 + 34                      # top of waterproofing upturn (wall recessed to 10 below it)
conc = [(0, 1905), (0, 2051), (30, 2049), (30, 2038), (13, 2038), (13, UP), (10, UP), (10, 1943),
        (99, 1943), (99, 1905)]
cc.pline(conc, "A-WALL-CUT", close=True)
cc.hatch(conc, "AR-CONC", 0.05)
cc.hatch(conc, "ANSI31", 0.6)
cc.breakline((99, 1898), (99, 1950), "A-SLAB-CUT")
cc.pline([(-2, 1905), (-2, 2053), (32, 2051), (32, 2036), (15, 2036), (15, UP + 3), (13, UP + 3)],
         "A-FLOR-FNSH")                                   # render 2 cm
cc.line((0, 2055), (32, 2053), "A-FLOR-FNSH")            # top finish (2 + 2 over the cap)
cc.pline([(-22, 1905), (-22, 2055)], "A-HIDDEN")         # projecting element beyond (dashed)
cc.rect(26, 2036, 28, 2034.5, "A-WALL-CUT")              # drip
# waterproofing membrane (2) turned up into the recess with a cant (radius 10)
wp = [(13, UP + 3), (13, UP), (11.5, UP), (11.5, 1964)]
for i in range(1, 10):
    ang = math.radians(180 + 90 * i / 9)
    wp.append((21.5 + 10 * math.cos(ang), 1964 + 10 * math.sin(ang)))
wp += [(99, 1954)]
cc.pline(wp, "A-STAIR", const_width=0.25)
# build-up layers
cc.line((10, 1951), (99, 1951), "A-FLOR-FNSH")
cc.line((10, 1953), (99, 1953), "A-FLOR-FNSH")
cc.line((22, 1955), (99, 1955), "A-FLOR-FNSH")
cc.line((22, 1959), (99, 1959), "A-FLOR-FNSH")
cc.line((22, 1955), (22, 1959), "A-FLOR-FNSH")
cc.hatch([(10, 1943), (99, 1943), (99, 1951), (10, 1951)], "AR-SAND", 0.12)
cc.hatch([(22, 1955), (99, 1955), (99, 1959), (22, 1959)], "AR-SAND", 0.06)
for x in range(37, 99, 15):
    cc.line((x, 1955), (x, 1959), "A-FLOR-FNSH")
# layer labels: 7 Arabic labels on the original are illegible in the photo -> typical names, flagged
labels = ["Floor tiles on mortar (4)", "Waterproofing membrane (2), upturned 34 with cant",
          "Levelling screed (2)", "Lightweight concrete to falls (8)", "RC ribbed slab 32 + 6",
          "Ceiling plaster"]
ys = [1957, 1954, 1952, 1947, 1925, 1906]
for i, (s_, y) in enumerate(zip(labels, ys)):
    tx, ty = 115, 2015 - i * 7
    cc.pline([(45 + i * 6, y), (45 + i * 6, ty), (tx - 1, ty)], "Z-INFERRED")
    cc.text(s_, tx, ty, 2.2, "Z-INFERRED", TextEntityAlignment.MIDDLE_LEFT)
cc.text("Layer names inferred - original Arabic labels illegible in photo", 115, 2025, 2.0,
        "Z-INFERRED", TextEntityAlignment.MIDDLE_LEFT)
cc.dim_chain([-22, -2, 0, 30, 32], 2072, vertical=False)
cc.dim_chain([-22, -2, 0, 13, 15], 2030, vertical=False)
cc.dim_chain([1943, 2055], -32)
cc.dim_chain([2036, 2038, 2051, 2053, 2055], 42)
cc.dim_chain([1955, UP], 30)
cc.dim_chain([1905, 1943, 1951, 1953, 1955, 1959], 108)
cc.level(60, 1943, "+1943 B")
cc.level(-12, 2055, "+2055", side=-1)
cc.title("SECTION C-C", "المقطع C-C", "1:10", 45, 1880)

# =================================================================== GROOVE DETAIL (1:10)
gr = Ctx(6200, 1000, 1, "DIM-10")   # plan: X = cm from groove axis, Y = 0 at facade face
shape = [(-49, 0), (-10, 0), (-10, -20), (10, -20), (10, 0), (44, 0), (44, -15), (25, -15),
         (25, -35), (-25, -35), (-25, -15), (-49, -15)]
gr.pline(shape, "A-WALL-CUT", close=True)
gr.hatch(shape, "ANSI31", 0.6)
gr.breakline((-49, 3), (-49, -35), "A-WALL-CUT")
gr.breakline((44, 3), (44, -35), "A-WALL-CUT")
for seq in ([(-49, -35), (-40, -35), (-40, -50), (40, -50), (40, -35), (44, -35)],):
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
p2.rect(-7.5, 56, 7.5, 170, "A-WALL-CUT")
p2.hatch([(-7.5, 56), (7.5, 56), (7.5, 170), (-7.5, 170)], "ANSI31", 2.0)
p2.rect(-12.5, 0, 12.5, 56, "A-WALL-CUT")
p2.hatch([(-12.5, 0), (12.5, 0), (12.5, 56), (-12.5, 56)], "ANSI37", 0.5)
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
    p2.line((x0, -31), (x1, -31), "A-ELEV")
    p2.line((x0, -76), (x1, -76), "A-ELEV")
for x in (-10, 10, 229, 482):
    p2.line((x, -21), (x, -76), "A-ELEV")
p2.line((-87, -126), (590, -126), "A-HIDDEN")
p2.breakline((-73, 25), (-73, -140), "A-ELEV")
p2.breakline((570, 25), (570, -140), "A-ELEV")
r = p2.bubble(0, -160, "C")
p2.line((0, -21), (0, -160 + r), "A-GRID")
p2.title("PLAN 2.2", "المسقط 2.2", "1:50", 250, -300)

p1 = Ctx(2400, -1600, 5, "DIM-50")
p1.rect(-7.5, 65, 7.5, 180, "A-WALL-CUT")
p1.hatch([(-7.5, 65), (7.5, 65), (7.5, 180), (-7.5, 180)], "ANSI31", 2.0)
p1.line((-40, 178), (38, 178), "A-WALL-CUT")
p1.rect(-12.5, 10, 12.5, 65, "A-WALL-CUT")
p1.hatch([(-12.5, 10), (12.5, 10), (12.5, 65), (-12.5, 65)], "ANSI37", 0.5)
p1.pline([(-20, 10), (-20, 0), (-10, 0), (-10, -10), (10, -10), (10, 0), (20, 0), (20, 10)], "A-WALL-CUT")
p1.line((-10, -10), (-10, -70), "A-ELEV")
p1.line((10, -10), (10, -70), "A-ELEV")
for y in (10, 0):
    p1.line((-76, y), (-20, y), "A-GLAZ")
    p1.line((20, y), (240, y), "A-GLAZ")
    p1.line((500, y), (560, y), "A-GLAZ")
p1.rect(240, 10, 500, -10, "A-WALL-CUT")
p1.hatch([(240, 10), (500, 10), (500, -10), (240, -10)], "ANSI31", 2.0)
p1.line((260, 10), (260, -10), "A-WALL-CUT")
p1.line((480, 10), (480, -10), "A-WALL-CUT")
p1.line((-76, -25), (-10, -25), "A-ELEV")
p1.line((10, -25), (560, -25), "A-ELEV")
p1.line((-76, -68), (560, -68), "A-HIDDEN")
p1.breakline((-76, 30), (-76, -90), "A-ELEV")
p1.breakline((560, 30), (560, -90), "A-ELEV")
r = p1.bubble(0, -118, "C")
p1.line((0, -70), (0, -118 + r), "A-GRID")
p1.dim_chain([-70, -10, 0, 10, 35, 65], 60)
p1.dim_chain([-20, -10, 10, 20], -40, vertical=False)
p1.dim_chain([20, 240, 260, 480, 500], -48, vertical=False)
p1.dim_chain([-12.5, 12.5], 72, vertical=False)
p1.dim_chain([-7.5, 7.5], 150, vertical=False)
p1.dim_chain([-70, -25, -10, 10], 520)
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
    return (4000 + (px - 3345) / 1.2, 885 + (2145 - py) / 1.2)


def cc_m(px, py):
    return (5200 + (px - 4065) / 6.0, 1943 + (1440 - py) / 6.0)


def gr_m(px, py):
    return (6200 + (px - 2725) / 6.0, 1000 + (740 - py) / 6.0)


viewport(330, 640, 2700, 2330, aa_m((330 + 2700) / 2, (640 + 2330) / 2), 10)
viewport(3020, 600, 3900, 2520, b_m((3020 + 3900) / 2, (600 + 2520) / 2), 5)
viewport(3880, 560, 4720, 1990, cc_m((3880 + 4720) / 2, (560 + 1990) / 2), 1)
viewport(2380, 600, 3060, 1440, gr_m((2380 + 3060) / 2, (600 + 1440) / 2), 1)
viewport(420, 2520, 1360, 3180, (p3.ox + ((420 + 1360) / 2 - 576) / 1.2, p3.oy + (2651 - (2520 + 3180) / 2) / 1.2), 5)
viewport(1560, 2520, 2600, 3180, (p2.ox + ((1560 + 2600) / 2 - 1769) / 1.2, p2.oy + (2796 - (2520 + 3180) / 2) / 1.2), 5)
viewport(2740, 2520, 3700, 3180, (p1.ox + ((2740 + 3700) / 2 - 2908) / 1.2, p1.oy + (2805 - (2520 + 3180) / 2) / 1.2), 5)

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
