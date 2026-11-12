"""Command-line interface.

    archvec analyze  plan.pdf
    archvec process  plan.pdf -o out/plan [--scale 100] [--config cfg.toml] [--set section.key=value]
    archvec synth    samples/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .config import Config


def _cmd_analyze(args) -> int:
    from .pdf_input import analyze_pdf

    for info in analyze_pdf(args.input):
        print(json.dumps(info.to_dict(), indent=1))
    return 0


def _cmd_process(args) -> int:
    from .pipeline import run

    overrides = list(args.set or [])
    if args.page is not None:
        overrides.append(f"input.page={args.page}")
    if args.dpi is not None:
        overrides.append(f"input.dpi={args.dpi}")
    if args.scale is not None:
        overrides.append(f"scale.denominator={float(args.scale)}")
    if args.known_distance:
        x1, y1, x2, y2, mm = args.known_distance
        overrides.append(f"scale.known_distance_px=[{x1}, {y1}, {x2}, {y2}]")
        overrides.append(f"scale.known_distance_mm={mm}")
    cfg = Config.load(args.config, overrides)
    out = Path(args.output) if args.output else Path("output") / Path(args.input).stem
    res = run(args.input, out, cfg, truth=args.truth, verbose=args.verbose)
    print(json.dumps({"outputs": res.outputs, "summary": res.drawing.summary(),
                      "ink_all": res.report.get("ink_all"), "ink_geometry": res.report.get("ink_geometry"),
                      "scale": res.report.get("scale", {}).get("source")}, indent=1))
    return 0


def _cmd_synth(args) -> int:
    from .synthetic import write_scan_pdf, write_vector_pdf

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    write_scan_pdf(out / "synthetic_scan.pdf", rotate_deg=args.rotate, seed=args.seed)
    write_vector_pdf(out / "synthetic_vector.pdf")
    print(f"wrote {out / 'synthetic_scan.pdf'} and {out / 'synthetic_vector.pdf'} (+ .truth.json)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="archvec", description="Architectural PDF vectorisation")
    p.add_argument("--version", action="version", version=f"archvec {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="classify PDF pages (raster / vector / hybrid)")
    a.add_argument("input")
    a.set_defaults(func=_cmd_analyze)

    r = sub.add_parser("process", help="vectorise one page")
    r.add_argument("input")
    r.add_argument("-o", "--output", help="output folder (default: output/<stem>)")
    r.add_argument("-c", "--config", help="TOML configuration file")
    r.add_argument("--page", type=int)
    r.add_argument("--dpi", type=int, help="render resolution when the page must be rasterised")
    r.add_argument("--scale", type=float, help="drawing scale denominator, e.g. 100 for 1:100")
    r.add_argument("--known-distance", type=float, nargs=5, metavar=("X1", "Y1", "X2", "Y2", "MM"),
                   help="two points in working-image pixels and their real distance in mm")
    r.add_argument("--truth", help="ground-truth JSON for validation")
    r.add_argument("--set", action="append", metavar="SECTION.KEY=VALUE", help="override a config value")
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(func=_cmd_process)

    s = sub.add_parser("synth", help="generate synthetic test sheets with ground truth")
    s.add_argument("output")
    s.add_argument("--rotate", type=float, default=0.8)
    s.add_argument("--seed", type=int, default=7)
    s.set_defaults(func=_cmd_synth)
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"archvec: error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - report, details are in run.log
        print(f"archvec: unexpected error: {type(exc).__name__}: {exc} (see run.log)", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
