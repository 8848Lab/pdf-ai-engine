"""Unit tests for engine/geometry.py.

The two matrix tests are the critic's 1,024-configuration attack on R2. They
collect every failure and assert on the list, so one run reports all of them
rather than stopping at the first.
"""
import threading
import time

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
    user_unit,
)
from tests.geometry_helpers import box_page, build, drift_probe, standard  # noqa: E402


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
# interpreted geometry, so these now exercise drawing_refusal end to end
# rather than a deleted parser; see also Test A/B further down.
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
    assert page.rotation == 90  # PyMuPDF agrees this one is fine
    assert drawing_refusal(page, 0, OTHER_DRAWING) is None
    doc.close()


def test_the_rotation_check_runs_before_the_user_unit_check():
    doc, page = box_page(Rotate="45", UserUnit="2")
    reason = drawing_refusal(page, 0, OTHER_DRAWING)
    assert reason is not None
    assert "invalid rotation" in reason
    assert "/UserUnit" not in reason
    doc.close()


def test_a_parent_cycle_does_not_hang():
    # I2: an unguarded /Parent walk hung forever on a cycle. Round 2 no
    # longer walks /Parent by hand at all (it reads PyMuPDF's own
    # page.mediabox/page.cropbox), so this now pins the outcome at the
    # PyMuPDF layer: reload/read may itself raise on a self-referencing
    # /Parent, or it may succeed. Either is fine -- a hang is not.
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
    assert "overhangs" in result or "error" in result
    doc.close()


# ---------------------------------------------------------------------------
# Fix round 2 (coordinator ruling C15): the readers were rewritten to decide
# from PyMuPDF's own interpreted geometry (page.rotation, page.rect,
# page.mediabox, page.cropbox, page.transformation_matrix) instead of
# re-parsing raw keys. The binding principle stands: every gate test must
# agree with what PyMuPDF draws, checked by drawing -- not by asserting the
# gate against our own parsing. Test A and Test B below are that check.
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


def _adversarial_b2():
    # /Parent must appear exactly once in the page dict, so this needs
    # ``build`` directly rather than ``standard`` (which already writes
    # /Parent 2 0 R).
    return build([
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 /CropBox [-40 -60 660 820] >>",
        f"<< /Type /Page /Parent 4 0 R {_LETTER} >>",
        "2 0 R",
    ])


def _adversarial_dangling_parent():
    # Same reason as B2: /Parent must appear exactly once.
    return build([
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 99 0 R {_LETTER} >>",
    ])


# id, builder, expected category: "-" allowed, "rot" invalid rotation,
# "unit" /UserUnit, "incons" inconsistent boxes, "over" overhang,
# "any" refused for any reason (the probe itself is unrenderable).
_ADVERSARIAL_TABLE = [
    ("rot45", lambda: standard(f"{_LETTER} /Rotate 45"), "rot"),
    ("rot-2.7e9", lambda: standard(f"{_LETTER} /Rotate 2700000000.0"), "rot"),
    ("rot-2^32+45", lambda: standard(f"{_LETTER} /Rotate 4294967341"), "rot"),
    ("rot-2^32+90", lambda: standard(f"{_LETTER} /Rotate 4294967386"), "-"),
    ("rot45-square", lambda: standard("/MediaBox [0 0 600 600] /Rotate 45"), "rot"),
    ("rot270-square", lambda: standard("/MediaBox [0 0 600 600] /Rotate 270"), "-"),
    ("rot-90", lambda: standard(f"{_LETTER} /Rotate -90"), "-"),
    ("rot450", lambda: standard(f"{_LETTER} /Rotate 450"), "-"),
    ("unit2", lambda: standard(f"{_LETTER} /UserUnit 2"), "unit"),
    ("unit-2^32+1", lambda: standard(f"{_LETTER} /UserUnit 4294967297"), "unit"),
    ("unit1.0000001", lambda: standard(f"{_LETTER} /UserUnit 1.0000001"), "-"),
    ("unit-indirect", lambda: standard(f"{_LETTER} /UserUnit 4 0 R", extra_objects=["2"]), "unit"),
    ("unit-chain16", lambda: standard(f"{_LETTER} /UserUnit 4 0 R", extra_objects=_chain16()), "-"),
    ("unit2-rot90", lambda: standard(f"{_LETTER} /UserUnit 2 /Rotate 90"), "unit"),
    ("unit2-square-rot90", lambda: standard("/MediaBox [0 0 600 600] /UserUnit 2 /Rotate 90"), "unit"),
    ("unit0.5", lambda: standard(f"{_LETTER} /UserUnit 0.5"), "unit"),
    ("unit-1", lambda: standard(f"{_LETTER} /UserUnit -1"), "incons"),
    ("unit0", lambda: standard(f"{_LETTER} /UserUnit 0"), "any"),
    ("unit1e30", lambda: standard(f"{_LETTER} /UserUnit 1e30"), "-"),
    ("G1", lambda: standard(f"{_LETTER} /CropBox [4 0 R -60 660 820]", extra_objects=["-40"]), "over"),
    ("H1", lambda: standard(f"{_LETTER} /CropBox [-40 -60 660 820 0]"), "over"),
    ("H2", lambda: standard("/MediaBox [0 0 612 792 0] /CropBox [-40 -60 660 820]"), "over"),
    ("I1", lambda: standard("/MediaBox [0 0 612] /CropBox [-40 -60 660 820]"), "over"),
    ("I3", lambda: standard("/CropBox [-40 -60 660 820]"), "over"),
    ("I5", lambda: standard(f"{_LETTER} /CropBox [-40 -60 660]"), "incons"),
    ("N3", lambda: standard("/MediaBox [4 0 R 0 612 792] /CropBox [-40 0 612 792]", extra_objects=["0"]), "over"),
    ("J-null", lambda: standard(
        "/MediaBox 4 0 R /CropBox [-40 0 612 692]",
        pages_extra="/MediaBox [-100 -100 512 692]",
        extra_objects=["null"],
    ), "incons"),
    ("J2", lambda: standard(
        f"{_LETTER} /CropBox 4 0 R",
        pages_extra="/CropBox [-40 -60 660 820]",
        extra_objects=["null"],
    ), "-"),
    ("B2", _adversarial_b2, "over"),
    ("dangling", lambda: standard(f"{_LETTER} /CropBox 99 0 R /UserUnit 99 0 R /Rotate 99 0 R"), "-"),
    ("dangling-parent", _adversarial_dangling_parent, "-"),
    ("negmedia-left", lambda: standard("/MediaBox [-100 -100 512 692] /CropBox [-140 0 512 692]"), "over"),
    ("negmedia-top", lambda: standard("/MediaBox [-100 -100 512 692] /CropBox [-100 -100 512 720]"), "over"),
    ("crop-empty", lambda: standard(f"{_LETTER} /CropBox [100 100 100 100]"), "-"),
    ("crop-outside", lambda: standard(f"{_LETTER} /CropBox [700 800 900 1000]"), "incons"),
    ("media-zero", lambda: standard("/MediaBox [0 0 0 0]"), "-"),
    ("crop-inverted", lambda: standard(f"{_LETTER} /CropBox [612 792 -40 -60]"), "over"),
    ("rot90-left", lambda: standard(f"{_LETTER} /Rotate 90 /CropBox [-40 0 612 792]"), "over"),
    ("rot180-top", lambda: standard(f"{_LETTER} /Rotate 180 /CropBox [0 0 612 830]"), "over"),
]

_CATEGORY_PHRASE = {
    "rot": "invalid rotation",
    "unit": "uses PDF /UserUnit",
    "incons": "lays out inconsistently",
    "over": "CropBox",
}


@pytest.mark.parametrize(
    "case_id, builder, expected",
    _ADVERSARIAL_TABLE,
    ids=[row[0] for row in _ADVERSARIAL_TABLE],
)
def test_the_adversarial_table_agrees_with_pymupdfs_own_drawing(case_id, builder, expected):
    # Test B. Two things, per the coordinator's contract: the refusal
    # category (matched by message phrase), and agreement with the probe --
    # if the gate allows, the probe must show no drift; if the probe shows
    # drift, the gate must refuse, regardless of category.
    pdf_bytes = builder()
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


@pytest.mark.parametrize("row", _ADVERSARIAL_TABLE, ids=[row[0] for row in _ADVERSARIAL_TABLE])
def test_the_adversarial_table_categories_apply_to_other_drawing_too(row):
    # Explicit statement of the same rule the assertions above already
    # enforce inline, per the brief: "every non-over refusal applies to
    # OTHER_DRAWING too, and over does not."
    case_id, builder, expected = row
    if expected in ("any", "-", "over"):
        pytest.skip(f"{case_id}: covered directly above")
    pdf_bytes = builder()
    opened = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = opened[0]
    reason_other = drawing_refusal(page, 0, OTHER_DRAWING)
    opened.close()
    assert reason_other is not None, f"{case_id}: {expected!r} must refuse OTHER_DRAWING too"
