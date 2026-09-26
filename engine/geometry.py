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

The drawing-refusal gate (``drawing_refusal`` and what it calls) reads ONLY
PyMuPDF's own interpreted geometry -- ``page.rotation``, ``page.rect``,
``page.mediabox``, ``page.cropbox`` and ``page.transformation_matrix`` --
never a page's raw /MediaBox, /CropBox, /Rotate or /UserUnit keys. Coordinator
ruling C15: an earlier version re-parsed those raw keys, and MuPDF's own
parser turned out to disagree with that re-parsing in a long tail of cases
(reference depth and dangling references, whether a null or a cycle stops an
inheritance walk, how a malformed box's entries are read, the letter-size
MediaBox fallback, int32 vs int64 reads, integer overflow on a huge
/Rotate) -- each one a potential gate bypass, and emulating them one at a
time is whack-a-mole. Reading PyMuPDF's own already-computed geometry instead
means the gate agrees with what gets drawn by construction, because it IS
what gets drawn.
"""
import contextlib

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


# Tolerance, in points over the page's larger side, for "PyMuPDF laid this
# page out at scale 1". /UserUnit 1.0000001 moves nothing measurable and is
# allowed; /UserUnit 1.5 is refused.
_LAYOUT_TOLERANCE_PT = 0.01


def visible_area(page: fitz.Page) -> fitz.Rect:
    """The part of the page PyMuPDF shows, in the frame it reports page.cropbox in.

    PyMuPDF's page.cropbox keeps the PDF's x but measures y DOWN from the
    MediaBox's top edge, so the MediaBox in that frame is
    (mediabox.x0, 0, mediabox.x1, mediabox.height). Both boxes are PyMuPDF's
    own interpretation -- inheritance, references, malformed arrays and the
    letter-size fallback already applied -- which is the point: the gate must
    agree with what PyMuPDF draws, not with our reading of the raw keys.
    """
    mediabox = page.mediabox
    return page.cropbox & fitz.Rect(mediabox.x0, 0, mediabox.x1, mediabox.height)


def rotation_is_valid(page: fitz.Page) -> bool:
    """False when PyMuPDF is in its malformed-rotation state.

    A /Rotate that is not a multiple of 90 -- including one that overflows
    MuPDF's integer conversion, such as 2700000000.0 -- makes PyMuPDF report
    rotation 0 with a swapped rect. Its transformation matrix then has
    off-diagonal terms, which no valid rotation produces.
    """
    matrix = page.transformation_matrix
    return abs(matrix.b) < 1e-9 and abs(matrix.c) < 1e-9


def user_unit(page: fitz.Page) -> float | None:
    """The scale PyMuPDF actually lays this page out at, or None if its boxes
    are inconsistent with any single scale.

    Measured, not read: page.rect divided by the visible area (swapped at
    90/270). This catches every way /UserUnit reaches PyMuPDF -- indirect,
    chained, inherited or not, int64-sized -- and ignores every way it does
    not (a value MuPDF discards is scale 1 here, because it IS drawn at 1).
    """
    visible = visible_area(page)
    width, height = visible.width, visible.height
    if page.rotation in (90, 270):
        width, height = height, width
    if visible.is_empty or width <= 0 or height <= 0:
        return None
    scale_x, scale_y = page.rect.width / width, page.rect.height / height
    if abs(scale_x - scale_y) * max(width, height) > _LAYOUT_TOLERANCE_PT:
        return None
    return scale_x


def crop_origin_overhangs(page: fitz.Page) -> bool:
    """True when the visible area's top-left extends past the MediaBox (R5).

    In PyMuPDF's cropbox frame (see visible_area) that is: left of the
    MediaBox's x0, or above its top edge, y = 0. Text drawn on such a page
    lands in the wrong place. A bottom-only or right-only overhang, or a
    MediaBox with a negative origin, draws correctly and is not flagged --
    the three documents mediabox.contains(cropbox) wrongly refuses.
    """
    return page.cropbox.x0 < page.mediabox.x0 or page.cropbox.y0 < 0


# Operations are grouped by what they paint, because the refusal rules
# apply to different sets. See spec R5 and R12.
TEXT_DRAWING = "text"  # replace_text, move_block (destination), insert_block
OTHER_DRAWING = "other"  # redact_region, delete_block, replace_image, move_block (source)


def drawing_refusal(page: fitz.Page, page_index: int, kind: str) -> str | None:
    """Why an operation must not draw on this page, or None if it may.

    Checked in order, before any mutation, all from PyMuPDF's own interpreted
    geometry (never a raw key -- see the module docstring, ruling C15):

    1. An invalid rotation (``rotation_is_valid`` is False) refuses EVERY
       drawing operation. PyMuPDF reports such a page inconsistently
       (rotation 0 with a swapped rect), and an erase on such a page removes
       the text but paints its fill elsewhere.
    2. Boxes PyMuPDF lays out inconsistently -- ``user_unit`` returns None,
       or the page is mirrored (the transformation matrix's diagonal is not
       positive/negative) -- refuse EVERY drawing operation: the editor
       cannot place anything on such a page reliably.
    3. /UserUnit != 1 refuses EVERY drawing operation, including redaction
       (R12, the owner's ruling): text and fills are drawn at the wrong
       scale, and it is untested whether a scaled redaction removes only
       the intended text.
    4. A CropBox top-left overhang refuses TEXT drawing only (R5). Redaction,
       erasing and image insertion are verified correct on such pages.

    The message is written as a warning to the operator, per the owner's
    instruction: it names the cause, says nothing changed, and -- for
    /UserUnit -- that support is planned.

    Callers run this after ``_validate_target``, so on a malformed-rotation
    page whose swapped bounds reject the bbox first, the operator sees an
    off-page error instead of this one. Either way nothing is modified.
    """
    if not rotation_is_valid(page):
        return (
            f"Page {page_index} has an invalid rotation (its /Rotate is not a "
            f"multiple of 90, as the PDF format requires), so this operation was "
            f"not applied and nothing was changed."
        )
    unit = user_unit(page)
    matrix = page.transformation_matrix
    if unit is None or not (matrix.a > 0 and matrix.d < 0):
        return (
            f"Page {page_index} has page boxes that PyMuPDF lays out "
            f"inconsistently (a malformed CropBox, MediaBox or /UserUnit), so the "
            f"editor cannot place anything on it reliably. This operation was not "
            f"applied and nothing was changed."
        )
    if abs(unit - 1) * max(page.rect.width, page.rect.height) / unit > _LAYOUT_TOLERANCE_PT:
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
