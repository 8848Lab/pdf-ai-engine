"""Read-oriented projection of a PDF's structure.

Document/Page/TextBlock/Image exist for callers to inspect a PDF and find
redaction-target coordinates. They are not the write path -- operations.py
mutates the live PyMuPDF document handle directly. See the design spec's
"Data model" section.
"""
from dataclasses import dataclass, field


@dataclass
class TextBlock:
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    # Optional metadata for replace_text's widen-before-shrink path (plan
    # 2026-09-28-replace-text-widen, spec W1/W5/D3). All three default to
    # None so every existing constructor call (built by hand, not through
    # parse()) stays valid.
    origin: tuple[float, float] | None = None
    direction: tuple[float, float] | None = None
    color: tuple[float, float, float] | None = None


@dataclass
class Image:
    """One PLACEMENT of an image on a page -- not one image object. The same
    underlying PDF image object (`xref`) drawn twice on a page produces two
    Images here, sharing an xref but carrying different bboxes, so each
    placement can be targeted independently.
    """
    bbox: tuple[float, float, float, float]
    xref: int
    width: int
    height: int
    # All three counts below identify an image by its CONTENT DIGEST, not its xref.
    # The same picture is routinely stored as a separate image object per
    # page -- any merge of separately-built PDFs does this -- and an
    # xref-keyed count reports "appears once" on every page while the same
    # picture is on all of them, which is silence in exactly the case the
    # operator needs a warning.
    #
    # placement_count is how many times it is drawn on THIS page;
    # document_placement_count is how many times in the whole document; and
    # document_page_count is how many PAGES contain it. The last is the one
    # to phrase an operator-facing warning in: a placement count cannot be
    # described as a number of pages without being wrong whenever an image is
    # drawn twice somewhere.
    #
    # Why any of this is surfaced: replacing a placement changes only that
    # placement, so when the picture also appears elsewhere the original
    # survives there -- and export()'s garbage pass cannot reclaim it,
    # because another page still references it.
    #
    # A count of 1 is not a guarantee of absence. Two visually identical
    # images that differ by even one pixel hash differently and are counted
    # separately.
    placement_count: int
    document_placement_count: int
    document_page_count: int


@dataclass
class Page:
    index: int
    width: float
    height: float
    text_blocks: list[TextBlock] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)


@dataclass
class Document:
    pages: list[Page] = field(default_factory=list)
