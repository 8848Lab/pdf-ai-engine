"""Merge B: the five page operations in engine/pages.py.

Claims about output are asserted on EXPORTED bytes re-parsed from scratch.
"Nothing was changed" is asserted on a structural fingerprint, never on
exported bytes: PyMuPDF regenerates the trailer /ID on every save.
"""
import itertools

import pymupdf as fitz
import pytest

from engine.errors import RefusedBeforeMutation
from engine.export import export
from engine.pages import delete_page, duplicate_page, insert_page, move_page, rotate_page
from engine.parser import parse
from tests.test_page_geometry import fingerprint


def labelled(count, size=(612, 792)) -> bytes:
    """A document whose page i reads "P{i}", so page order is checkable."""
    doc = fitz.open()
    for i in range(count):
        doc.new_page(width=size[0], height=size[1]).insert_text((72, 100), f"P{i}", fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def exported(handle):
    return fitz.open(stream=export(handle), filetype="pdf")


def order(handle):
    return [page.get_text().strip() for page in exported(handle)]


def refused(handle, call):
    """Assert `call` raises RefusedBeforeMutation and changes nothing."""
    before = fingerprint(handle)
    with pytest.raises(RefusedBeforeMutation) as caught:
        call()
    assert isinstance(caught.value, ValueError)
    assert "Nothing was changed." in str(caught.value)
    assert fingerprint(handle) == before
    return str(caught.value)


# ---- move_page ---------------------------------------------------------------


@pytest.mark.parametrize("src, final", list(itertools.product(range(4), range(4))))
def test_move_page_puts_the_page_at_its_final_index(src, final):
    _, handle = parse(labelled(4))
    move_page(handle, src, final)
    expected = [f"P{i}" for i in range(4)]
    expected.insert(final, expected.pop(src))
    assert order(handle) == expected


def test_move_page_to_its_own_index_is_a_no_op_not_an_error():
    _, handle = parse(labelled(3))
    before = fingerprint(handle)
    move_page(handle, 1, 1)
    assert fingerprint(handle) == before


@pytest.mark.parametrize(
    "src, final",
    [(-1, 0), (4, 0), (0, -1), (0, 4), (True, 0), (0, 1.0), (5, 5), (-1, -1), (True, True)],
)
def test_move_page_refuses_bad_indices(src, final):
    _, handle = parse(labelled(4))
    refused(handle, lambda: move_page(handle, src, final))


# ---- delete_page -------------------------------------------------------------


@pytest.mark.parametrize("index", range(3))
def test_delete_page_leaves_the_rest_in_order(index):
    _, handle = parse(labelled(3))
    delete_page(handle, index)
    assert order(handle) == [f"P{i}" for i in range(3) if i != index]


def test_delete_page_refuses_the_only_page():
    _, handle = parse(labelled(1))
    message = refused(handle, lambda: delete_page(handle, 0))
    assert "only page" in message


@pytest.mark.parametrize("index", (-1, 3, None, "0"))
def test_delete_page_refuses_a_bad_index(index):
    _, handle = parse(labelled(3))
    refused(handle, lambda: delete_page(handle, index))


# ---- rotate_page -------------------------------------------------------------


@pytest.mark.parametrize(
    "given, stored",
    [(0, 0), (90, 90), (180, 180), (270, 270), (-90, 270), (450, 90), (360, 0), (-360, 0), (720, 0)],
)
def test_rotate_page_is_absolute_and_normalised_and_survives_export(given, stored):
    _, handle = parse(labelled(2))
    rotate_page(handle, 0, 90)  # absolute: a second call replaces, never adds
    rotate_page(handle, 0, given)
    out = exported(handle)
    assert out[0].rotation == stored
    assert out[1].rotation == 0


@pytest.mark.parametrize("rotation", (45, 1, -30, 89, 90.0, 90.5, True, False, None, "90"))
def test_rotate_page_refuses_anything_but_a_whole_multiple_of_90(rotation):
    # PyMuPDF's own set_rotation(45) silently stores 0: only this check
    # stops "rotate by 45" becoming "reset to upright".
    _, handle = parse(labelled(1))
    rotate_page(handle, 0, 90)
    refused(handle, lambda: rotate_page(handle, 0, rotation))


@pytest.mark.parametrize("index", (-1, 3, True, None))
def test_rotate_page_refuses_a_bad_index(index):
    _, handle = parse(labelled(3))
    refused(handle, lambda: rotate_page(handle, index, 90))


def test_rotate_page_reduces_a_huge_multiple_of_90_before_calling_set_rotation(monkeypatch):
    # PyMuPDF's set_rotation loops `while r >= 360: r -= 360`, so a huge
    # multiple of 90 would hang forever without the `% 360` here. This spy
    # pins the ARGUMENT passed to set_rotation, so removing the `% 360`
    # fails this test instead of hanging it.
    seen = []
    original = fitz.Page.set_rotation

    def spy(self, rotation):
        seen.append(rotation)
        # Refuse to pass an unreduced value on: the real call would hang.
        assert 0 <= rotation < 360, f"set_rotation was given {rotation}, not a value in 0..359"
        return original(self, rotation)

    monkeypatch.setattr(fitz.Page, "set_rotation", spy)
    _, handle = parse(labelled(1))
    rotate_page(handle, 0, 90 * 2**64 + 90)
    assert seen[-1] == 90
    rotate_page(handle, 0, -90 * 2**64 - 90)
    assert seen[-1] == 270


def test_rotate_page_normalises_a_huge_multiple_of_90_and_survives_export():
    _, handle = parse(labelled(1))
    rotate_page(handle, 0, 90 * 2**64 + 90)
    assert exported(handle)[0].rotation == 90
    rotate_page(handle, 0, -90 * 2**64 - 90)
    assert exported(handle)[0].rotation == 270


# ---- insert_page -------------------------------------------------------------


def _size(page):
    return (round(page.rect.width, 3), round(page.rect.height, 3))


@pytest.mark.parametrize("at_index, expected", [(0, ["", "P0", "P1"]), (1, ["P0", "", "P1"]), (2, ["P0", "P1", ""])])
def test_insert_page_ends_at_the_requested_index(at_index, expected):
    _, handle = parse(labelled(2))
    insert_page(handle, at_index)
    assert order(handle) == expected


def test_insert_page_takes_a_non_letter_neighbours_size_not_a4():
    _, handle = parse(labelled(2, size=(333, 444)))
    insert_page(handle, 1)
    insert_page(handle, 3)  # append: the neighbour is the last page
    out = exported(handle)
    assert [_size(p) for p in out] == [(333, 444)] * 4
    assert out[1].rotation == 0 and out[3].rotation == 0


def test_insert_page_matches_a_rotated_neighbours_display_size():
    doc = fitz.open(stream=labelled(1), filetype="pdf")
    doc[0].set_rotation(90)
    _, handle = parse(doc.tobytes())
    insert_page(handle, 0)
    out = exported(handle)
    assert _size(out[0]) == (792, 612)  # landscape, as the neighbour is shown
    assert out[0].rotation == 0


def test_insert_page_matches_a_cropped_neighbours_display_size():
    doc = fitz.open(stream=labelled(1), filetype="pdf")
    doc[0].set_cropbox(fitz.Rect(50, 50, 400, 600))
    _, handle = parse(doc.tobytes())
    insert_page(handle, 1)
    assert _size(exported(handle)[1]) == (350, 550)


@pytest.mark.parametrize(
    "width, height, expected", [(200, None, (200, 792)), (None, 300, (612, 300)), (200, 300, (200, 300))]
)
def test_insert_page_defaults_each_dimension_independently(width, height, expected):
    _, handle = parse(labelled(1))
    insert_page(handle, 1, width=width, height=height)
    assert _size(exported(handle)[1]) == expected


@pytest.mark.parametrize("at_index", (-1, 3, None, 1.0, True))
def test_insert_page_refuses_an_out_of_range_index(at_index):
    _, handle = parse(labelled(2))
    refused(handle, lambda: insert_page(handle, at_index))


@pytest.mark.parametrize(
    "width, height",
    [
        (0, None), (-5, None), (0.5, None), (None, 14400.5), (float("nan"), None), (None, float("inf")),
        (True, None), ("200", None), (10**400, None), (-(10**400), None),
    ],
)
def test_insert_page_refuses_bad_dimensions(width, height):
    _, handle = parse(labelled(2))
    refused(handle, lambda: insert_page(handle, 1, width=width, height=height))


@pytest.mark.parametrize("width, height, expected", [(1, 1, (1, 1)), (14400, 14400, (14400, 14400))])
def test_insert_page_accepts_the_exact_bound_values(width, height, expected):
    _, handle = parse(labelled(2))
    insert_page(handle, 1, width=width, height=height)
    assert _size(exported(handle)[1]) == expected


def test_insert_page_refuses_just_past_the_upper_bound():
    _, handle = parse(labelled(2))
    refused(handle, lambda: insert_page(handle, 1, width=14400.0001, height=300))


def _zero_page_pdf() -> bytes:
    from tests.geometry_helpers import build

    return build([
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [] /Count 0 >>",
    ])


def test_insert_page_refuses_a_zero_page_document_without_an_explicit_size():
    # handle[-1] loops forever in PyMuPDF when page_count == 0, so the
    # neighbour must never be looked up before this refusal.
    _, handle = parse(_zero_page_pdf())
    assert handle.page_count == 0
    message = refused(handle, lambda: insert_page(handle, 0))
    assert "no pages" in message


def test_insert_page_with_both_dimensions_given_works_on_a_zero_page_document():
    _, handle = parse(_zero_page_pdf())
    insert_page(handle, 0, width=200, height=300)
    out = exported(handle)
    assert len(out) == 1
    assert _size(out[0]) == (200, 300)


def _wide_neighbour_pdf() -> bytes:
    doc = fitz.open(stream=labelled(1), filetype="pdf")
    doc.xref_set_key(doc[0].xref, "MediaBox", "[0 0 20000 792]")
    return doc.tobytes()


def test_insert_page_names_the_neighbours_dimension_when_it_is_out_of_range():
    _, handle = parse(_wide_neighbour_pdf())
    message = refused(handle, lambda: insert_page(handle, 1))
    assert "neighbouring page" in message
    assert "width" in message


@pytest.mark.parametrize(
    "width_a, height_a, width_b, height_b, at_index, expected",
    [
        (300, 400, 500, 600, 0, (300, 400)),
        (300, 400, 500, 600, 1, (500, 600)),
        (300, 400, 500, 600, 2, (500, 600)),
    ],
)
def test_insert_page_takes_the_size_of_the_correct_neighbour(width_a, height_a, width_b, height_b, at_index, expected):
    doc = fitz.open()
    doc.new_page(width=width_a, height=height_a).insert_text((10, 10), "P0")
    doc.new_page(width=width_b, height=height_b).insert_text((10, 10), "P1")
    _, handle = parse(doc.tobytes())
    insert_page(handle, at_index)
    assert _size(exported(handle)[at_index]) == expected


@pytest.mark.parametrize(
    "rotation, expected", [(90, (792, 612)), (180, (612, 792)), (270, (792, 612))]
)
def test_insert_page_matches_a_rotated_neighbours_display_size_at_every_angle(rotation, expected):
    doc = fitz.open(stream=labelled(1), filetype="pdf")
    doc[0].set_rotation(rotation)
    _, handle = parse(doc.tobytes())
    insert_page(handle, 0)
    out = exported(handle)
    assert _size(out[0]) == expected
    assert out[0].rotation == 0


# ---- duplicate_page ----------------------------------------------------------


@pytest.mark.parametrize("index, expected", [(0, ["P0", "P0", "P1", "P2"]), (1, ["P0", "P1", "P1", "P2"]), (2, ["P0", "P1", "P2", "P2"])])
def test_duplicate_page_inserts_the_copy_right_after_the_source(index, expected):
    _, handle = parse(labelled(3))
    duplicate_page(handle, index)
    assert order(handle) == expected


def test_duplicate_page_works_on_a_one_page_document():
    # fullcopy_page(0, 1) raises "bad page number(s)" here (spec R7).
    _, handle = parse(labelled(1))
    duplicate_page(handle, 0)
    assert order(handle) == ["P0", "P0"]


@pytest.mark.parametrize("index", (0, 1))
def test_redacting_the_duplicate_leaves_the_original_intact_in_the_exported_bytes(index):
    # F4: copy_page aliases the page object, so this redaction would also
    # remove the original's text, and that would survive export.
    _, handle = parse(labelled(2))
    duplicate_page(handle, index)
    copy = handle[index + 1]
    copy.add_redact_annot(copy.search_for(f"P{index}")[0])
    copy.apply_redactions()
    out = exported(handle)
    assert out[index].get_text().strip() == f"P{index}"
    assert out[index + 1].get_text().strip() == ""
    assert out[index].xref != out[index + 1].xref


@pytest.mark.parametrize("index", (-1, 2, None))
def test_duplicate_page_refuses_a_bad_index(index):
    _, handle = parse(labelled(2))
    refused(handle, lambda: duplicate_page(handle, index))


def test_the_original_stays_at_its_index_and_the_copy_is_the_new_object():
    # Pins "immediately after", which the order test cannot see when the
    # copy and the source read the same: a copy placed BEFORE the source
    # gives the same page labels.
    _, handle = parse(labelled(3))
    before = [handle[i].xref for i in range(3)]
    duplicate_page(handle, 1)
    after = [handle[i].xref for i in range(4)]
    assert after[1] == before[1]
    assert after[2] not in before
    assert [after[0], after[3]] == [before[0], before[2]]


# ---- inherited attributes (Resources, MediaBox, CropBox, Rotate) ------------


def _two_nodes_pdf() -> bytes:
    """Two /Pages nodes with different inherited Resources, MediaBox and
    Rotate, as a merge of two documents commonly produces. Node A (pages
    0, 1): portrait, upright, font F1=Helvetica. Node B (pages 2, 3): small
    landscape, Rotate 90, and F1 bound to a DIFFERENT font (Courier)."""
    from tests.geometry_helpers import build

    def stream(text, y):
        body = f"BT /F1 18 Tf 40 {y} Td ({text}) Tj ET"
        return f"<< /Length {len(body)} >>\nstream\n{body}\nendstream"

    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 4 >>",
        (
            "<< /Type /Pages /Parent 2 0 R /Kids [5 0 R 6 0 R] /Count 2 "
            "/Resources << /Font << /F1 9 0 R >> >> /MediaBox [0 0 400 600] /Rotate 0 >>"
        ),
        (
            "<< /Type /Pages /Parent 2 0 R /Kids [7 0 R 8 0 R] /Count 2 "
            "/Resources << /Font << /F1 10 0 R >> >> /MediaBox [0 0 300 200] /Rotate 90 >>"
        ),
        "<< /Type /Page /Parent 3 0 R /Contents 11 0 R >>",
        "<< /Type /Page /Parent 3 0 R /Contents 12 0 R >>",
        "<< /Type /Page /Parent 4 0 R /Contents 13 0 R >>",
        "<< /Type /Page /Parent 4 0 R /Contents 14 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        stream("A0", 500),
        stream("A1", 500),
        stream("B0", 150),
        stream("B1", 150),
    ]
    return build(objs)


def test_duplicate_page_keeps_the_sources_inherited_attributes_across_a_pages_node_boundary():
    # fullcopy_page files the copy under the FOLLOWING page's /Pages node.
    # Duplicating node A's last page (index 1) files the copy under node B,
    # whose Resources/MediaBox/Rotate differ: without pinning, the copy came
    # out blank, 300x200 and rotated.
    _, handle = parse(_two_nodes_pdf())
    duplicate_page(handle, 1)
    out = exported(handle)
    src, copy = out[1], out[2]
    assert copy.get_text().strip() == src.get_text().strip() == "A1"
    assert (copy.rect, copy.rotation) == (src.rect, src.rotation)
    assert [f[3] for f in copy.get_fonts()] == [f[3] for f in src.get_fonts()]


@pytest.mark.parametrize("src, final", [(1, 2), (2, 0), (3, 1)])
def test_move_page_keeps_the_movers_inherited_attributes_across_a_pages_node_boundary(src, final):
    before = exported(parse(_two_nodes_pdf())[1])[src]
    before_text = before.get_text().strip()
    before_rect, before_rotation = before.rect, before.rotation
    before_fonts = [f[3] for f in before.get_fonts()]
    _, handle = parse(_two_nodes_pdf())
    move_page(handle, src, final)
    after = exported(handle)[final]
    assert after.get_text().strip() == before_text
    assert (after.rect, after.rotation) == (before_rect, before_rotation)
    assert [f[3] for f in after.get_fonts()] == before_fonts


# ---- links (spec "Out of scope" pins, and R8) ----------------------------------


def _linked(source, target, count=3) -> bytes:
    doc = fitz.open(stream=labelled(count), filetype="pdf")
    doc[source].insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(72, 88, 120, 104), "page": target})
    return doc.tobytes()


def test_a_link_follows_its_target_page_when_pages_move():
    _, handle = parse(_linked(0, 2))
    move_page(handle, 2, 0)  # order becomes P2, P0, P1
    out = exported(handle)
    target = out[1].get_links()[0]["page"]
    assert out[target].get_text().strip() == "P2"


def test_deleting_a_links_target_removes_the_link_cleanly():
    _, handle = parse(_linked(0, 2))
    delete_page(handle, 2)
    assert exported(handle)[0].get_links() == []


def test_a_duplicated_self_link_still_targets_the_original_page():
    # R8: "independent" means independently editable; navigation is not
    # retargeted to the copy.
    _, handle = parse(_linked(0, 0, count=1))
    duplicate_page(handle, 0)
    out = exported(handle)
    assert [out[i].get_links()[0]["page"] for i in range(2)] == [0, 0]
