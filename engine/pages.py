"""Page-level operations: delete, move, rotate, insert blank, duplicate.

A sibling of engine/operations.py rather than part of it. Those operations
take a page and a target rect and change that region; these take no rect and
change the document's shape. Same contract, though: validate completely
before mutating, raise ValueError naming the problem, never silently no-op,
never produce output that looks right but isn't.

Every validation failure here raises RefusedBeforeMutation, a ValueError, so
callers can tell "nothing was touched" apart from a failure after a mutation.

Page operations shift the page_index of every block and image after the
affected page, so they invalidate every id a caller holds. webui/session.py
already rebuilds both registries with fresh monotonic ids after every
operation, so a stale id raises LookupError instead of resolving to the wrong
content.
"""
import math

import pymupdf as fitz

from engine.errors import RefusedBeforeMutation

# The PDF specification's largest page side (ISO 32000-1, Annex C). Far below
# engine.geometry's 2**18 coordinate bound, so an inserted page can never be
# one the drawing gate would refuse for size.
MAX_PAGE_SIDE_PT = 14400.0
# engine.geometry refuses a visible side under 1pt; an inserted page is never
# made smaller than that.
MIN_PAGE_SIDE_PT = 1.0


def _check_page_index(handle: fitz.Document, page_index: int, name: str = "page_index") -> None:
    if isinstance(page_index, bool) or not isinstance(page_index, int):
        raise RefusedBeforeMutation(f"{name} must be an integer, got {page_index!r}; nothing was changed")
    if page_index < 0 or page_index >= handle.page_count:
        raise RefusedBeforeMutation(
            f"{name} {page_index} is out of range for a document with "
            f"{handle.page_count} page(s); must be 0 <= {name} < {handle.page_count}. "
            f"Nothing was changed."
        )


def delete_page(handle: fitz.Document, page_index: int) -> None:
    """Delete one page.

    Raises:
        RefusedBeforeMutation: page_index out of range, or it is the only
            page -- a PDF with zero pages cannot be saved.
    """
    _check_page_index(handle, page_index)
    if handle.page_count == 1:
        raise RefusedBeforeMutation(
            "cannot delete the only page: a PDF must have at least one page. "
            "Nothing was changed."
        )
    handle.delete_page(page_index)


def move_page(handle: fitz.Document, page_index: int, to_index: int) -> None:
    """Move one page so that, after the call, it is at to_index.

    Final-index semantics: every other page keeps its relative order.
    PyMuPDF's own move_page inserts BEFORE its target, so it is translated
    here (spec F5, verified on all 16 pairs of a four-page document).
    to_index == page_index is a valid no-op, not an error.

    Raises:
        RefusedBeforeMutation: either index out of range.
    """
    _check_page_index(handle, page_index)
    _check_page_index(handle, to_index, "to_index")
    last = handle.page_count - 1
    if to_index == page_index:
        return
    if to_index == last:
        handle.move_page(page_index, -1)
    elif to_index > page_index:
        handle.move_page(page_index, to_index + 1)
    else:
        handle.move_page(page_index, to_index)


def rotate_page(handle: fitz.Document, page_index: int, rotation: int) -> None:
    """Set one page's rotation to an ABSOLUTE value.

    Absolute, not relative: the driving case is "fix the sideways scan", where
    the caller knows the target orientation. Negative values and multiples of
    360 are normalised (-90 -> 270, 450 -> 90, 360 -> 0).

    PyMuPDF's set_rotation silently turns a non-multiple of 90 into 0, so the
    check here is the only thing that stops "rotate by 45" becoming "reset to
    upright".

    Raises:
        RefusedBeforeMutation: page_index out of range, or rotation is not an
            integer multiple of 90.
    """
    _check_page_index(handle, page_index)
    if isinstance(rotation, bool) or not isinstance(rotation, int) or rotation % 90 != 0:
        raise RefusedBeforeMutation(
            f"rotation must be a whole multiple of 90 degrees (0, 90, 180 or 270), "
            f"got {rotation!r}. Nothing was changed."
        )
    # set_rotation normalises -90 -> 270 and 450 -> 90 itself; the
    # normalisation test pins that, so a PyMuPDF change would fail it.
    handle[page_index].set_rotation(rotation)


def _side(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RefusedBeforeMutation(f"{name} must be a finite number, got {value!r}. Nothing was changed.")
    if not MIN_PAGE_SIDE_PT <= value <= MAX_PAGE_SIDE_PT:
        raise RefusedBeforeMutation(
            f"{name} must be between {MIN_PAGE_SIDE_PT:g} and {MAX_PAGE_SIDE_PT:g} points, "
            f"got {value!r}. Nothing was changed."
        )
    return float(value)


def insert_page(
    handle: fitz.Document,
    at_index: int,
    width: float | None = None,
    height: float | None = None,
) -> None:
    """Insert a blank page so that, after the call, it is at at_index.

    0 <= at_index <= page_count; at_index == page_count appends. Each missing
    dimension defaults independently to the neighbour's DISPLAY width or
    height (what the operator sees: a page shown in landscape gets a
    landscape blank), where the neighbour is the page currently at at_index,
    or the last page when appending. PyMuPDF's own default is A4 regardless
    of the neighbour, so the size is always passed explicitly (spec R6). The
    new page has rotation 0.

    Raises:
        RefusedBeforeMutation: at_index out of range, or a given dimension is
            not a finite number between 1 and 14,400 points.
    """
    if isinstance(at_index, bool) or not isinstance(at_index, int):
        raise RefusedBeforeMutation(f"at_index must be an integer, got {at_index!r}. Nothing was changed.")
    if at_index < 0 or at_index > handle.page_count:
        raise RefusedBeforeMutation(
            f"at_index {at_index} is out of range for a document with {handle.page_count} "
            f"page(s); must be 0 <= at_index <= {handle.page_count} (equal appends). "
            f"Nothing was changed."
        )
    neighbour = handle[at_index if at_index < handle.page_count else handle.page_count - 1].rect
    new_width = _side(neighbour.width if width is None else width, "width")
    new_height = _side(neighbour.height if height is None else height, "height")
    handle.new_page(at_index if at_index < handle.page_count else -1, width=new_width, height=new_height)
