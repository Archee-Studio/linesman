"""Linesman by Archee Studio: a benchmark for generated 2D drafting sheets."""

from ezdxf.fonts import fonts as _ezfonts


def _monospace(font_name: str, cap_height: float, width_factor: float = 1.0):
    # Every font request resolves to ezdxf's built-in metric model: the grader and the family
    # layout must measure text identically on every machine, and the system font set is what
    # varies. make_font is ezdxf's single funnel for TEXT/MTEXT/ATTRIB measurement.
    return _ezfonts.MonospaceFont(cap_height, width_factor)


_ezfonts.make_font = _monospace
