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
        raise RefusedBeforeMutation(f"{name} must be an integer, got {page_index!r}. Nothing was changed.")
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
    to_index == page_index is a valid no-op, not an error -- checked and
    returned BEFORE any pinning, so it stays a byte-identical no-op.

    The moved page's inheritable attributes are pinned onto its own dict
    before the move (see _pin_inherited_attributes): PyMuPDF's move_page
    files the page under its new neighbour's /Parent, whose inherited values
    may differ from the page's current ones.

    Raises:
        RefusedBeforeMutation: either index out of range.
    """
    _check_page_index(handle, page_index)
    _check_page_index(handle, to_index, "to_index")
    last = handle.page_count - 1
    if to_index == page_index:
        return
    _pin_inherited_attributes(handle, page_index)
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
            f"rotation must be a whole multiple of 90 degrees (it is normalised to "
            f"0, 90, 180 or 270), got {rotation!r}. Nothing was changed."
        )
    # `% 360` is REQUIRED here, not just tidy: PyMuPDF's set_rotation
    # normalises with `while r >= 360: r -= 360` / `while r < 0: r += 360`,
    # a LINEAR loop. Without reducing first, a huge multiple of 90 (e.g.
    # 90 * 2**64) would make set_rotation loop effectively forever.
    handle[page_index].set_rotation(rotation % 360)


def _side(value: object, name: str, *, source: str | None = None) -> float:
    """Validate one page dimension (or the neighbour's, when defaulted)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RefusedBeforeMutation(f"{name} must be a real number (int or float), got {value!r}. Nothing was changed.")
    # The range check alone also rejects NaN and +-inf (every comparison
    # against them is False), so it runs BEFORE any float conversion: for an
    # out-of-range int, e.g. 10**400, math.isfinite(value) would first try to
    # convert it to a float and raise OverflowError instead of refusing it.
    if not MIN_PAGE_SIDE_PT <= value <= MAX_PAGE_SIDE_PT:
        if source is not None:
            raise RefusedBeforeMutation(
                f"{source} ({value:g}pt) is outside {MIN_PAGE_SIDE_PT:g}-{MAX_PAGE_SIDE_PT:g} "
                f"points; give {name} explicitly. Nothing was changed."
            )
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

    The neighbour is looked up ONLY when a dimension is missing: handle[-1]
    loops forever in PyMuPDF when the document has zero pages, and a
    zero-page PDF is otherwise a valid document to operate on.

    Raises:
        RefusedBeforeMutation: at_index out of range; a given dimension is
            not a finite number between 1 and 14,400 points; a dimension
            defaulted from the neighbour is out of that range (a page wider
            or taller than 14,400pt); or a dimension is missing and the
            document has no pages to take a size from.
    """
    if isinstance(at_index, bool) or not isinstance(at_index, int):
        raise RefusedBeforeMutation(f"at_index must be an integer, got {at_index!r}. Nothing was changed.")
    if at_index < 0 or at_index > handle.page_count:
        raise RefusedBeforeMutation(
            f"at_index {at_index} is out of range for a document with {handle.page_count} "
            f"page(s); must be 0 <= at_index <= {handle.page_count} (equal appends). "
            f"Nothing was changed."
        )
    neighbour = None
    if width is None or height is None:
        if handle.page_count == 0:
            raise RefusedBeforeMutation(
                "the document has no pages to take a size from; give both width and height. "
                "Nothing was changed."
            )
        neighbour = handle[at_index if at_index < handle.page_count else handle.page_count - 1].rect
    new_width = (
        _side(width, "width")
        if width is not None
        else _side(neighbour.width, "width", source="the neighbouring page's display width")
    )
    new_height = (
        _side(height, "height")
        if height is not None
        else _side(neighbour.height, "height", source="the neighbouring page's display height")
    )
    handle.new_page(at_index if at_index < handle.page_count else -1, width=new_width, height=new_height)


_INHERITABLE_PAGE_KEYS = ("Resources", "MediaBox", "CropBox", "Rotate")


def _effective_inherited(handle: fitz.Document, xref: int, key: str):
    """The first non-null `key` found walking /Parent from `xref` (inclusive).

    Returns handle.xref_get_key's raw (kind, value) pair, or None if no node
    in the chain defines it. A visited set guards a /Parent cycle -- Merge A
    found that a hand-crafted PDF can have one, and walking it unguarded
    would loop forever.
    """
    visited = set()
    current = xref
    while current is not None and current not in visited:
        visited.add(current)
        kind, value = handle.xref_get_key(current, key)
        if kind != "null":
            return kind, value
        parent_kind, parent_value = handle.xref_get_key(current, "Parent")
        current = int(parent_value.split()[0]) if parent_kind == "xref" else None
    return None


def _pin_inherited_attributes(handle: fitz.Document, page_index: int) -> None:
    """Make a page's effective inheritable attributes explicit on its own dict.

    Resources, MediaBox, CropBox and Rotate are INHERITABLE (ISO 32000-1
    Table 30): a page missing one of these keys takes it from the nearest
    ancestor /Pages node that has it. move_page and fullcopy_page file the
    page under a new /Parent, which may inherit DIFFERENT values for these
    keys -- two /Pages nodes from a merged document commonly do. Without
    this, a moved or duplicated page can pick up the wrong ancestor's
    values: it renders blank, in the wrong font, or at the wrong size.

    This is a no-op when a key is already explicit on the page. Writing the
    effective (possibly inherited) value explicitly never changes how the
    page currently renders -- only where that value comes from.
    """
    xref = handle[page_index].xref
    for key in _INHERITABLE_PAGE_KEYS:
        own_kind, _ = handle.xref_get_key(xref, key)
        if own_kind != "null":
            continue
        found = _effective_inherited(handle, xref, key)
        if found is not None:
            handle.xref_set_key(xref, key, found[1])


def duplicate_page(handle: fitz.Document, page_index: int) -> None:
    """Insert an independent copy of a page immediately after it.

    Uses fullcopy_page, never copy_page: copy_page aliases the page object
    itself, so redacting the "copy" would also redact the original, and that
    survives export (spec F4, R7). fullcopy_page rejects a target past the
    last page, so a copy of the last page is appended with -1.

    The source's inheritable attributes are pinned onto its own dict before
    the copy is made (see _pin_inherited_attributes): fullcopy_page files the
    copy under the FOLLOWING page's /Parent, whose inherited values may
    differ from the source's, and the copy would otherwise silently take on
    the wrong ones.

    Independent means independently EDITABLE. Links on the copy still point
    where the original's did -- a copied self-link targets the original page
    (spec R8); retargeting links is out of scope, and form fields on the
    copy are likewise not registered as new AcroForm fields.

    The copy may still share the original's /Resources dictionary BY
    REFERENCE (fullcopy_page does not deep-copy it). Editing content on the
    copy can then add a font entry that the original's /Resources lists but
    never uses; the original's rendered content is unaffected.

    Raises:
        RefusedBeforeMutation: page_index out of range.
    """
    _check_page_index(handle, page_index)
    _pin_inherited_attributes(handle, page_index)
    last = handle.page_count - 1
    handle.fullcopy_page(page_index, -1 if page_index == last else page_index + 1)
