"""Small PNG byte builders shared by the engine and webui test modules.

Lives here rather than in generate_fixtures.py because these are built at
TEST time (as replacement-image inputs), not baked into a checked-in
fixture file the way the fixture PDFs are.
"""
import pymupdf as fitz


def solid_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    """A solid-color PNG of the given pixel dimensions. `color` is 0-255 RGB."""
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height))
    pixmap.set_rect(pixmap.irect, color)
    return pixmap.tobytes("png")
