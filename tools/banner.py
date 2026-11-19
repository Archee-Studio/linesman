"""Draw the README banner as a Linesman sheet and render it to SVG, light and dark.

Usage: uv run python tools/banner.py <out-dir>
The shaft comes from the shaft family's generator, so the banner is the benchmark's own drafting.
"""

import sys
from pathlib import Path

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, layout, svg
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration

from linesman.families import shaft
from linesman.families.drafting import ddim, hdim, line, new_sheet
from linesman.schema import SPEC_VERSION

W, H = 300.0, 100.0  # banner sheet, millimetres
SEED = 7
THEMES = {"light": ("#ffffff", "#131b26"), "dark": ("#0d1117", "#e6edf3")}


def sheet() -> ezdxf.document.Drawing:
    doc = new_sheet()
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (W, 0), (W, H), (0, H)], close=True, dxfattribs={"layer": "frame"})
    steps = shaft.sample(SEED)["steps"]
    x, axis, top = 20.0, 46.0, []
    for step in steps:
        r, length = step["diameter"] / 2, step["length"]
        for a, b in (((x, axis - r), (x + length, axis - r)), ((x, axis + r), (x + length, axis + r))):
            line(msp, a, b)
        top.append((x, r))
        x += length
    edges = [(x0, r) for x0, r in top] + [(x, top[-1][1])]
    for i, (x0, r) in enumerate(edges):
        prev = top[i - 1][1] if 0 < i < len(top) else 0.0
        reach = max(r, prev)
        line(msp, (x0, axis - reach), (x0, axis + reach))
    line(msp, (12, axis), (x + 8, axis), layer="center")
    for (x0, r), step in zip(top, steps, strict=True):
        hdim(msp, (x0, axis + r), (x0 + step["length"], axis + r), axis + 30)
        fit = f" {step['fit']}" if step["fit"] else ""
        cx = x0 + step["length"] / 2
        ddim(msp, (cx, axis), step["diameter"], 90.0, text=f"<>{fit}", location=(cx, axis - r - 14))
    hdim(msp, (20, axis + top[0][1]), (x, axis + top[0][1]), axis + 42)
    block(msp, x0=W - 150.0)
    return doc


def block(msp, x0: float) -> None:
    rows = (
        ("SCORED", "from the file, against its calculation"),
        ("SPEC", SPEC_VERSION),
        ("WHAT", "a benchmark for drafting sheets"),
    )
    y0, h = 12.0, 76.0
    msp.add_lwpolyline(
        [(x0, y0), (W - 12, y0), (W - 12, y0 + h), (x0, y0 + h)], close=True, dxfattribs={"layer": "frame"}
    )
    msp.add_text("LINESMAN", height=16.0, dxfattribs={"layer": "frame"}).set_placement((x0 + 6, y0 + 3 * 12.0 + 12))
    row = 12.0
    for i, (label, value) in enumerate(rows):
        y = y0 + i * row
        msp.add_line((x0, y + row), (W - 12, y + row), dxfattribs={"layer": "frame"})
        msp.add_text(label, height=2.5, dxfattribs={"layer": "frame"}).set_placement((x0 + 4, y + 4.5))
        msp.add_text(value, height=3.5, dxfattribs={"layer": "frame"}).set_placement((x0 + 26, y + 4.2))


def render(doc, background: str, ink: str) -> str:
    cfg = Configuration(
        background_policy=BackgroundPolicy.CUSTOM,
        custom_bg_color=background,
        color_policy=ColorPolicy.CUSTOM,
        custom_fg_color=ink,
    )
    backend = svg.SVGBackend()
    Frontend(RenderContext(doc), backend, config=cfg).draw_layout(doc.modelspace())
    return backend.get_string(layout.Page(W, H, layout.Units.mm))


def main(out: Path) -> None:
    doc = sheet()
    for name, (background, ink) in THEMES.items():
        (out / f"banner-{name}.svg").write_text(render(doc, background, ink))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
