"""Text measurement is platform-independent: every font request resolves to ezdxf's
built-in MonospaceFont (pinned in linesman/__init__.py), so the grader gives the same
scores on a macOS workstation and a bare Linux container."""

import ezdxf
from ezdxf.fonts import fonts as ezfonts
from ezdxf.fonts.font_manager import FontFace

from linesman.geo import text_box


def _sample():
    doc = ezdxf.new()
    msp = doc.modelspace()
    text = msp.add_text("50", height=2.5)
    mtext = msp.add_mtext("DIM 50\\Pnext", dxfattribs={"char_height": 2.5})
    return text, mtext


def test_text_and_mtext_boxes_are_the_monospace_metrics():
    text, mtext = _sample()
    assert text_box(text) == (0.0, -0.8325, 5.0, 2.5)
    assert text_box(mtext) == (0.0, -3.75, 10.0, 0.0)


def test_text_box_ignores_the_system_font_lookup(monkeypatch):
    text, mtext = _sample()
    monkeypatch.setattr(
        ezfonts.font_manager,
        "find_best_match",
        lambda **kw: FontFace(family="Wide", style="Regular", filename="DejaVuSansCondensed-Bold.ttf"),
    )
    assert text_box(text) == (0.0, -0.8325, 5.0, 2.5)
    assert text_box(mtext) == (0.0, -3.75, 10.0, 0.0)
