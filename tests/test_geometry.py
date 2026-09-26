"""Unit tests for engine/geometry.py.

The two matrix tests are the critic's 1,024-configuration attack on R2. They
collect every failure and assert on the list, so one run reports all of them
rather than stopping at the first.
"""
import threading

import pymupdf as fitz
import pytest

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
    raw_rotation,
    user_unit,
)
from tests.geometry_helpers import box_page, raw_object_page  # noqa: E402


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


@pytest.mark.parametrize(
    "keys, where, expected",
    [
        (dict(), "page", 1.0),
        (dict(UserUnit="1.5"), "page", 1.5),
        (dict(UserUnit="2"), "page", 2.0),
        # PyMuPDF ignores /UserUnit on /Pages, so the gate must too.
        (dict(UserUnit="1.5"), "parent", 1.0),
    ],
)
def test_user_unit_reads_the_page_level_value_only(keys, where, expected):
    doc, page = box_page(where=where, **keys)
    assert user_unit(page) == expected
    doc.close()


@pytest.mark.parametrize(
    "raw, where, expected",
    [("90", "page", 90.0), ("-90", "page", -90.0), ("45", "page", 45.0),
     ("90", "parent", 90.0), ("45", "parent", 45.0)],
)
def test_raw_rotation_reports_the_value_as_written(raw, where, expected):
    doc, page = box_page(where=where, Rotate=raw)
    assert raw_rotation(page) == expected
    doc.close()


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
# ---------------------------------------------------------------------------


def test_an_indirect_user_unit_is_read_refused_and_matches_pymupdfs_scaling():
    doc, page = box_page(UserUnit="2", indirect=("UserUnit",))
    assert doc.xref_get_key(page.xref, "UserUnit")[0] == "xref"
    assert user_unit(page) == 2.0
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
    assert raw_rotation(page) == 90.0
    assert page.rotation == 90  # PyMuPDF agrees this one is fine
    assert drawing_refusal(page, 0, OTHER_DRAWING) is None
    doc.close()


def test_a_two_level_chained_reference_resolves_to_the_final_value():
    # /UserUnit -> object 4 ("5 0 R") -> object 5 ("2"): resolved, not
    # defaulted. PyMuPDF's own page.rect confirms it scales by 2 too.
    doc, page = raw_object_page({"UserUnit": "4 0 R"}, ["5 0 R", "2"])
    assert user_unit(page) == 2.0
    assert page.rect == fitz.Rect(0, 0, 1224, 1584)
    doc.close()


def test_a_reference_cycle_resolves_to_null_and_terminates():
    # /Rotate -> object 4 ("5 0 R") -> object 5 ("4 0 R"): a cycle. Must
    # terminate (not hang) and fall back to the inheritance/default path,
    # matching PyMuPDF's own rotation, which also defaults to 0 here.
    doc, page = raw_object_page({"Rotate": "4 0 R"}, ["5 0 R", "4 0 R"])
    assert raw_rotation(page) == 0.0
    assert page.rotation == 0
    assert drawing_refusal(page, 0, OTHER_DRAWING) is None
    doc.close()


def test_an_indirect_null_continues_the_inheritance_walk_to_the_parent():
    doc, page = box_page(where="parent", CropBox="[-40 -60 660 820]")
    assert doc.xref_get_key(page.xref, "CropBox") == ("null", "null")
    # A fresh, never-updated xref defaults to content "null" without being
    # freed (freeing only happens if it is explicitly updated to "null").
    ref = doc.get_new_xref()
    doc.xref_set_key(page.xref, "CropBox", f"{ref} 0 R")
    page = doc.reload_page(page)
    assert doc.xref_get_key(page.xref, "CropBox")[0] == "xref"
    assert crop_origin_overhangs(page) is True
    doc.close()


def test_a_malformed_cropbox_array_is_treated_as_absent_matching_pymupdf():
    # Three entries instead of four.
    doc, page = box_page(CropBox="[0 0 612]")
    assert crop_origin_overhangs(page) is False
    # Confirm against PyMuPDF's own drawing: with clipping disabled, the
    # probe lands exactly where it was placed -- no drift.
    page.insert_text((100, 140), "PROBE", fontsize=10)
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP
    d = page.get_text("dict", clip=fitz.INFINITE_RECT(), flags=flags)
    origin = next(
        span["origin"] for block in d["blocks"] if "lines" in block
        for line in block["lines"] for span in line["spans"] if span["text"] == "PROBE"
    )
    assert origin == (100.0, 140.0)
    doc.close()


def test_a_non_numeric_rotate_defaults_to_zero_matching_pymupdf():
    doc, page = box_page(Rotate="/Foo")
    assert raw_rotation(page) == 0.0
    assert page.rotation == 0  # PyMuPDF also defaults a malformed /Rotate
    assert drawing_refusal(page, 0, OTHER_DRAWING) is None
    doc.close()


def test_a_non_numeric_user_unit_defaults_to_one_matching_pymupdf():
    doc, page = box_page(UserUnit="/Foo")
    assert user_unit(page) == 1.0
    assert page.rect == fitz.Rect(0, 0, 612, 792)  # PyMuPDF leaves it unscaled
    doc.close()


def test_the_rotation_check_runs_before_the_user_unit_check():
    doc, page = box_page(Rotate="45", UserUnit="2")
    reason = drawing_refusal(page, 0, OTHER_DRAWING)
    assert reason is not None
    assert "invalid rotation" in reason
    assert "/UserUnit" not in reason
    doc.close()


def test_a_parent_cycle_does_not_hang():
    # I2: an unguarded /Parent walk hangs forever on a cycle. Run it in a
    # daemon thread so a regression fails fast (and never blocks interpreter
    # exit) instead of hanging the whole suite.
    doc, page = box_page()  # no CropBox anywhere: forces the full /Parent walk
    parent = int(doc.xref_get_key(page.xref, "Parent")[1].split()[0])
    doc.xref_set_key(parent, "Parent", f"{parent} 0 R")
    page = doc.reload_page(page)
    result = {}

    def run():
        # Do NOT touch page.rect here: MuPDF raises on it for this page,
        # which would mask the hang this test exists to catch.
        result["overhangs"] = crop_origin_overhangs(page)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert result["overhangs"] is False
    doc.close()
