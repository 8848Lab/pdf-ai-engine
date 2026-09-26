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
``page.mediabox``, ``page.cropbox`` and MuPDF's own page transform -- never a
page's raw /MediaBox, /CropBox, /Rotate or /UserUnit keys. Coordinator ruling
C15: an earlier version re-parsed those raw keys, and MuPDF's own parser
turned out to disagree with that re-parsing in a long tail of cases (reference
depth and dangling references, whether a null or a cycle stops an inheritance
walk, how a malformed box's entries are read, the letter-size MediaBox
fallback, int32 vs int64 reads, integer overflow on a huge /Rotate) -- each
one a potential gate bypass, and emulating them one at a time is whack-a-mole.
Reading PyMuPDF's own already-computed geometry instead means the gate agrees
with what gets drawn by construction, because it IS what gets drawn.

Ruling C16: ``page.transformation_matrix`` is NOT MuPDF's own page transform
either, except at rotation 0 -- PyMuPDF derives it from MuPDF's transform only
there, and returns a fixed constant at 90/180/270 that hides a mirrored or
rescaled rotated page. ``page_transform``/``layout_orientation`` below read
the real transform through the low-level ``mupdf`` binding instead, because
PyMuPDF has no public accessor for it.
"""
import contextlib

import pymupdf as fitz
from pymupdf import mupdf


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


# Linear part (a, b, c, d) of MuPDF's page transform at scale 1, for each
# valid rotation. A page laid out at /UserUnit u has the same pattern times u.
_ROTATION_PATTERNS = {0: (1, 0, 0, -1), 90: (0, 1, 1, 0), 180: (-1, 0, 0, 1), 270: (0, -1, -1, 0)}

# PDF coordinates are float32 inside MuPDF, so a fractional position -- which
# is what font metrics, bboxes and the editor's own points are -- drifts by up
# to half the float32 spacing at its magnitude. That was measured at 0.0125pt
# from 2**19 on (0.3pt at 2**24), past the gate's 0.01pt tolerance; at 2**18
# (262,144pt, about 92m) it stays at or below 0.005pt. The PDF spec's own page
# limit is 14,400pt, far below this bound. Ruling C18.
_MAX_COORDINATE_PT = 2 ** 18


def page_transform(page: fitz.Page) -> fitz.Matrix | None:
    """MuPDF's own page transform, or None if this PyMuPDF cannot provide it.

    page.transformation_matrix is NOT this: PyMuPDF derives it from MuPDF's
    transform only at rotation 0 and returns a constant at 90/180/270, which
    hides a mirrored or rescaled rotated page. There is no public accessor,
    so this uses the low-level binding; None fails closed.
    """
    try:
        ctm = mupdf.FzMatrix()
        mupdf.pdf_page_transform(page._pdf_page(), mupdf.FzRect(mupdf.FzRect.Fixed_UNIT), ctm)
    except (AttributeError, TypeError):
        return None
    return fitz.Matrix(ctm.a, ctm.b, ctm.c, ctm.d, ctm.e, ctm.f)


def layout_orientation(page: fitz.Page) -> tuple[int, float] | None:
    """(rotation, scale) that MuPDF actually lays the page out at, or None if
    its transform is not a valid rotation at one positive scale."""
    ctm = page_transform(page)
    if ctm is None:
        return None
    linear = (ctm.a, ctm.b, ctm.c, ctm.d)
    scale = max(abs(value) for value in linear)
    if scale <= 0:
        return None
    for rotation, pattern in _ROTATION_PATTERNS.items():
        if all(abs(value - p * scale) <= 1e-9 * max(1.0, scale) for value, p in zip(linear, pattern)):
            return rotation, scale
    return None


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
    geometry (never a raw key -- see the module docstring, rulings C15, C16):

    1. An invalid rotation refuses EVERY drawing operation: MuPDF's own page
       transform (``layout_orientation``) is not the rotation PyMuPDF reports
       at any positive scale. This is not just a malformed /Rotate -- a
       negative /UserUnit produces the same mismatch, because mirroring and
       a 180-degree turn share the same linear transform, so both share this
       one message.
    2. Boxes PyMuPDF lays out inconsistently -- no valid layout orientation,
       an empty or sub-point-wide/tall visible area (MuPDF swaps such a box
       for the unit rect; ``page.cropbox`` does not mirror that), or the
       visible area's size disagrees with ``page.rect`` -- refuse EVERY
       drawing operation: the editor cannot place anything on such a page
       reliably.
    3. /UserUnit != 1 refuses EVERY drawing operation, including redaction
       (R12, the owner's ruling): text and fills are drawn at the wrong
       scale, and it is untested whether a scaled redaction removes only
       the intended text.
    4. A page whose real extent is larger than 2**18 points refuses EVERY
       drawing operation: PDF coordinates are float32 inside MuPDF, and a
       fractional position drifts by half the float32 spacing, which passes
       the 0.01pt tolerance from 2**19 on (see ``_MAX_COORDINATE_PT``). The
       extent is every value of ``page.mediabox``, ``page.cropbox`` and
       ``page.rect`` plus the translation (e, f) of MuPDF's own page
       transform: the boxes alone miss a page whose content sits at 2**25 in
       page space, and all three boxes fall back to letter size on MuPDF's
       infinite MediaBox in a repaired file while the transform keeps
       e = f = 2**31.
    5. A CropBox top-left overhang refuses TEXT drawing only (R5). Redaction,
       erasing and image insertion are verified correct on such pages.

    The message is written as a warning to the operator, per the owner's
    instruction: it names the cause, says nothing changed, and -- for
    /UserUnit -- that support is planned.

    It can also RAISE rather than return: ``IndexError`` from PyMuPDF's own
    ``page.rect`` on some infinite-bound pages (``Page.bound()`` reads an
    empty MuPDF warning buffer), and ``FzErrorFormat`` on a looping page tree.
    Callers treat an exception as a refusal; the operation-level handling is
    tracked for the final review (ruling C17).

    Callers run this after ``_validate_target``, so on a malformed-rotation
    page whose swapped bounds reject the bbox first, the operator sees an
    off-page error instead of this one. Either way nothing is modified.
    """
    layout = layout_orientation(page)
    if layout is not None and layout[0] != page.rotation:
        return (
            f"Page {page_index} has an invalid rotation: PyMuPDF lays it out at a "
            f"different orientation than its /Rotate states (a /Rotate that is not a "
            f"multiple of 90, or a negative /UserUnit), so this operation was not "
            f"applied and nothing was changed."
        )
    visible = visible_area(page)
    width, height = visible.width, visible.height
    if page.rotation in (90, 270):
        width, height = height, width
    unit = layout[1] if layout is not None else None
    if (
        unit is None
        or visible.is_empty
        or width < 1 or height < 1  # MuPDF swaps a sub-point box for the unit rect; page.cropbox does not
        or abs(page.rect.width - unit * width) > _LAYOUT_TOLERANCE_PT
        or abs(page.rect.height - unit * height) > _LAYOUT_TOLERANCE_PT
    ):
        return (
            f"Page {page_index} has page boxes that PyMuPDF lays out "
            f"inconsistently (a malformed CropBox, MediaBox or /UserUnit), so the "
            f"editor cannot place anything on it reliably. This operation was not "
            f"applied and nothing was changed."
        )
    if abs(unit - 1) * max(page.rect.width, page.rect.height) / unit > _LAYOUT_TOLERANCE_PT:
        return (
            f"Page {page_index} uses PDF /UserUnit scaling ({unit:.10g}), which the "
            f"editor does not support yet, so this operation was not applied and "
            f"nothing was changed. Support is planned."
        )
    # layout is not None here, so neither is the transform (rule 2 refuses None).
    ctm = page_transform(page)
    values = [v for box in (page.mediabox, page.cropbox, page.rect) for v in box] + [ctm.e, ctm.f]
    if any(abs(v) > _MAX_COORDINATE_PT for v in values):
        return (
            f"Page {page_index} has page boxes larger than {_MAX_COORDINATE_PT} "
            f"points, where PDF coordinates lose precision and content lands in the "
            f"wrong place, so this operation was not applied and nothing was changed."
        )
    if kind == TEXT_DRAWING and crop_origin_overhangs(page):
        return (
            f"Page {page_index} has a CropBox that extends past the top-left of its "
            f"MediaBox. Text drawn on such a page lands in the wrong place, so this "
            f"operation was not applied and nothing was changed. Redaction and "
            f"deleting content still work on this page."
        )
    return None
