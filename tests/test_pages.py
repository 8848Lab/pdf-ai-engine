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
from engine.pages import delete_page, insert_page, move_page, rotate_page
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
    assert "Nothing was changed" in str(caught.value) or "nothing was changed" in str(caught.value)
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


@pytest.mark.parametrize("src, final", [(-1, 0), (4, 0), (0, -1), (0, 4), (True, 0), (0, 1.0)])
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


@pytest.mark.parametrize("rotation", (45, 1, -30, 89, 90.0, 90.5, True, None, "90"))
def test_rotate_page_refuses_anything_but_a_whole_multiple_of_90(rotation):
    # PyMuPDF's own set_rotation(45) silently stores 0: only this check
    # stops "rotate by 45" becoming "reset to upright".
    _, handle = parse(labelled(1))
    rotate_page(handle, 0, 90)
    refused(handle, lambda: rotate_page(handle, 0, rotation))


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


@pytest.mark.parametrize("at_index", (-1, 3, None, 1.0))
def test_insert_page_refuses_an_out_of_range_index(at_index):
    _, handle = parse(labelled(2))
    refused(handle, lambda: insert_page(handle, at_index))


@pytest.mark.parametrize(
    "width, height",
    [(0, None), (-5, None), (0.5, None), (None, 14400.5), (float("nan"), None), (None, float("inf")), (True, None), ("200", None)],
)
def test_insert_page_refuses_bad_dimensions(width, height):
    _, handle = parse(labelled(2))
    refused(handle, lambda: insert_page(handle, 1, width=width, height=height))
