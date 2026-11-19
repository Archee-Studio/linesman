"""The README banner: drawn from the generator, opaque, with text as paths so no font is needed to view it."""

import importlib.util
from pathlib import Path

TOOL = Path(__file__).parents[1] / "tools" / "banner.py"


def test_banner_renders_both_themes_opaque_and_font_free(tmp_path):
    spec = importlib.util.spec_from_file_location("banner", TOOL)
    banner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(banner)
    banner.main(tmp_path)
    for theme, (background, _) in banner.THEMES.items():
        svg = (tmp_path / f"banner-{theme}.svg").read_text()
        assert f'<rect fill="{background}"' in svg
        assert "<text" not in svg and "font-family" not in svg
