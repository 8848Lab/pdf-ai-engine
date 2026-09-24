from pathlib import Path

import pymupdf as fitz

from engine.export import export, snapshot
from engine.operations import replace_image
from engine.parser import parse
from tests.image_helpers import solid_png

FIXTURES = Path(__file__).parent / "fixtures"


def _object_graph(handle):
    """Every object in the document, by xref, with its stream if it has one.

    Compared instead of the serialized bytes because MuPDF regenerates the
    second half of the trailer's /ID on every save, so two consecutive
    tobytes() calls on an untouched document already differ -- verified.
    """
    return [
        (
            xref,
            handle.xref_object(xref, compressed=True),
            handle.xref_stream_raw(xref) if handle.xref_is_stream(xref) else None,
        )
        for xref in range(1, handle.xref_length())
    ]


def test_export_round_trips_to_a_valid_pdf():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")

    exported_bytes = export(handle)

    reopened = fitz.open(stream=exported_bytes, filetype="pdf")
    assert reopened.page_count == handle.page_count
    assert "REDACT-ME-12345" in reopened[0].get_text()
    reopened.close()
    handle.close()


def test_export_reflects_redaction_applied_before_export():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("REDACT-ME-12345")
    assert hits
    page.add_redact_annot(tuple(hits[0]), fill=(0, 0, 0))
    page.apply_redactions()

    exported_bytes = export(handle)

    reopened = fitz.open(stream=exported_bytes, filetype="pdf")
    assert "REDACT-ME-12345" not in reopened[0].get_text()
    reopened.close()
    handle.close()


def test_export_returns_nonempty_bytes():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")

    exported_bytes = export(handle)

    assert isinstance(exported_bytes, bytes)
    assert len(exported_bytes) > 0
    handle.close()


def test_export_produces_a_full_rewrite_not_an_incremental_save():
    # Exactly one %%EOF proves a single-generation, full rewrite. An
    # incremental save appends a new trailer/%%EOF while leaving prior
    # generations (including any pre-redaction content) physically present
    # in the file -- which would be a real security regression for a
    # redaction library. See the comment above export()'s tobytes() call.
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("REDACT-ME-12345")
    assert hits
    page.add_redact_annot(tuple(hits[0]), fill=(0, 0, 0))
    page.apply_redactions(images=2, graphics=1, text=0)

    exported_bytes = export(handle)

    assert exported_bytes.count(b"%%EOF") == 1
    handle.close()


def test_export_does_not_mutate_the_handle_it_serializes():
    # The C1 contract, pinned at its source. tobytes(garbage=N) with N >= 2
    # compacts and renumbers the LIVE document's object table in place, so
    # export() runs its garbage pass on a throwaway reopened copy. A caller
    # holding a session's handle must be able to export as often as it likes
    # without the handle changing underneath it.
    #
    # The image here is not incidental: a just-inserted image is exactly what
    # the in-place renumbering used to corrupt, leaving a dangling
    # /ColorSpace reference the next insert_image choked on.
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    replace_image(handle, 0, doc.pages[0].images[0], solid_png(64, 64, (30, 30, 220)))
    before = _object_graph(handle)

    for _ in range(5):
        export(handle)

    assert _object_graph(handle) == before
    handle.close()


def test_snapshot_does_not_garbage_collect_and_is_not_a_download_path():
    # snapshot() exists precisely because it does NOT collect, so this pins
    # the difference from export() in both directions: the orphan export()
    # reclaims is still present in a snapshot, which is why no path whose
    # bytes reach the operator may use it.
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    original_stream = handle.xref_stream_raw(doc.pages[0].images[0].xref)
    assert original_stream

    replace_image(handle, 0, doc.pages[0].images[0], solid_png(64, 64, (30, 30, 220)))

    assert original_stream in snapshot(handle), (
        "snapshot() is supposed to keep un-referenced objects -- if it starts "
        "collecting them it has become export() and must not be used on a live handle"
    )
    assert original_stream not in export(handle), (
        "export()'s garbage pass must still reclaim the replaced image's orphaned "
        "original, or the bitmap the operator replaced stays recoverable from the download"
    )
    handle.close()


def test_snapshot_does_not_mutate_the_handle_either():
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    replace_image(handle, 0, doc.pages[0].images[0], solid_png(64, 64, (30, 30, 220)))
    before = _object_graph(handle)

    for _ in range(5):
        snapshot(handle)

    assert _object_graph(handle) == before
    handle.close()
