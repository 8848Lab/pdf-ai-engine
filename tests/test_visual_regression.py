"""End-to-end proof that redact_region -> export produces a PDF satisfying
all three properties the design spec requires: visual (only the target
region's pixels changed), content (redacted text is unextractable, not
just visually covered), and structural (the document stays valid and
untouched pages are byte-for-byte unchanged). No single property alone is
sufficient proof -- see the spec's "Testing strategy" section.
"""
from pathlib import Path

import pymupdf as fitz

from engine.export import export
from engine.operations import redact_region
from engine.parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


def _pixmap_pixels(page: fitz.Page) -> tuple[int, int, bytes]:
    pixmap = page.get_pixmap()
    return pixmap.width, pixmap.height, pixmap.samples


def test_redaction_only_changes_pixels_inside_the_target_region():
    original_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    original_handle = fitz.open(stream=original_bytes, filetype="pdf")
    original_page = original_handle[0]
    hits = original_page.search_for("REDACT-ME-12345")
    assert hits
    bbox = fitz.Rect(hits[0])

    _, handle = parse(original_bytes)
    redact_region(handle, page_index=0, bbox=tuple(bbox))
    redacted_bytes = export(handle)
    handle.close()

    redacted_handle = fitz.open(stream=redacted_bytes, filetype="pdf")
    redacted_page = redacted_handle[0]

    ow, oh, original_samples = _pixmap_pixels(original_page)
    rw, rh, redacted_samples = _pixmap_pixels(redacted_page)
    assert (ow, oh) == (rw, rh)

    zoom = original_page.get_pixmap().width / original_page.rect.width
    n_components = len(original_samples) // (ow * oh)

    # PyMuPDF's apply_redactions() renders the fill rectangle via a fill+stroke
    # ("B") content-stream operator at the PDF default 1pt line width -- there
    # is no public API to request fill-only (add_redact_annot/Annot.set_border
    # both reject it for Redact annotations), so a ~0.5pt halo bleeds outward
    # on anti-aliased edges. This tolerance absorbs that known, benign halo;
    # any pixel inside it is required to have gotten strictly darker (never
    # lighter), proving the halo only adds redaction coverage and never
    # exposes content.
    STROKE_HALO_TOLERANCE_PT = 1.0
    tolerant_bbox = fitz.Rect(
        bbox.x0 - STROKE_HALO_TOLERANCE_PT,
        bbox.y0 - STROKE_HALO_TOLERANCE_PT,
        bbox.x1 + STROKE_HALO_TOLERANCE_PT,
        bbox.y1 + STROKE_HALO_TOLERANCE_PT,
    )

    changed_inside_bbox = False
    changed_outside_bbox = False
    for y in range(oh):
        for x in range(ow):
            idx = (y * ow + x) * n_components
            pixel_original = original_samples[idx : idx + n_components]
            pixel_redacted = redacted_samples[idx : idx + n_components]
            if pixel_original == pixel_redacted:
                continue
            # Sample the pixel's CENTER in point-space, not its top-left
            # corner -- see the "center-sampling" note above.
            px_pt, py_pt = (x + 0.5) / zoom, (y + 0.5) / zoom
            if bbox.x0 <= px_pt <= bbox.x1 and bbox.y0 <= py_pt <= bbox.y1:
                changed_inside_bbox = True
            elif tolerant_bbox.x0 <= px_pt <= tolerant_bbox.x1 and tolerant_bbox.y0 <= py_pt <= tolerant_bbox.y1:
                assert sum(pixel_redacted) <= sum(pixel_original), (
                    f"pixel at ({x},{y}) is in the known stroke-halo tolerance "
                    f"band but got LIGHTER, not darker -- this would mean the "
                    f"redaction is damaging nearby content rather than merely "
                    f"bleeding slightly darker at its own edge"
                )
            else:
                changed_outside_bbox = True

    assert changed_inside_bbox, "redaction should visibly change the target region"
    assert not changed_outside_bbox, (
        "redaction must not touch pixels outside the target region and its "
        "known ~1pt stroke-halo tolerance"
    )

    original_handle.close()
    redacted_handle.close()


def test_redacted_text_is_unextractable_not_just_visually_covered():
    original_bytes = (FIXTURES / "mixed.pdf").read_bytes()
    _, handle = parse(original_bytes)
    page = handle[0]
    hits = page.search_for("PATIENT-0042")
    assert hits

    redact_region(handle, page_index=0, bbox=tuple(hits[0]))
    redacted_bytes = export(handle)
    handle.close()

    reopened = fitz.open(stream=redacted_bytes, filetype="pdf")
    assert "PATIENT-0042" not in reopened[0].get_text()
    reopened.close()


def test_redacted_document_stays_valid_and_other_pages_are_untouched():
    original_bytes = (FIXTURES / "multi_page.pdf").read_bytes()
    original_handle = fitz.open(stream=original_bytes, filetype="pdf")
    original_page_count = original_handle.page_count
    original_page1_text = original_handle[1].get_text()
    original_page2_text = original_handle[2].get_text()
    original_page1_pixels = _pixmap_pixels(original_handle[1])
    original_page2_pixels = _pixmap_pixels(original_handle[2])

    _, handle = parse(original_bytes)
    page0 = handle[0]
    hits = page0.search_for("PAGE-MARK-1")
    assert hits
    redact_region(handle, page_index=0, bbox=tuple(hits[0]))
    redacted_bytes = export(handle)
    handle.close()

    reopened = fitz.open(stream=redacted_bytes, filetype="pdf")
    assert reopened.page_count == original_page_count
    assert reopened[1].get_text() == original_page1_text
    assert reopened[2].get_text() == original_page2_text
    assert _pixmap_pixels(reopened[1]) == original_page1_pixels
    assert _pixmap_pixels(reopened[2]) == original_page2_pixels

    reopened.close()
    original_handle.close()
