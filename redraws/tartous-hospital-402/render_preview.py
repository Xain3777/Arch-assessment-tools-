import sys, ezdxf, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy, LineweightPolicy
doc = ezdxf.readfile(sys.argv[1])
fig = plt.figure(figsize=(841/25.4, 594/25.4))
ax = fig.add_axes([0, 0, 1, 1])
cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.MONOCHROME_LIGHT_BG,
                    lineweight_policy=LineweightPolicy.ABSOLUTE, lineweight_scaling=1.0, min_lineweight=0.05)
Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(doc.layouts.get("SHEET-165"), finalize=True)
ax.set_xlim(0,841); ax.set_ylim(0,594); ax.set_aspect("auto"); fig.set_size_inches(841/25.4, 594/25.4)
fig.savefig(sys.argv[2], dpi=int(sys.argv[3]))
