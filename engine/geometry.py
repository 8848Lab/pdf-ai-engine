"""Coordinate-space correctness for PyMuPDF pages.

PyMuPDF exposes two coordinate spaces that disagree whenever a page carries
rotation, a CropBox, fractional dimensions or /UserUnit:

- the UNROTATED page space that ``get_text()`` reports bboxes in, and that
  the drawing calls (``insert_textbox``, ``insert_image``,
  ``add_redact_annot``) accept;
- the DISPLAY space of ``page.rect`` and of every rendered pixmap.

Every bound check and every pixel lookup in engine/operations.py must pick
the right one. This module is the single place that knows how. See
docs/superpowers/specs/2026-09-26-page-operations-design.md, rulings R2,
R3, R4, R5, R11, R12 and R16, for the evidence behind each function.
"""
import contextlib
import re

import pymupdf as fitz


def unrotated_bounds(page: fitz.Page) -> fitz.Rect:
    """The page's extent in the unrotated space bboxes are reported in.

    ``page.rect`` is the display box, whose width and height swap at 90
    and 270. Un-swapping them gives the true unrotated extent. Verified on
    1,024 configurations (shifted, fractional and negative MediaBox origins,
    every CropBox overhang, /UserUnit 0.5-2, all four rotations).

    Deliberately NOT ``page.rect * page.derotation_matrix``: that returns
    ``(0,88,612,880)`` at rotation 90 on a CropBox extending past the
    MediaBox, and rejects visible text.
    """
    width, height = page.rect.width, page.rect.height
    if page.rotation in (90, 270):
        width, height = height, width
    return fitz.Rect(0, 0, width, height)


def to_display_matrix(page: fitz.Page) -> fitz.Matrix:
    """Maps a point from unrotated page space into display space.

    A rotation by ``page.rotation``, then the translation that brings the
    rotated extent back to the origin. Identical to ``page.rotation_matrix``
    on ordinary pages; it differs exactly where the library matrix is wrong
    (an oversized CropBox, and /UserUnit), which is where it matters.
    """
    matrix = fitz.Matrix(page.rotation)
    rotated = unrotated_bounds(page) * matrix
    return matrix * fitz.Matrix(1, 0, 0, 1, -rotated.x0, -rotated.y0)


@contextlib.contextmanager
def at_rotation_zero(page: fitz.Page):
    """Temporarily draw with the page unrotated, restoring rotation after.

    PyMuPDF's ``insert_image`` and its redaction fill both misplace their
    output on a rotated page that also has a CropBox: images land 40-52pt
    off, and a redaction's black fill paints ~88pt away from the text it
    removed (the text itself is still removed). Drawing at rotation 0 lands
    both exactly, at every rotation and on both offset and oversized
    CropBoxes. Rotation is restored in a ``finally`` so a failed draw never
    leaves the page with a changed orientation.
    """
    original = page.rotation
    if original == 0:
        yield
        return
    page.set_rotation(0)
    try:
        yield
    finally:
        page.set_rotation(original)


_REFERENCE = re.compile(r"^\s*(\d+)\s+\d+\s+R\s*$")


def _classify(text: str) -> tuple[str, str]:
    """Classify a raw PDF object body already read via ``xref_object``."""
    text = text.strip()
    if text == "null":
        return "null", text
    if text.startswith("["):
        return "array", text
    for kind, cast in (("int", int), ("float", float)):
        try:
            cast(text)
            return kind, text
        except ValueError:
            pass
    return "other", text


def _resolve(doc: fitz.Document, kind: str, value: str) -> tuple[str, str]:
    """Follow a chain of indirect references (``N 0 R``) to a concrete value.

    A key's value can itself be indirect, and the object it points to can in
    turn be another reference. PyMuPDF's own object printer does not always
    collapse a reference to its resolved value -- a reference cycle prints
    the reference text itself rather than resolving forever -- so this loop
    keeps following as long as the text read back is itself a reference. A
    ``seen`` set of visited xrefs guards against a cycle: it resolves to
    ``("null", "null")`` rather than looping forever.

    Direct (non-``"xref"``) values from ``xref_get_key`` are already
    classified by PyMuPDF and are returned unchanged.
    """
    seen: set[int] = set()
    while kind == "xref":
        xref = int(value.split()[0])
        if xref in seen:
            return "null", "null"
        seen.add(xref)
        text = doc.xref_object(xref).strip()
        if _REFERENCE.match(text):
            kind, value = "xref", text
            continue
        kind, value = _classify(text)
    return kind, value


def _inherited(page: fitz.Page, key: str) -> tuple[str, str] | None:
    """A page attribute as written in the PDF, resolving page-tree inheritance.

    /MediaBox, /CropBox and /Rotate are INHERITABLE: set only on an ancestor
    /Pages node, they read as null at page level. This walks the /Parent
    chain, resolving indirect references, and returns ``(kind, value)`` from
    the nearest node that sets the key, or None if none does. A visited set
    guards against a /Parent cycle: a repeated xref returns None instead of
    looping forever (verified: an unguarded walk hangs indefinitely).
    """
    doc = page.parent
    xref = page.xref
    seen: set[int] = set()
    while xref:
        if xref in seen:
            return None
        seen.add(xref)
        kind, value = _resolve(doc, *doc.xref_get_key(xref, key))
        if kind != "null":
            return kind, value
        kind, parent = doc.xref_get_key(xref, "Parent")
        if kind != "xref":
            return None
        xref = int(parent.split()[0])
    return None


def _raw_box(page: fitz.Page, key: str) -> fitz.Rect | None:
    """A box as written in the PDF, in raw PDF user space (y up).

    Read raw, with inheritance resolved, because PyMuPDF's own
    ``page.mediabox``/``page.cropbox`` are converted into two frames that
    disagree on a negative-origin MediaBox, so they cannot be compared
    against each other.

    Returns None for anything that isn't exactly four numbers, including a
    malformed array (too few/many entries, or a non-numeric entry): that
    matches PyMuPDF's own drawing behaviour, verified for a three-entry
    CropBox -- ``insert_text`` places its text exactly where asked, with no
    drift, so treating the malformed box as though it were absent is correct.
    """
    found = _inherited(page, key)
    if found is None or found[0] != "array":
        return None
    parts = found[1].strip("[] \n").split()
    try:
        numbers = [float(v) for v in parts]
    except ValueError:
        return None
    if len(numbers) != 4:
        return None
    box = fitz.Rect(numbers)
    box.normalize()
    return box


def raw_rotation(page: fitz.Page) -> float:
    """The /Rotate value as written, inheritance resolved, defaulting to 0.

    Needed because ``page.rotation`` hides malformed values: for /Rotate 45
    it reports 0 while ``page.rect`` is swapped as if rotated, and an erase
    on such a page removes the text but paints its fill somewhere else.
    """
    found = _inherited(page, "Rotate")
    if found is None or found[0] not in ("int", "float"):
        return 0.0
    return float(found[1])


def user_unit(page: fitz.Page) -> float:
    """The page's /UserUnit, defaulting to 1.

    Read at page level ONLY. PyMuPDF does not inherit /UserUnit (verified:
    set on /Pages alone, it leaves ``page.rect`` unscaled), and it is
    PyMuPDF that draws -- so the gate must agree with PyMuPDF, not with a
    stricter reading of the spec.
    """
    doc = page.parent
    kind, value = _resolve(doc, *doc.xref_get_key(page.xref, "UserUnit"))
    if kind in ("int", "float"):
        return float(value)
    return 1.0


def crop_origin_overhangs(page: fitz.Page) -> bool:
    """True when the CropBox's top-left corner lies outside the MediaBox.

    In that configuration ``insert_text`` and ``insert_textbox`` draw shifted
    by the out-of-bounds offset at every rotation, including 0, while
    ``get_text()`` reads unshifted. Verified exact on 256 unit-1
    configurations: drift occurs iff ``crop.x0 < media.x0`` or
    ``crop.y1 > media.y1`` in raw PDF coordinates.

    Deliberately NOT ``mediabox.contains(cropbox)``: that flags a bottom-only
    overhang, a right-only overhang and a negative-origin MediaBox, none of
    which actually drift (confirmed by mutating this function to that
    expression and rerunning the 256-case matrix test: those three case ids
    are exactly the ones that then fail).
    """
    media = _raw_box(page, "MediaBox")
    if media is None:
        return False
    crop = _raw_box(page, "CropBox") or media
    return crop.x0 < media.x0 or crop.y1 > media.y1


# Operations are grouped by what they paint, because the refusal rules
# apply to different sets. See spec R5 and R12.
TEXT_DRAWING = "text"  # replace_text, move_block (destination), insert_block
OTHER_DRAWING = "other"  # redact_region, delete_block, replace_image, move_block (source)


def drawing_refusal(page: fitz.Page, page_index: int, kind: str) -> str | None:
    """Why an operation must not draw on this page, or None if it may.

    Checked in order, before any mutation:

    1. A /Rotate that is not a multiple of 90 refuses EVERY drawing
       operation. The file is malformed, PyMuPDF reports it inconsistently
       (rotation 0 with a swapped rect), and an erase on such a page removes
       the text but paints its fill elsewhere.
    2. /UserUnit != 1 refuses EVERY drawing operation, including redaction
       (R12, the owner's ruling): text and fills are drawn at the wrong
       scale, and it is untested whether a scaled redaction removes only
       the intended text.
    3. A CropBox top-left overhang refuses TEXT drawing only (R5). Redaction,
       erasing and image insertion are verified correct on such pages.

    The message is written as a warning to the operator, per the owner's
    instruction: it names the cause, says nothing changed, and -- for
    /UserUnit -- that support is planned.

    Callers run this after ``_validate_target``, so on a malformed-rotation
    page whose swapped bounds reject the bbox first, the operator sees an
    off-page error instead of this one. Either way nothing is modified.
    """
    rotate = raw_rotation(page)
    if rotate % 90 != 0:
        return (
            f"Page {page_index} has an invalid rotation (/Rotate {rotate:g}; the PDF "
            f"format requires a multiple of 90), so this operation was not applied "
            f"and nothing was changed."
        )
    unit = user_unit(page)
    if unit != 1:
        return (
            f"Page {page_index} uses PDF /UserUnit scaling ({unit:g}), which the "
            f"editor does not support yet, so this operation was not applied and "
            f"nothing was changed. Support is planned."
        )
    if kind == TEXT_DRAWING and crop_origin_overhangs(page):
        return (
            f"Page {page_index} has a CropBox that extends past the top-left of its "
            f"MediaBox. Text drawn on such a page lands in the wrong place, so this "
            f"operation was not applied and nothing was changed. Redaction and "
            f"deleting content still work on this page."
        )
    return None
