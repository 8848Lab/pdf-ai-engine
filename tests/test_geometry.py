"""Unit tests for engine/geometry.py.

The two matrix tests are the critic's 1,024-configuration attack on R2. They
collect every failure and assert on the list, so one run reports all of them
rather than stopping at the first.
"""
import threading
import time
from typing import NamedTuple

import pymupdf as fitz
import pytest
from pymupdf import mupdf

from engine.geometry import at_rotation_zero, to_display_matrix, unrotated_bounds
from tests.geometry_helpers import BAND_RGB, ROTATIONS, matrix_cases, matrix_page, reopen

ALL_UNITS = (0.5, 1, 1.5, 2)


def _spans(page):
    # Include text outside the visible area, so OFFPAGE is reported at all.
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP
    blocks = page.get_text("dict", clip=fitz.INFINITE_RECT(), flags=flags)["blocks"]
    return {
        span["text"]: fitz.Rect(span["bbox"])
        for block in blocks if "lines" in block
        for line in block["lines"] for span in line["spans"]
    }


def _pixel(page, point, matrix):
    pix = page.get_pixmap()
    q = fitz.Point(point) * matrix
    x = max(0, min(pix.width - 1, int(q.x - pix.x)))
    y = max(0, min(pix.height - 1, int(q.y - pix.y)))
    return tuple(pix.pixel(x, y)[:3])


def _near(a, b, tol=0.003):
    return max(abs(x - y) for x, y in zip(a, b)) < tol


def test_unrotated_bounds_hold_across_the_1024_case_matrix():
    failures = []
    for name, media, crop, unit, rot in matrix_cases(units=ALL_UNITS):
        doc = reopen(matrix_page(media, crop, unit, rot))
        page = doc[0]
        visible = media & crop
        bounds = unrotated_bounds(page)
        spans = _spans(page)
        if not _near(bounds, (0, 0, visible.width * unit, visible.height * unit)):
            failures.append(f"{name}: extent {tuple(bounds)}")
        if not bounds.contains(spans["VISIBLE"]):
            failures.append(f"{name}: visible text falls outside the bounds")
        if bounds.intersects(spans["OFFPAGE"]):
            failures.append(f"{name}: off-page text falls inside the bounds")
        doc.close()
    assert not failures, f"{len(failures)} failures, first five: {failures[:5]}"


def test_to_display_matrix_samples_the_true_colour_across_the_1024_case_matrix():
    failures = []
    for name, media, crop, unit, rot in matrix_cases(units=ALL_UNITS):
        doc = reopen(matrix_page(media, crop, unit, rot))
        page = doc[0]
        # (120, 70) sits well inside the band on every side (85 from the
        # left, 15 from the right, 12 from the top, 18 from the bottom) and
        # avoids the VISIBLE glyphs, which start at x=40 and sit on the
        # baseline near y=80.
        got = _pixel(page, (120, 70), to_display_matrix(page))
        if got != BAND_RGB:
            failures.append(f"{name}: sampled {got}")
        doc.close()
    assert not failures, f"{len(failures)} failures, first five: {failures[:5]}"


def test_to_display_matrix_equals_the_library_matrix_on_an_ordinary_page():
    # Pins that the new matrix is a strict correction: where PyMuPDF's own
    # matrix is right, ours must be identical to it.
    for rot in ROTATIONS:
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.set_rotation(rot)
        assert _near(tuple(to_display_matrix(page)), tuple(page.rotation_matrix)), rot
        doc.close()


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_at_rotation_zero_unrotates_the_page_then_restores_it(rotation):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.set_rotation(rotation)
    with at_rotation_zero(page):
        assert page.rotation == 0
    assert page.rotation == rotation
    doc.close()


def test_at_rotation_zero_restores_rotation_when_the_body_raises():
    # Review Focus 5: a failed draw must never leave the page re-oriented.
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.set_rotation(90)
    with pytest.raises(RuntimeError, match="boom"):
        with at_rotation_zero(page):
            raise RuntimeError("boom")
    assert page.rotation == 90
    doc.close()


from engine.geometry import (  # noqa: E402
    OTHER_DRAWING,
    TEXT_DRAWING,
    crop_origin_overhangs,
    drawing_refusal,
    page_transform,
)
from engine.operations import _erase_region  # noqa: E402
from tests.geometry_helpers import (  # noqa: E402
    box_page,
    broken_xref,
    drift_probe,
    find_span_bbox,
    standard,
    with_text,
)


@pytest.mark.parametrize(
    "keys, expected",
    [
        (dict(CropBox="[-40 0 612 792]"), True),       # left only
        (dict(CropBox="[0 0 612 830]"), True),         # top only
        (dict(CropBox="[-40 -60 660 820]"), True),     # all four
        (dict(CropBox="[0 -60 612 792]"), False),      # bottom only
        (dict(CropBox="[0 0 660 792]"), False),        # right only
        (dict(CropBox="[40 60 580 740]"), False),      # contained
        (dict(), False),                               # no CropBox at all
        # The false-positive trap for mediabox.contains(cropbox): it draws fine.
        (dict(MediaBox="[-100 -100 512 692]"), False),
    ],
    ids=["left", "top", "all-four", "bottom", "right", "contained", "none",
         "negative-origin-mediabox"],
)
def test_crop_origin_overhangs_matches_where_text_actually_drifts(keys, expected):
    doc, page = box_page(**keys)
    assert crop_origin_overhangs(page) is expected
    doc.close()


def test_crop_origin_overhangs_resolves_an_inherited_cropbox():
    doc, page = box_page(where="parent", CropBox="[-40 -60 660 820]")
    assert doc.xref_get_key(page.xref, "CropBox") == ("null", "null")
    assert crop_origin_overhangs(page) is True
    doc.close()


def test_crop_origin_overhangs_resolves_an_indirect_cropbox():
    doc, page = box_page(CropBox="[-40 -60 660 820]", indirect=("CropBox",))
    assert doc.xref_get_key(page.xref, "CropBox")[0] == "xref"
    assert crop_origin_overhangs(page) is True
    doc.close()


def test_crop_origin_overhangs_resolves_an_inherited_mediabox():
    # A distinct parent MediaBox, with a CropBox chosen so the answer flips
    # depending on which MediaBox is used: True against the parent's
    # [100 100 712 892] (crop.x0=50 < 100), False against the default
    # [0 0 612 792] a reader that failed to find the inherited box would
    # fall back to.
    doc, page = box_page(where="parent", MediaBox="[100 100 712 892]")
    assert doc.xref_get_key(page.xref, "MediaBox") == ("null", "null")
    doc.xref_set_key(page.xref, "CropBox", "[50 150 600 700]")
    page = doc.reload_page(page)
    assert crop_origin_overhangs(page) is True
    doc.close()


def test_crop_origin_overhangs_a_local_mediabox_overrides_the_inherited_one():
    # Same parent MediaBox and CropBox as above, but the page also sets its
    # own MediaBox back to the default -- the page's own box must win, so
    # the same CropBox that overhangs the parent's box no longer overhangs.
    doc, page = box_page(where="parent", MediaBox="[100 100 712 892]")
    assert doc.xref_get_key(page.xref, "MediaBox") == ("null", "null")
    doc.xref_set_key(page.xref, "MediaBox", "[0 0 612 792]")
    page = doc.reload_page(page)
    doc.xref_set_key(page.xref, "CropBox", "[50 150 600 700]")
    page = doc.reload_page(page)
    assert crop_origin_overhangs(page) is False
    doc.close()


def test_crop_origin_overhangs_resolves_a_grandparent_mediabox():
    # The box is set two levels up: a grandparent /Pages node, with nothing
    # on the parent or the page. Built by hand: a new /Pages dict, made the
    # parent's /Parent, with the parent as its sole /Kids entry.
    doc, page = box_page()
    parent = int(doc.xref_get_key(page.xref, "Parent")[1].split()[0])
    doc.xref_set_key(page.xref, "MediaBox", "null")
    grandparent = doc.get_new_xref()
    doc.update_object(grandparent, f"<< /Type /Pages /Kids [{parent} 0 R] /Count 1 >>")
    doc.xref_set_key(grandparent, "MediaBox", "[100 100 712 892]")
    doc.xref_set_key(parent, "Parent", f"{grandparent} 0 R")
    page = doc.reload_page(page)
    assert doc.xref_get_key(page.xref, "MediaBox") == ("null", "null")
    assert doc.xref_get_key(parent, "MediaBox") == ("null", "null")
    doc.xref_set_key(page.xref, "CropBox", "[50 150 600 700]")
    page = doc.reload_page(page)
    assert page.mediabox == fitz.Rect(100, 100, 712, 892)  # PyMuPDF agrees
    assert crop_origin_overhangs(page) is True
    doc.close()


def test_the_predicate_matches_observed_text_drift_on_all_256_unit_one_cases():
    # The predicate is only worth having if it agrees with what PyMuPDF
    # actually does. Draw a probe string on each configuration and compare.
    mismatches = []
    for name, media, crop, unit, rot in matrix_cases(units=(1,)):
        doc = matrix_page(media, crop, unit, rot)
        page = doc[0]
        predicted = crop_origin_overhangs(page)
        page.insert_text((100, 140), "PROBE", fontsize=10)
        drawn = reopen(doc)[0]
        origin = next(
            span["origin"] for block in drawn.get_text("dict")["blocks"] if "lines" in block
            for line in block["lines"] for span in line["spans"] if span["text"] == "PROBE"
        )
        drifted = abs(origin[0] - 100) > 0.01 or abs(origin[1] - 140) > 0.01
        if predicted != drifted:
            mismatches.append(f"{name}: predicted={predicted} drifted={drifted}")
    assert not mismatches, f"{len(mismatches)} mismatches: {mismatches[:5]}"


def test_a_plain_page_is_never_refused():
    doc, page = box_page()
    assert drawing_refusal(page, 0, TEXT_DRAWING) is None
    assert drawing_refusal(page, 0, OTHER_DRAWING) is None
    doc.close()


@pytest.mark.parametrize("kind", [TEXT_DRAWING, OTHER_DRAWING])
def test_user_unit_refuses_every_kind_with_the_owners_warning(kind):
    doc, page = box_page(UserUnit="1.5")
    reason = drawing_refusal(page, 3, kind)
    assert reason is not None
    assert "Page 3" in reason
    assert "/UserUnit" in reason and "1.5" in reason
    assert "nothing was changed" in reason
    assert "Support is planned" in reason
    doc.close()


def test_an_overhang_refuses_text_drawing_only():
    doc, page = box_page(CropBox="[-40 -60 660 820]")
    reason = drawing_refusal(page, 0, TEXT_DRAWING)
    assert reason is not None and "CropBox" in reason and "nothing was changed" in reason
    assert drawing_refusal(page, 0, OTHER_DRAWING) is None
    doc.close()


@pytest.mark.parametrize("where", ["page", "parent"])
@pytest.mark.parametrize("kind", [TEXT_DRAWING, OTHER_DRAWING])
def test_a_malformed_rotation_refuses_every_kind(kind, where):
    # Review Focus 4 / plan ruling P3.
    doc, page = box_page(where=where, Rotate="45")
    reason = drawing_refusal(page, 0, kind)
    assert reason is not None and "invalid rotation" in reason and "nothing was changed" in reason
    doc.close()


@pytest.mark.parametrize("raw", ["-90", "450", "-270", "360", "720"])
def test_un_normalised_but_valid_rotations_are_not_refused(raw):
    doc, page = box_page(Rotate=raw)
    assert drawing_refusal(page, 0, OTHER_DRAWING) is None
    doc.close()


# ---------------------------------------------------------------------------
# Fix round 1: I1 (indirect numbers bypassed the gate), I2 (a /Parent cycle
# hung), A1/A2 (Codex critic findings), and the Minor findings M2-M5.
# Fix round 2 (ruling C15) replaced the raw-key readers with PyMuPDF's own
# interpreted geometry (user_unit/rotation_is_valid). Fix round 3 (ruling C16)
# replaced those in turn with layout_orientation/page_transform, since
# page.transformation_matrix turned out to be a constant on rotated pages.
# These now exercise drawing_refusal end to end rather than a deleted
# function; see also Test A/B further down.
# ---------------------------------------------------------------------------


def test_an_indirect_user_unit_is_refused_and_matches_pymupdfs_scaling():
    doc, page = box_page(UserUnit="2", indirect=("UserUnit",))
    assert doc.xref_get_key(page.xref, "UserUnit")[0] == "xref"
    reason = drawing_refusal(page, 0, OTHER_DRAWING)
    assert reason is not None and "/UserUnit" in reason
    # The gate must agree with what PyMuPDF actually draws: it scales.
    assert page.rect == fitz.Rect(0, 0, 1224, 1584)
    doc.close()


@pytest.mark.parametrize("where", ["page", "parent"])
def test_an_indirect_rotate_45_refuses_every_kind(where):
    doc, page = box_page(where=where, Rotate="45", indirect=("Rotate",))
    if where == "parent":
        assert doc.xref_get_key(page.xref, "Rotate") == ("null", "null")
    for kind in (TEXT_DRAWING, OTHER_DRAWING):
        reason = drawing_refusal(page, 0, kind)
        assert reason is not None and "invalid rotation" in reason
    doc.close()


def test_an_indirect_rotate_90_is_not_refused():
    doc, page = box_page(Rotate="90", indirect=("Rotate",))
    assert page.rotation == 90  # PyMuPDF agrees this one is fine
    assert drawing_refusal(page, 0, OTHER_DRAWING) is None
    doc.close()


def test_the_rotation_check_runs_before_the_user_unit_check():
    doc, page = box_page(Rotate="45", UserUnit="2")
    reason = drawing_refusal(page, 0, OTHER_DRAWING)
    assert reason is not None
    assert "invalid rotation" in reason
    # Fix round 3: the invalid-rotation message itself now mentions
    # "/UserUnit" in passing (a negative /UserUnit shares the same malformed
    # transform as a bad rotation), so the check that matters is that this
    # is NOT the separate /UserUnit-scaling rule's message.
    assert "uses PDF /UserUnit scaling" not in reason
    doc.close()


def test_a_parent_cycle_does_not_hang():
    # I2: an unguarded /Parent walk hung forever on a cycle. Round 2/3 no
    # longer walk /Parent by hand at all (they read PyMuPDF's own
    # page.mediabox/page.cropbox/page transform), so the only way this can
    # still hang is inside PyMuPDF's own load/read. Measured (re-review 2,
    # Minor 4): on this exact construction -- a /Pages node whose own
    # /Parent points to itself -- PyMuPDF raises RuntimeError("cycle in
    # resources") from doc.reload_page. Pinned below instead of accepting
    # any outcome, since an assertion that can never fail once the thread
    # has terminated caught nothing.
    doc, page = box_page()  # no CropBox anywhere: forces resolution work
    parent = int(doc.xref_get_key(page.xref, "Parent")[1].split()[0])
    doc.xref_set_key(parent, "Parent", f"{parent} 0 R")
    result = {}

    def run():
        try:
            reloaded = doc.reload_page(page)
            result["overhangs"] = crop_origin_overhangs(reloaded)
        except Exception as exc:  # noqa: BLE001 -- any exception beats a hang
            result["error"] = repr(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert "cycle in resources" in result.get("error", "")
    doc.close()


def test_page_transform_returns_a_matrix_on_a_plain_page():
    # Pins the low-level mupdf API layout_orientation depends on: if PyMuPDF
    # ever stops exposing page._pdf_page()/pdf_page_transform, this test (and
    # every plain-page refusal test) goes red immediately, per the brief's
    # fail-closed design, rather than silently refusing every page in
    # production with no test noticing why.
    doc, page = box_page()
    matrix = page_transform(page)
    assert isinstance(matrix, fitz.Matrix)
    assert tuple(matrix) == (1, 0, 0, -1, 0, 792)
    doc.close()


def test_page_transform_fails_closed_when_the_real_binding_is_missing(monkeypatch):
    # The explicit getattr check (M-5), verified against the real attributes
    # rather than a stand-in: deleting either one must still return None
    # (fails closed), not raise.
    doc, page = box_page()
    monkeypatch.delattr(mupdf, "pdf_page_transform", raising=True)
    assert page_transform(page) is None
    doc.close()


def test_page_transform_fails_closed_when_pdf_page_is_missing(monkeypatch):
    doc, page = box_page()
    monkeypatch.delattr(fitz.Page, "_pdf_page", raising=True)
    assert page_transform(page) is None
    doc.close()


def test_page_transform_raises_on_a_non_page_argument():
    # M-5: page_transform used to catch AttributeError/TypeError broadly, so
    # a caller's own mistake (passing something that is not a fitz.Page) was
    # indistinguishable from the binding genuinely being missing, and
    # returned the same misleading None. It must now propagate instead --
    # the explicit getattr check above is what fails closed on a real
    # missing binding.
    with pytest.raises(AttributeError):
        page_transform(None)


# ---------------------------------------------------------------------------
# Fix round 2 (coordinator ruling C15): the readers were rewritten to decide
# from PyMuPDF's own interpreted geometry (page.rotation, page.rect,
# page.mediabox, page.cropbox) instead of re-parsing raw keys. Fix round 3
# (ruling C16) went one property further: page.transformation_matrix turned
# out to be a constant on rotated pages, not MuPDF's real page transform, so
# layout_orientation/page_transform read that transform directly instead. The
# binding principle stands throughout: every gate test must agree with what
# PyMuPDF draws, checked by drawing -- not by asserting the gate against our
# own parsing. Test A and Test B below are that check.
# ---------------------------------------------------------------------------


def test_the_matrix_agrees_with_pymupdfs_own_drawing():
    # Test A: every case of the 1,024-configuration matrix (all four units),
    # checked against a drawn-and-read-back probe, not against our own
    # parsing of the boxes that built it.
    start = time.perf_counter()
    mismatches = []
    for name, media, crop, unit, rot in matrix_cases(units=ALL_UNITS):
        doc = matrix_page(media, crop, unit, rot)
        pdf_bytes = doc.tobytes()
        doc.close()
        opened = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = opened[0]
        reason = drawing_refusal(page, 0, TEXT_DRAWING)
        if unit == 1:
            drifted, origin = drift_probe(pdf_bytes)
            if drifted:
                if reason is None or "CropBox" not in reason:
                    mismatches.append(f"{name}: expected overhang refusal, got {reason!r}")
            elif reason is not None:
                mismatches.append(f"{name}: expected None, got {reason!r}")
        else:
            if reason is None or f"{unit:g}" not in reason:
                mismatches.append(f"{name}: expected the /UserUnit {unit:g} message, got {reason!r}")
        opened.close()
    elapsed = time.perf_counter() - start
    print(f"\ntest_the_matrix_agrees_with_pymupdfs_own_drawing: {elapsed:.2f}s for "
          f"{4 * 16 * len(ALL_UNITS) * 4} cases")
    assert not mismatches, f"{len(mismatches)} mismatches ({elapsed:.2f}s): {mismatches[:5]}"


_LETTER = "/MediaBox [0 0 612 792]"


def _chain16():
    # obj4 -> obj5 -> ... -> obj18 -> obj19 = 2 (16 objects, 15 hops).
    return [f"{5 + i} 0 R" for i in range(15)] + ["2"]


_INF = "/MediaBox [-2147483648 -2147483648 2147483520 2147483520]"  # MuPDF's fz_infinite_rect


class _Spec(NamedTuple):
    """One Test B page, stored once so the redaction-placement test builds
    the same page with text on it (fix round 5, review Minor 4): the two
    tables can no longer drift apart, because there is only one."""

    page_extra: str = ""
    pages_extra: str = ""
    extra_objects: tuple = ()
    parent: str = "2 0 R"  # B2 and dangling-parent point /Parent elsewhere
    repaired: bool = False  # broken startxref: MuPDF repairs the file on open

    def _finish(self, pdf_bytes):
        return broken_xref(pdf_bytes) if self.repaired else pdf_bytes

    def standard(self):
        return self._finish(standard(self.page_extra, self.pages_extra, self.extra_objects, self.parent))

    def with_text(self):
        return self._finish(with_text(self.page_extra, self.pages_extra, self.extra_objects, self.parent))


# id, page spec, expected category: "-" allowed, "rot" invalid rotation,
# "unit" /UserUnit, "incons" inconsistent boxes, "over" overhang,
# "any" refused for any reason (the probe itself is unrenderable).
_ADVERSARIAL_TABLE = [
    ("rot45", _Spec(f"{_LETTER} /Rotate 45"), "rot"),
    ("rot-2.7e9", _Spec(f"{_LETTER} /Rotate 2700000000.0"), "rot"),
    ("rot-2^32+45", _Spec(f"{_LETTER} /Rotate 4294967341"), "rot"),
    ("rot-2^32+90", _Spec(f"{_LETTER} /Rotate 4294967386"), "-"),
    ("rot45-square", _Spec("/MediaBox [0 0 600 600] /Rotate 45"), "rot"),
    ("rot270-square", _Spec("/MediaBox [0 0 600 600] /Rotate 270"), "-"),
    ("rot-90", _Spec(f"{_LETTER} /Rotate -90"), "-"),
    ("rot450", _Spec(f"{_LETTER} /Rotate 450"), "-"),
    ("unit2", _Spec(f"{_LETTER} /UserUnit 2"), "unit"),
    ("unit-2^32+1", _Spec(f"{_LETTER} /UserUnit 4294967297"), "unit"),
    ("unit1.0000001", _Spec(f"{_LETTER} /UserUnit 1.0000001"), "-"),
    ("unit-indirect", _Spec(f"{_LETTER} /UserUnit 4 0 R", extra_objects=("2",)), "unit"),
    ("unit-chain16", _Spec(f"{_LETTER} /UserUnit 4 0 R", extra_objects=tuple(_chain16())), "-"),
    ("unit2-rot90", _Spec(f"{_LETTER} /UserUnit 2 /Rotate 90"), "unit"),
    ("unit2-square-rot90", _Spec("/MediaBox [0 0 600 600] /UserUnit 2 /Rotate 90"), "unit"),
    ("unit0.5", _Spec(f"{_LETTER} /UserUnit 0.5"), "unit"),
    # A negative /UserUnit is the same linear transform as a 180-degree turn
    # (fix round 3, ruling C16): MuPDF cannot tell them apart, so both share
    # the "invalid rotation" message.
    ("unit-1", _Spec(f"{_LETTER} /UserUnit -1"), "rot"),
    ("unit0", _Spec(f"{_LETTER} /UserUnit 0"), "any"),
    ("unit1e30", _Spec(f"{_LETTER} /UserUnit 1e30"), "-"),
    ("G1", _Spec(f"{_LETTER} /CropBox [4 0 R -60 660 820]", extra_objects=("-40",)), "over"),
    ("H1", _Spec(f"{_LETTER} /CropBox [-40 -60 660 820 0]"), "over"),
    ("H2", _Spec("/MediaBox [0 0 612 792 0] /CropBox [-40 -60 660 820]"), "over"),
    ("I1", _Spec("/MediaBox [0 0 612] /CropBox [-40 -60 660 820]"), "over"),
    ("I3", _Spec("/CropBox [-40 -60 660 820]"), "over"),
    ("I5", _Spec(f"{_LETTER} /CropBox [-40 -60 660]"), "incons"),
    ("N3", _Spec("/MediaBox [4 0 R 0 612 792] /CropBox [-40 0 612 792]", extra_objects=("0",)), "over"),
    ("J-null", _Spec(
        "/MediaBox 4 0 R /CropBox [-40 0 612 692]",
        pages_extra="/MediaBox [-100 -100 512 692]",
        extra_objects=("null",),
    ), "incons"),
    ("J2", _Spec(
        f"{_LETTER} /CropBox 4 0 R",
        pages_extra="/CropBox [-40 -60 660 820]",
        extra_objects=("null",),
    ), "-"),
    # /Parent must appear exactly once in the page dict, so B2 and
    # dangling-parent point it elsewhere through ``parent``.
    ("B2", _Spec(_LETTER, pages_extra="/CropBox [-40 -60 660 820]", extra_objects=("2 0 R",), parent="4 0 R"), "over"),
    ("dangling", _Spec(f"{_LETTER} /CropBox 99 0 R /UserUnit 99 0 R /Rotate 99 0 R"), "-"),
    ("dangling-parent", _Spec(_LETTER, parent="99 0 R"), "-"),
    ("negmedia-left", _Spec("/MediaBox [-100 -100 512 692] /CropBox [-140 0 512 692]"), "over"),
    ("negmedia-top", _Spec("/MediaBox [-100 -100 512 692] /CropBox [-100 -100 512 720]"), "over"),
    ("crop-empty", _Spec(f"{_LETTER} /CropBox [100 100 100 100]"), "-"),
    ("crop-outside", _Spec(f"{_LETTER} /CropBox [700 800 900 1000]"), "incons"),
    ("media-zero", _Spec("/MediaBox [0 0 0 0]"), "-"),
    ("crop-inverted", _Spec(f"{_LETTER} /CropBox [612 792 -40 -60]"), "over"),
    ("rot90-left", _Spec(f"{_LETTER} /Rotate 90 /CropBox [-40 0 612 792]"), "over"),
    ("rot180-top", _Spec(f"{_LETTER} /Rotate 180 /CropBox [0 0 612 830]"), "over"),
    # Fix round 3 (ruling C16): page.transformation_matrix is a constant on
    # rotated pages, so a negative /UserUnit combined with any valid rotation
    # (direct, indirect, with or without a CropBox) used to pass all four
    # round-2 rules -- these rows are that bypass, closed.
    ("unit-1-rot90", _Spec(f"{_LETTER} /UserUnit -1 /Rotate 90"), "rot"),
    ("unit-1-rot180", _Spec(f"{_LETTER} /UserUnit -1 /Rotate 180"), "rot"),
    ("unit-1-rot270", _Spec(f"{_LETTER} /UserUnit -1 /Rotate 270"), "rot"),
    ("unit-1-rot180-crop", _Spec(f"{_LETTER} /CropBox [50 50 500 700] /UserUnit -1 /Rotate 180"), "rot"),
    ("unit-1-indirect-rot90", _Spec(f"{_LETTER} /UserUnit 4 0 R /Rotate 90", extra_objects=("-1",)), "rot"),
    # MuPDF snaps a rotation in [135, 225) to 180; its ctm then has b=c=0,
    # so this needs the same linear-part-match check as unit-1, not a
    # separate "off-diagonal" test.
    ("rot135", _Spec(f"{_LETTER} /Rotate 135"), "rot"),
    ("rot-inherited-135", _Spec(_LETTER, pages_extra="/Rotate 135"), "rot"),
    # MuPDF replaces a box under 1pt wide/tall with the unit rect; page.cropbox
    # does not mirror that the way page.mediabox does.
    ("crop-tiny", _Spec(f"{_LETTER} /CropBox [100 100 100.5 100.5]"), "incons"),
    ("crop-tiny-unit0.5", _Spec(f"{_LETTER} /CropBox [100 100 100.5 100.5] /UserUnit 0.5"), "incons"),
    # 0.995pt is within the 0.01pt size tolerance of the unit rect MuPDF
    # swaps in, so only the sub-point check catches it; text drifts to
    # (200, 40.005) without that check.
    ("crop-0.995", _Spec(f"{_LETTER} /CropBox [100 100 100.995 100.995]"), "incons"),
    # Coordinate magnitude (fix round 5, ruling C18): PDF numbers are float32
    # inside MuPDF, and a fractional position drifts by half the float32
    # spacing -- 0.0125pt from 2^19 on, 0.3pt at 1e7 -- so the bound is 2^18.
    ("media-huge", _Spec("/MediaBox [0 0 1000000000 1000000000]"), "huge"),
    ("media-huge-1e7", _Spec("/MediaBox [0 0 10000000 10000000]"), "huge"),
    # The bound itself, both sides (re-review 4): a loosening to 2^19 or
    # 300000 otherwise passed every test.
    ("media-2^18", _Spec("/MediaBox [0 0 262144 792]"), "-"),
    ("media-2^18+1", _Spec("/MediaBox [0 0 262145 792]"), "huge"),
    ("media-2^20", _Spec("/MediaBox [0 0 1048576 792]"), "huge"),
    # Every box coordinate is within 2^24, but page space reaches 2^25:
    # get_text read VISIBLE back as "VISIBL E" here under the 2^24 bound.
    ("media-sym-2^24", _Spec("/MediaBox [-16777216 0 16777216 792]"), "huge"),
    ("rot315", _Spec(f"{_LETTER} /Rotate 315"), "-"),  # MuPDF snaps to 0, no drift
    ("unit-1.0000001-huge", _Spec("/MediaBox [0 0 100000 100000] /UserUnit 1.0000001"), "unit"),
    # MuPDF's infinite MediaBox in a file MuPDF repairs on open: page.mediabox,
    # page.cropbox and page.rect all fall back to letter size, but MuPDF's
    # transform carries e = f = 2^31 and nothing drawn can be read back. Only
    # the transform's e/f give it away. (Without the repair warning PyMuPDF's
    # page.rect raises IndexError instead, so the bare page cannot be a row.)
    ("media-inf-repaired", _Spec(_INF, repaired=True), "huge"),
    ("media-inf-repaired-rot90", _Spec(f"{_INF} /Rotate 90", repaired=True), "huge"),
    ("media-inf-inherited-repaired", _Spec(pages_extra=_INF, repaired=True), "huge"),
    # The same page with a letter CropBox is genuinely consistent: MuPDF lays
    # it out as the CropBox (transform (1,0,0,-1,0,792)), and it draws exactly.
    ("media-inf-crop-letter", _Spec(f"{_INF} /CropBox [0 0 612 792]", repaired=True), "-"),
    # MuPDF snaps /Rotate 135 to 180 and the negative /UserUnit mirrors it
    # back: the page is laid out exactly like a plain one and PyMuPDF reports
    # rotation 0. Correctly allowed -- pinned so nobody "fixes" it later.
    ("rot135-unit-1", _Spec(f"{_LETTER} /Rotate 135 /UserUnit -1"), "-"),
]

_CATEGORY_PHRASE = {
    "rot": "invalid rotation",
    "unit": "uses PDF /UserUnit",
    "incons": "lays out inconsistently",
    "over": "CropBox",
    "huge": "beyond",
}


@pytest.mark.parametrize(
    "case_id, spec, expected",
    _ADVERSARIAL_TABLE,
    ids=[row[0] for row in _ADVERSARIAL_TABLE],
)
def test_the_adversarial_table_agrees_with_pymupdfs_own_drawing(case_id, spec, expected):
    # Test B. Two things, per the coordinator's contract: the refusal
    # category (matched by message phrase), and agreement with the probe --
    # if the gate allows, the probe must show no drift; if the probe shows
    # drift, the gate must refuse, regardless of category.
    pdf_bytes = spec.standard()
    opened = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = opened[0]
    reason_text = drawing_refusal(page, 0, TEXT_DRAWING)
    reason_other = drawing_refusal(page, 0, OTHER_DRAWING)
    drifted, origin = drift_probe(pdf_bytes)
    opened.close()

    if expected == "any":
        assert reason_text is not None, f"{case_id}: expected some refusal, got None"
        assert drifted is None, f"{case_id}: expected an unrenderable probe, got {(drifted, origin)}"
        return

    if expected == "-":
        assert reason_text is None, f"{case_id}: expected allowed, got {reason_text!r}"
        assert reason_other is None, f"{case_id}: expected allowed for OTHER_DRAWING, got {reason_other!r}"
        assert drifted is False, f"{case_id}: gate allowed TEXT_DRAWING but the probe reported {(drifted, origin)}"
        return

    phrase = _CATEGORY_PHRASE[expected]
    assert reason_text is not None and phrase in reason_text, \
        f"{case_id}: expected a {expected!r} refusal, got {reason_text!r}"
    if expected == "over":
        assert reason_other is None, \
            f"{case_id}: an overhang must not refuse OTHER_DRAWING, got {reason_other!r}"
    else:
        assert reason_other is not None and phrase in reason_other, \
            f"{case_id}: a {expected!r} refusal must also refuse OTHER_DRAWING, got {reason_other!r}"

    # The mandatory bypass check, independent of category: a drifting probe
    # always means the gate must have refused TEXT_DRAWING.
    if drifted:
        assert reason_text is not None, \
            f"{case_id}: PyMuPDF drifted to {origin} but the gate allowed TEXT_DRAWING -- bypass"

    if case_id == "unit-1.0000001-huge":
        # The brief's table requires this message to "print more than (1)".
        # MuPDF's float32 rounding puts the actual scale at
        # 1.0000001192092896; {unit:.10g} prints it as "1.000000119", so the
        # message must not claim a scale of exactly 1.
        assert "scaling (1)" not in reason_text


# Fix round 3 (review item 4): for every Test B row that allows
# OTHER_DRAWING ("-" or "over"), assert where a redaction actually lands --
# not just that the gate agreed with a text-drift probe. Fix round 5: derived
# from _ADVERSARIAL_TABLE's own page specs, built through ``with_text`` so
# there is a span to redact, rather than hand-copied, so a row's page can no
# longer change in one table and not the other.
_REDACTION_ALLOWED_ROWS = [(row[0], row[1]) for row in _ADVERSARIAL_TABLE if row[2] in ("-", "over")]


@pytest.mark.parametrize(
    "case_id, spec",
    _REDACTION_ALLOWED_ROWS,
    ids=[row[0] for row in _REDACTION_ALLOWED_ROWS],
)
def test_redaction_lands_correctly_on_every_row_the_gate_allows_for_other_drawing(case_id, spec):
    # Review item 4: agreement-by-text-drift-probe alone missed the round-3
    # bypasses, because they misplaced a REDACTION's fill, not inserted text.
    # This draws a real span, confirms the gate still allows OTHER_DRAWING,
    # redacts through engine.operations._erase_region (wrapped in
    # at_rotation_zero, since Task 5 does not exist yet to do that itself),
    # and checks the fill lands within 0.01pt of the span it replaced (the
    # drift probe's tolerance; every measured offset is 0.0).
    pdf_bytes = spec.with_text()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    reason_other = drawing_refusal(page, 0, OTHER_DRAWING)
    assert reason_other is None, f"{case_id}: expected OTHER_DRAWING to be allowed, got {reason_other!r}"
    bbox = find_span_bbox(page, "VISIBLE")
    assert bbox is not None, f"{case_id}: could not find the VISIBLE span to redact"
    with at_rotation_zero(page):
        _erase_region(page, bbox, fill=(0, 1, 0))
    reopened = fitz.open(stream=doc.tobytes(), filetype="pdf")
    doc.close()
    page2 = reopened[0]
    assert find_span_bbox(page2, "VISIBLE") is None, f"{case_id}: text was not removed"
    # Only the green fill this test asked for counts, so a pre-existing fill
    # or a fill of the wrong colour cannot satisfy "exactly one".
    fills = [fitz.Rect(drawing["rect"]) for drawing in page2.get_drawings() if drawing.get("fill") == (0, 1, 0)]
    reopened.close()
    assert len(fills) == 1, f"{case_id}: expected exactly one fill, got {len(fills)}"
    fill = fills[0]
    offset = max(
        abs(fill.x0 - bbox.x0), abs(fill.y0 - bbox.y0),
        abs(fill.x1 - bbox.x1), abs(fill.y1 - bbox.y1),
    )
    assert offset <= 0.01, f"{case_id}: fill {tuple(fill)} is {offset:.2f}pt from bbox {tuple(bbox)}"


@pytest.mark.parametrize("offset", [261500, 2 ** 19 - 612, 2 ** 20])
def test_a_fractional_position_reads_back_within_tolerance_on_every_allowed_page(offset):
    # Fix round 5 (ruling C18). drift_probe writes at integer positions, which
    # float32 holds exactly; the editor's own positions are fractional, and
    # those round to half the float32 spacing. This page is 612pt wide and
    # offset so its far edge sits just under the 2^18 bound (262112pt), or at
    # 2^20. PROBE goes at page (511.7, 140.7), i.e. PDF x = offset + 511.7.
    # Measured (PyMuPDF 1.28.2): drift 0.0031pt at the 261500 offset (origin
    # x 511.7031), and 0.05pt at the 2^20 offset (origin x 511.75), where
    # this test's point is an exact float32 grid midpoint.
    # At the 2^19 - 612 offset it drifts 0.0125pt, which is why the bound is 2^18.
    pdf_bytes = standard(f"/MediaBox [{offset} 0 {offset + 612} 792]")
    opened = fitz.open(stream=pdf_bytes, filetype="pdf")
    reason_text = drawing_refusal(opened[0], 0, TEXT_DRAWING)
    reason_other = drawing_refusal(opened[0], 0, OTHER_DRAWING)
    opened.close()
    _, origin = drift_probe(pdf_bytes, (511.7, 140.7))
    assert origin is not None
    drift = max(abs(origin[0] - 511.7), abs(origin[1] - 140.7))
    if offset + 612 <= 2 ** 18:
        assert reason_text is None and reason_other is None, (reason_text, reason_other)
        assert drift <= 0.01, f"allowed page, but PROBE read back {drift:.4f}pt off at {origin}"
    else:
        assert drift > 0.01, f"expected measurable drift past the bound, got {drift:.4f}pt"
        for reason in (reason_text, reason_other):
            assert reason is not None and "beyond" in reason, reason
