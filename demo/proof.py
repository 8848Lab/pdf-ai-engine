"""Produces the film's proof beat, as real evidence rather than a claim.

The interesting question is not "is the SSN gone from the exported file" in
the abstract -- it is "gone compared to what?". So this builds BOTH
outcomes from the same source document and extracts text from each:

  naive   -- a black rectangle drawn over the text, which is what a great
             many "redaction" workflows actually do. It looks redacted.
  engine  -- the file this project's engine produced.

Then it copy-pastes out of both, the way a recipient would.

Writes proof-comparison.json next to the captures. Run via capture.mjs, or
directly:  ../.venv/Scripts/python.exe proof.py
"""
import json
from pathlib import Path

import pymupdf as fitz

HERE = Path(__file__).parent
REPO = HERE.parent
CAPTURES = HERE / "public" / "captures"

SOURCE = REPO / "webui" / "static" / "sample-document.pdf"
ENGINE_OUTPUT = CAPTURES / "redacted.pdf"
NAIVE_OUTPUT = CAPTURES / "naive-blackbox.pdf"

# The four values the engine's run actually removed. The naive comparison
# covers exactly these same four, so the two sides differ only in HOW the
# content was removed -- not in how much of it was targeted. A comparison
# where one side covered fewer lines would be unfair in our own favour.
NEEDLES = ["512-34-9081", "03/14/1985", "(208) 555-0173", "(208) 555-0199"]


def build_naive_blackbox() -> None:
    """Draw opaque rectangles over the sensitive lines and save.

    Deliberately the naive approach: it covers the pixels and never touches
    the text layer. This is not a strawman -- it is what you get from
    annotating a PDF in most everyday tools.
    """
    doc = fitz.open(SOURCE)
    page = doc[0]
    for needle in NEEDLES:
        for rect in page.search_for(needle):
            # Pad to cover the whole label+value line, as a person would.
            box = fitz.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2)
            page.draw_rect(box, color=None, fill=(0, 0, 0))
    doc.save(NAIVE_OUTPUT)
    doc.close()


def extract(path: Path) -> str:
    doc = fitz.open(path)
    text = "".join(page.get_text() for page in doc)
    doc.close()
    return text


def recovered_from(path: Path) -> dict:
    text = extract(path)
    return {needle: needle in text for needle in NEEDLES}


def render(path: Path, name: str, zoom: float = 2.0) -> None:
    """Render page 0 to PNG at a fixed zoom.

    Both sides of the comparison are rendered the same way from the PDFs
    themselves, so the film's side-by-side is genuinely like-for-like rather
    than one screenshot against one render.
    """
    doc = fitz.open(path)
    pixmap = doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    pixmap.save(CAPTURES / f"{name}.png")
    doc.close()


def main() -> None:
    build_naive_blackbox()
    render(NAIVE_OUTPUT, "compare-naive")
    render(ENGINE_OUTPUT, "compare-engine")

    result = {
        "needles": NEEDLES,
        "source": recovered_from(SOURCE),
        "naive_blackbox": recovered_from(NAIVE_OUTPUT),
        "engine": recovered_from(ENGINE_OUTPUT),
    }

    # State the limits of the evidence in the artifact itself, so nobody
    # later reads more into it than it supports.
    result["method"] = (
        "Text extracted with PyMuPDF's get_text(), which is the same text a "
        "reader gets by selecting and copying. A raw-byte search is NOT used: "
        "PDF writes text with per-glyph positioning, so a literal digit run "
        "does not appear contiguously even in the untouched original, and a "
        "byte search would read as proof while proving nothing."
    )

    (CAPTURES / "proof-comparison.json").write_text(json.dumps(result, indent=2))

    print(json.dumps(result, indent=2))
    naive_leaks = [n for n, found in result["naive_blackbox"].items() if found]
    engine_leaks = [n for n, found in result["engine"].items() if found]
    print(f"\nnaive black box still leaks: {naive_leaks}")
    print(f"engine leaks:                {engine_leaks}")


if __name__ == "__main__":
    main()
