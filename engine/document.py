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
    placement_count: int
    # Placements of this xref on THIS page vs. in the whole document. They
    # differ when one image is drawn on several pages, and the difference is
    # what an operator needs to see: replacing a placement changes only that
    # placement, so when the document-wide count is higher the original image
    # survives elsewhere and stays recoverable from the exported file.
    document_placement_count: int


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
