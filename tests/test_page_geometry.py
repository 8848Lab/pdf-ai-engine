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


from engine.geometry import to_display_matrix  # noqa: E402
from engine.operations import _sample_background_color  # noqa: E402
from tests.geometry_helpers import BAND, BAND_RGB  # noqa: E402

BAND_BEHIND_LOW = (60, 680, 400, 720)
SAMPLE_CROPS = {"plain": None, "contained": "[40 60 580 740]", "oversized": "[-40 -60 660 820]"}


def _centre_pixel(page, bbox):
    pix = page.get_pixmap()
    c = fitz.Point((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2) * to_display_matrix(page)
    return tuple(pix.pixel(int(c.x - pix.x), int(c.y - pix.y))[:3])


@pytest.mark.parametrize("crop", sorted(SAMPLE_CROPS))
@pytest.mark.parametrize("rotation", ROTATIONS)
def test_background_sample_reads_the_colour_behind_the_block(rotation, crop):
    # D2, tested on the sampler itself (C3). Through an erase, a contained or
    # oversized crop would also move the fill (R11, Task 5), and the old fill
    # landing elsewhere leaves the original band showing at the checked spot
    # -- a false green. Sampling alone is isolated here.
    doc, handle = parse(build_page(rotation=rotation, cropbox=SAMPLE_CROPS[crop], band=BAND_BEHIND_LOW))
    rect = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    rgb = tuple(round(c * 255) for c in _sample_background_color(handle[0], rect))
    assert rgb == BAND_RGB


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_delete_block_erases_to_the_true_background_colour(rotation):
    # End to end on a plain page only: with no CropBox the fill already lands
    # on target (R11 needs a crop), so a wrong colour here is sampling alone.
    doc, handle = parse(build_page(rotation=rotation, band=BAND_BEHIND_LOW))
    b = block(doc, "LOW-MARKER")
    delete_block(handle, 0, b)
    page = exported(handle)[0]
    assert "LOW-MARKER" not in page.get_text()
    r, g, bl = _centre_pixel(page, b.bbox)
    assert bl > 240 and r < 200, f"erased area is {(r, g, bl)}, expected the band {BAND_RGB}"


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_sampling_is_exact_on_a_fractional_size_page(rotation):
    # R3: a 100.1 x 800.1 page renders 101 x 801 pixels, so inferring scale
    # from raster size (1.008991) lands samples on the wrong pixels; the old
    # sampler also never rotates its points (D2), so every rotation fails.
    # The four sample points of rect (40, 700, 60, 720) are (50, 697),
    # (50, 723), (37, 710) and (63, 710). Each is the centre of a 2x2 band
    # patch, so under the identity render it falls on a pixel INSIDE the
    # patch; a sample that misses by a few pixels reads white.
    doc = fitz.open()
    page = doc.new_page(width=100.1, height=800.1)
    for x, y in ((50, 697), (50, 723), (37, 710), (63, 710)):
        page.draw_rect(fitz.Rect(x - 1, y - 1, x + 1, y + 1), color=None, fill=BAND)
    page.set_rotation(rotation)
    rgb = tuple(round(c * 255) for c in _sample_background_color(page, fitz.Rect(40, 700, 60, 720)))
    assert rgb == BAND_RGB
    doc.close()


from engine.operations import _erase_region  # noqa: E402

GREEN = (0.0, 1.0, 0.0)
BLACK = (0.0, 0.0, 0.0)
CROPS = {"contained": "[40 60 580 740]", "oversized": "[-40 -60 660 820]"}


def _same_colour(actual, expected, tolerance=0.01):
    # Drawing colours come back as floats that have been through a content
    # stream, and a sampled fill is a 0-255 value divided by 255 (C11).
    return (
        actual is not None
        and len(actual) == len(expected)
        and all(abs(a - e) <= tolerance for a, e in zip(actual, expected))
    )


def _fills(page, colour):
    return [fitz.Rect(d["rect"]) for d in page.get_drawings() if _same_colour(d.get("fill"), colour)]


def _on(rect, target):
    return all(abs(a - b) < 1 for a, b in zip(rect, target))


@pytest.mark.parametrize("crop", sorted(CROPS))
@pytest.mark.parametrize("rotation", ROTATIONS)
def test_erase_region_paints_exactly_one_fill_on_the_target(rotation, crop):
    # R11. Every _clean_erase caller and redact_region go through
    # _erase_region, so this pins all of them. Three separate properties,
    # all checked on the exported bytes: the text is gone, there is exactly
    # one fill, and that fill is on the target -- checking only the first
    # is how this defect was missed.
    doc, handle = parse(build_page(rotation=rotation, cropbox=CROPS[crop]))
    target = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    _erase_region(handle[0], target, fill=GREEN)
    page = exported(handle)[0]
    assert "LOW-MARKER" not in page.get_text()
    fills = _fills(page, GREEN)
    assert len(fills) == 1, f"expected one fill, got {fills}"
    assert _on(fills[0], target), f"fill painted at {tuple(fills[0])}, target was {tuple(target)}"
    assert handle[0].rotation == rotation


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_redact_region_black_box_lands_on_the_target(rotation):
    doc, handle = parse(build_page(rotation=rotation, cropbox=CROPS["oversized"]))
    target = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    redact_region(handle, 0, target)
    page = exported(handle)[0]
    fills = _fills(page, BLACK)
    assert "LOW-MARKER" not in page.get_text()
    assert len(fills) == 1 and _on(fills[0], target)


def _inherited_rotation_page(rotate, cropbox=None):
    """A page whose /Rotate is set only on its /Pages parent."""
    source = fitz.open()
    page = source.new_page(width=612, height=792)
    page.insert_text((72, 700), "LOW-MARKER", fontsize=12)
    if cropbox is not None:
        source.xref_set_key(page.xref, "CropBox", cropbox)
    parent = int(source.xref_get_key(page.xref, "Parent")[1].split()[0])
    source.xref_set_key(page.xref, "Rotate", "null")
    source.xref_set_key(parent, "Rotate", rotate)
    data = source.tobytes()
    source.close()
    return data


def test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation():
    # Review Focus 3, with a contained CropBox so the fill-placement defect
    # is actually exercised (C4: without a crop this test was already green).
    # at_rotation_zero writes a page-level /Rotate while drawing and restores
    # it, so the page may end with an explicit value where it had an
    # inherited one -- the effective rotation must be unchanged.
    doc, handle = parse(_inherited_rotation_page("90", cropbox=CROPS["contained"]))
    assert handle[0].rotation == 90
    target = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    redact_region(handle, 0, target)
    out = exported(handle)[0]
    fills = _fills(out, BLACK)
    assert out.rotation == 90
    assert len(fills) == 1 and _on(fills[0], target), f"fills {fills}, target {tuple(target)}"


@pytest.mark.parametrize("rotation", (90, 180, 270))
def test_both_redaction_calls_run_at_rotation_zero(rotation, monkeypatch):
    # R11 wraps BOTH calls. Only apply_redactions is known to need it, so
    # only a spy on each call can tell the wrapper was kept around both (C4).
    doc, handle = parse(build_page(rotation=rotation, cropbox=CROPS["contained"]))
    seen = {}
    real_add, real_apply = fitz.Page.add_redact_annot, fitz.Page.apply_redactions

    def spy_add(self, *args, **kwargs):
        seen["add_redact_annot"] = self.rotation
        return real_add(self, *args, **kwargs)

    def spy_apply(self, *args, **kwargs):
        seen["apply_redactions"] = self.rotation
        return real_apply(self, *args, **kwargs)

    monkeypatch.setattr(fitz.Page, "add_redact_annot", spy_add)
    monkeypatch.setattr(fitz.Page, "apply_redactions", spy_apply)
    redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)
    assert seen == {"add_redact_annot": 0, "apply_redactions": 0}
    assert handle[0].rotation == rotation


@pytest.mark.parametrize("failing", ["add_redact_annot", "apply_redactions"])
def test_rotation_is_restored_when_a_redaction_call_raises(failing, monkeypatch):
    # A guard, green before and after the fix: it fails only if the restore
    # is not in a finally.
    doc, handle = parse(build_page(rotation=90, cropbox=CROPS["contained"]))

    def boom(self, *args, **kwargs):
        raise RuntimeError("injected")

    monkeypatch.setattr(fitz.Page, failing, boom)
    with pytest.raises(RuntimeError, match="injected"):
        redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)
    assert handle[0].rotation == 90
