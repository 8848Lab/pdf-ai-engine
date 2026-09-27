"""Operation-level tests for Merge A: every existing operation on rotated,
cropped, fractional and /UserUnit pages.

Assertions are made on EXPORTED bytes re-parsed from scratch wherever the
claim is about the output, because this project's last three shipped bugs
were each invisible on the live handle.
"""
from pathlib import Path

import pymupdf as fitz
import pytest

import engine
import tests.geometry_helpers
from engine.export import export
from engine.operations import (
    delete_block,
    insert_block,
    move_block,
    redact_region,
    replace_image,
    replace_text,
)
from engine.parser import parse
from tests.geometry_helpers import ROTATIONS, build_page
from tests.image_helpers import solid_png

CHECKOUT = Path(__file__).resolve().parents[1]


def block(doc, marker):
    return next(b for b in doc.pages[0].text_blocks if marker in b.text)


def exported(handle):
    return fitz.open(stream=export(handle), filetype="pdf")


def text_spans(page):
    return [
        span
        for entry in page.get_text("dict")["blocks"] if "lines" in entry
        for line in entry["lines"]
        for span in line["spans"]
        if span["text"].strip()
    ]


def fingerprint(handle):
    """Structural identity of a document (plan ruling P5, strengthened by C2).

    Every xref object's text, every raw stream, and the page count. Never
    compare exported bytes to prove nothing changed: PyMuPDF regenerates the
    trailer /ID on every save, so two exports with no operation in between
    already differ.
    """
    parts = [handle.page_count]
    for xref in range(1, handle.xref_length()):
        parts.append((xref, handle.xref_object(xref, compressed=False)))
        if handle.xref_is_stream(xref):
            parts.append((xref, handle.xref_stream_raw(xref)))
    return parts


def test_imports_resolve_inside_this_checkout():
    # C12: an editable install of another checkout would shadow this one,
    # and every result below would then describe the wrong code.
    for module in (engine, tests.geometry_helpers):
        assert Path(module.__file__).resolve().is_relative_to(CHECKOUT), module.__file__


def test_fingerprint_is_stable_when_nothing_changes():
    doc, handle = parse(build_page())
    assert fingerprint(handle) == fingerprint(handle)


def test_fingerprint_detects_an_added_annotation():
    doc, handle = parse(build_page())
    before = fingerprint(handle)
    handle[0].add_redact_annot(fitz.Rect(10, 10, 20, 20))
    assert fingerprint(handle) != before


def test_fingerprint_detects_a_resource_change():
    doc, handle = parse(build_page())
    before = fingerprint(handle)
    handle[0].insert_font(fontname="probefont", fontbuffer=fitz.Font("helv").buffer)
    assert fingerprint(handle) != before


# Where each fixture geometry puts LOW-MARKER, as the parser reports it. Every
# later test targets the marker by its reported bbox, so these pin the
# fixtures themselves: a fixture change that moved the marker would otherwise
# silently stop a test from exercising its defect (C7).
FIXTURE_ORIGINS = {
    "plain": ({}, (72, 700), 12),
    "rotated-90": ({"rotation": 90}, (72, 700), 12),
    "contained-crop": ({"cropbox": "[40 60 580 740]"}, (32, 648), 12),
    "negative-origin-mediabox": ({"mediabox": "[-100 -100 512 692]"}, (172, 600), 12),
    "user-unit-1.5": ({"user_unit": 1.5}, (108, 1050), 18),
    "malformed-rotate-45": ({"rotate_raw": "45"}, (92, 72), 12),
}


@pytest.mark.parametrize("case", sorted(FIXTURE_ORIGINS))
def test_fixture_places_the_marker_where_the_tests_assume(case):
    kwargs, origin, size = FIXTURE_ORIGINS[case]
    doc, handle = parse(build_page(**kwargs))
    spans = [s for s in text_spans(handle[0]) if "LOW-MARKER" in s["text"]]
    assert len(spans) == 1
    assert spans[0]["origin"] == pytest.approx(origin, abs=0.01, rel=0)
    assert spans[0]["size"] == pytest.approx(size, abs=0.01, rel=0)


# LOW-MARKER sits at y~700 on a 792-high page -- below the 612 that a
# rotated page.rect reports as its height, which is what exposed D1.
LOW_OPS = {
    "redact_region": lambda h, b: redact_region(h, 0, b.bbox),
    "replace_text": lambda h, b: replace_text(h, 0, b, b.text),
    "delete_block": lambda h, b: delete_block(h, 0, b),
    "move_block": lambda h, b: move_block(h, 0, b, offset=(0, 20)),
    "insert_block": lambda h, b: insert_block(h, 0, (72, 740, 400, 760), "INSERTED", 12.0),
}


@pytest.mark.parametrize("rotation", ROTATIONS)
@pytest.mark.parametrize("op", sorted(LOW_OPS))
def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
    doc, handle = parse(build_page(rotation=rotation))
    LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_replace_image_accepts_an_image_low_on_the_page(rotation):
    # The sixth operation that validates a target (spec E1). No CropBox here,
    # so insert_image already lands correctly (spec F2); only D1 is in play.
    doc, handle = parse(build_page(rotation=rotation, texts=(), image_rect=(72, 700, 136, 764)))
    replace_image(handle, 0, doc.pages[0].images[0], solid_png(8, 8, (30, 30, 220)))


@pytest.mark.parametrize("rotation", (90, 270))
def test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected(rotation):
    # x=650 is inside a rotated page.rect (792 wide) but beyond the real,
    # unrotated page (612 wide). The old check accepted it.
    doc, handle = parse(build_page(rotation=rotation))
    with pytest.raises(ValueError, match="entirely off-page"):
        redact_region(handle, 0, (650, 100, 700, 120))


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_a_genuinely_off_page_bbox_is_still_rejected(rotation):
    doc, handle = parse(build_page(rotation=rotation))
    with pytest.raises(ValueError, match="entirely off-page"):
        redact_region(handle, 0, (700, 900, 760, 920))


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page(rotation):
    # Review Focus 2: redact_region uses intersects, not contains, so a bbox
    # overhanging the page's right edge (x=612) is still a valid target. At
    # 90/270 the old check compared it with the swapped rect (612 high), where
    # y=690 is already off-page, and rejected it.
    doc, handle = parse(build_page(rotation=rotation))
    redact_region(handle, 0, (580, 690, 640, 710))  # must not raise


def test_identical_replacement_low_on_a_rotated_page_keeps_its_size():
    # D3: the old growth cap used the rotated height (612), losing the
    # headroom a low block needs, so the replacement shrank. Every span of
    # the replacement is checked, not only the first.
    doc, handle = parse(build_page(rotation=90))
    b = block(doc, "LOW-MARKER")
    replace_text(handle, 0, b, b.text)
    spans = text_spans(exported(handle)[0])
    assert "LOW-MARKER" in "".join(s["text"] for s in spans)
    for span in spans:
        assert span["size"] == pytest.approx(b.size, abs=0.01, rel=0), span["text"]


def test_insert_block_fits_a_tight_box_low_on_a_rotated_page():
    # E2: insert_block has no shrink loop, so on the old code lost headroom
    # made it RAISE "does not fit" for text that fits unrotated.
    doc, handle = parse(build_page(rotation=90))
    b = block(doc, "LOW-MARKER")
    insert_block(handle, 0, (300, b.bbox[1], 560, b.bbox[3]), "FITS", b.size)
    assert "FITS" in exported(handle)[0].get_text()


@pytest.mark.parametrize("rotation", (90, 270))
def test_move_block_accepts_a_destination_low_on_a_rotated_page(rotation):
    # D4: masked by D1 on the old code, and would surface as soon as D1 was
    # fixed alone.
    doc, handle = parse(build_page(rotation=rotation, texts=((72, 100, "TOP-MARKER"),)))
    move_block(handle, 0, block(doc, "TOP-MARKER"), target_position=(72, 740))
    assert "TOP-MARKER" in exported(handle)[0].get_text()
