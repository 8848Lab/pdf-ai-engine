import pymupdf as fitz
from engine.operations import redact_region
from tests.geometry_helpers import find_span_bbox
from tests.test_page_geometry import BLACK, CROPS, _fills, _inherited_rotation_page, _on, exported


def test_redaction_on_a_raw_inherited_rotation_page_keeps_the_effective_rotation():
    data = _inherited_rotation_page("90", cropbox=CROPS["contained"])
    probe = fitz.open(stream=data, filetype="pdf")
    target = find_span_bbox(probe[0], "LOW-MARKER")
    handle = fitz.open(stream=data, filetype="pdf")
    assert handle.xref_get_key(handle[0].xref, "Rotate") == ("null", "null")
    redact_region(handle, 0, tuple(target))
    out = exported(handle)[0]
    assert out.rotation == 90
    assert out.parent.xref_get_key(out.xref, "Rotate") == ("int", "90")
    fills = _fills(out, BLACK)
    assert len(fills) == 1 and _on(fills[0], target), f"fills {fills}, target {tuple(target)}"
    assert "LOW-MARKER" not in out.get_text()
