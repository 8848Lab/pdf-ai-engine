"""Merge B's web layer: the /api/pages/... routes, the pages summary, and the
block/image id behaviour around page operations and refusals (spec R9)."""
import pymupdf as fitz
import pytest

pytest.importorskip("fastapi", reason="webui tests need the `webui` extras group installed")

from fastapi.testclient import TestClient  # noqa: E402

from webui import session  # noqa: E402
from webui.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_session():
    session.reset()
    yield
    session.reset()


def _labelled(count) -> bytes:
    doc = fitz.open()
    for i in range(count):
        doc.new_page(width=612, height=792).insert_text((72, 100), f"P{i}", fontsize=12)
    return doc.tobytes()


def _upload(pdf_bytes) -> dict:
    response = client.post("/api/upload", files={"file": ("doc.pdf", pdf_bytes, "application/pdf")})
    assert response.status_code == 200, response.text
    return response.json()


def _texts_by_page(state):
    return [[b["text"] for b in state["blocks"] if b["page_index"] == p["index"]] for p in state["pages"]]


def test_the_pages_summary_reports_rotation():
    state = _upload(_labelled(2))
    assert [p["rotation"] for p in state["pages"]] == [0, 0]
    assert set(state["pages"][0]) == {"index", "width", "height", "rotation"}


def test_delete_route_removes_the_page():
    _upload(_labelled(3))
    state = client.post("/api/pages/delete", json={"page_index": 1}).json()
    assert _texts_by_page(state) == [["P0"], ["P2"]]


def test_move_route_uses_final_index_semantics():
    _upload(_labelled(4))
    state = client.post("/api/pages/move", json={"page_index": 0, "to_index": 3}).json()
    assert _texts_by_page(state) == [["P1"], ["P2"], ["P3"], ["P0"]]


def test_rotate_route_sets_an_absolute_rotation():
    _upload(_labelled(2))
    first = client.post("/api/pages/rotate", json={"page_index": 1, "rotation": 90}).json()
    # M5: rotating to 90 swaps the displayed size of that page.
    assert (first["pages"][1]["width"], first["pages"][1]["height"]) == (792, 612)
    state = client.post("/api/pages/rotate", json={"page_index": 1, "rotation": -90}).json()
    assert [p["rotation"] for p in state["pages"]] == [0, 270]


def test_insert_route_adds_a_blank_page_that_renders():
    _upload(_labelled(2))
    state = client.post("/api/pages/insert", json={"at_index": 1, "width": 300, "height": None}).json()
    assert _texts_by_page(state) == [["P0"], [], ["P1"]]
    assert (state["pages"][1]["width"], state["pages"][1]["height"]) == (300, 792)
    assert client.get("/api/page/1.png").status_code == 200


def test_insert_route_with_both_dimensions_explicit():
    # M4: both width and height given, neither defaulted from a neighbour.
    _upload(_labelled(2))
    state = client.post("/api/pages/insert", json={"at_index": 1, "width": 200, "height": 100}).json()
    assert (state["pages"][1]["width"], state["pages"][1]["height"]) == (200, 100)


def test_duplicate_route_inserts_the_copy_after_the_source():
    _upload(_labelled(2))
    state = client.post("/api/pages/duplicate", json={"page_index": 0}).json()
    assert _texts_by_page(state) == [["P0"], ["P0"], ["P1"]]


@pytest.mark.parametrize(
    "url, body, phrase",
    [
        ("/api/pages/delete", {"page_index": 5}, "out of range"),
        ("/api/pages/move", {"page_index": 0, "to_index": 9}, "out of range"),
        ("/api/pages/rotate", {"page_index": 0, "rotation": 45}, "multiple of 90"),
        ("/api/pages/insert", {"at_index": 0, "width": 0}, "between 1 and 14400"),
        ("/api/pages/duplicate", {"page_index": -1}, "out of range"),
    ],
)
def test_a_refused_page_operation_is_a_clean_400_and_keeps_every_id(url, body, phrase):
    before = _upload(_labelled(2))
    response = client.post(url, json=body)
    assert response.status_code == 400
    assert phrase in response.json()["error"]
    assert client.get("/api/state").json() == before  # same pages, same ids


def test_deleting_the_only_page_is_refused():
    _upload(_labelled(1))
    response = client.post("/api/pages/delete", json={"page_index": 0})
    assert response.status_code == 400
    assert "only page" in response.json()["error"]


def test_a_successful_page_operation_makes_every_old_block_id_stale():
    # R9 case 1: page indices shifted, so every id is reissued.
    before = _upload(_labelled(3))
    old_id = before["blocks"][2]["id"]  # P2, on a page that is not deleted
    client.post("/api/pages/delete", json={"page_index": 0})
    response = client.post("/api/redact", json={"block_id": old_id})
    assert response.status_code == 400
    assert "stale" in response.json()["error"]


# M2: every one of the five page routes reissues every block id on success,
# not just move.
_ALL_PAGE_ROUTES = [
    ("delete", "/api/pages/delete", {"page_index": 0}),
    ("move", "/api/pages/move", {"page_index": 0, "to_index": 1}),
    ("rotate", "/api/pages/rotate", {"page_index": 0, "rotation": 90}),
    ("insert", "/api/pages/insert", {"at_index": 0, "width": None, "height": None}),
    ("duplicate", "/api/pages/duplicate", {"page_index": 0}),
]


@pytest.mark.parametrize("name, url, body", _ALL_PAGE_ROUTES, ids=[c[0] for c in _ALL_PAGE_ROUTES])
def test_a_successful_page_operation_reissues_every_block_id(name, url, body):
    before = _upload(_labelled(3))
    after = client.post(url, json=body).json()
    assert {b["id"] for b in after["blocks"]}.isdisjoint({b["id"] for b in before["blocks"]})


# M3: each page route's response is exactly what /api/state reports afterwards.
@pytest.mark.parametrize("name, url, body", _ALL_PAGE_ROUTES, ids=[c[0] for c in _ALL_PAGE_ROUTES])
def test_a_page_routes_response_matches_the_state_it_leaves_behind(name, url, body):
    _upload(_labelled(3))
    response = client.post(url, json=body).json()
    assert response == client.get("/api/state").json()


def test_a_no_op_move_still_reissues_ids_like_any_successful_operation():
    # R9 case 3: pinned, not an endorsement -- a no-op is a success, and
    # every success refreshes. The document itself is unchanged.
    before = _upload(_labelled(2))
    after = client.post("/api/pages/move", json={"page_index": 1, "to_index": 1}).json()
    assert _texts_by_page(after) == _texts_by_page(before)
    assert {b["id"] for b in after["blocks"]}.isdisjoint({b["id"] for b in before["blocks"]})


def test_a_refused_block_operation_keeps_every_id_valid():
    # R9 case 2, and the Task 7 follow-up: a refusal before any mutation no
    # longer reissues ids, so the operator's next click still works.
    before = _upload(_labelled(1))
    block_id = before["blocks"][0]["id"]
    response = client.post(
        "/api/insert", json={"page_index": 0, "bbox": [900, 900, 950, 950], "text": "x", "size": 12}
    )
    assert response.status_code == 400
    assert client.get("/api/state").json() == before
    assert client.post("/api/redact", json={"block_id": block_id}).status_code == 200


def test_a_failure_after_a_mutation_still_refreshes_the_ids(monkeypatch):
    # D1 (plan 2026-09-28-replace-text-widen, ledgered): "new text does not
    # fit" used to be replace_text's one post-mutation failure, but R11
    # retires that -- it is now RefusedBeforeMutation, raised before any
    # erase, so it can no longer exercise "a failure after a mutation".
    # This test needs a different post-mutation failure to prove the ids
    # still refresh after one: the draw itself raising once the erase has
    # already happened, same as test_pages.py's "replace draw raises" guard
    # case. That failure is a plain ValueError, not a refusal, so the
    # registry must be re-read.
    before = _upload(_labelled(1))
    block_id = before["blocks"][0]["id"]

    def boom(*args, **kwargs):
        raise ZeroDivisionError("forced")

    monkeypatch.setattr(fitz.Page, "insert_textbox", boom)

    response = client.post("/api/replace", json={"block_id": block_id, "new_text": "hi"})
    assert response.status_code == 400
    after = client.get("/api/state").json()
    assert block_id not in {b["id"] for b in after["blocks"]}
    # Final review, fix round 3 (F5): the id-absence check above proves the
    # ids refreshed, but not specifically that the ERASE happened -- ids are
    # content-derived, so this could in principle hold even if the id
    # merely shifted for some other reason. Assert directly that the
    # original block's own text ("P0", from _labelled(1)) is gone from
    # state: the draw failed, but the erase that came before it did not,
    # and it is not undone.
    assert "P0" not in {b["text"] for b in after["blocks"]}


def test_a_page_rotated_through_the_api_accepts_every_block_operation_on_a_low_block():
    # The cross-merge case Merge A exists for: rotate, then edit a block in
    # the lower part of the original page.
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for y, text in ((650, "LOW-A"), (680, "LOW-B"), (710, "LOW-C"), (740, "LOW-D")):
        page.insert_text((72, y), text, fontsize=12)
    _upload(doc.tobytes())
    rotated = client.post("/api/pages/rotate", json={"page_index": 0, "rotation": 90}).json()
    # M1: the rotation itself is asserted, not just that block edits still work.
    assert rotated["pages"][0]["rotation"] == 90

    def block_id(text):
        state = client.get("/api/state").json()
        return next(b["id"] for b in state["blocks"] if b["text"] == text)

    assert client.post("/api/redact", json={"block_id": block_id("LOW-A")}).status_code == 200
    assert client.post("/api/replace", json={"block_id": block_id("LOW-B"), "new_text": "LOW-X"}).status_code == 200
    assert client.post("/api/delete", json={"block_id": block_id("LOW-C")}).status_code == 200
    assert client.post("/api/move", json={"block_id": block_id("LOW-D"), "offset": [0, 20]}).status_code == 200
    response = client.post(
        "/api/insert", json={"page_index": 0, "bbox": [72, 760, 300, 780], "text": "LOW-NEW", "size": 12}
    )
    assert response.status_code == 200
    texts = [b["text"] for b in response.json()["blocks"]]
    assert "LOW-A" not in texts and "LOW-C" not in texts
    assert {"LOW-X", "LOW-D", "LOW-NEW"} <= set(texts)

    # M1: re-parse the exported bytes from scratch and check both the text
    # and the rotation actually landed in the file, not just in the session.
    export_response = client.get("/api/export")
    assert export_response.status_code == 200
    exported = fitz.open(stream=export_response.content, filetype="pdf")
    page = exported[0]
    assert page.rotation == 90
    exported_texts = page.get_text()
    assert "LOW-A" not in exported_texts and "LOW-C" not in exported_texts
    assert "LOW-X" in exported_texts and "LOW-D" in exported_texts and "LOW-NEW" in exported_texts


def test_a_geometry_gate_refusal_keeps_every_id_valid():
    doc = fitz.open(stream=_labelled(1), filetype="pdf")
    doc.xref_set_key(doc[0].xref, "UserUnit", "1.5")
    before = _upload(doc.tobytes())
    response = client.post("/api/redact", json={"block_id": before["blocks"][0]["id"]})
    assert response.status_code == 400
    assert "Support is planned" in response.json()["error"]
    assert client.get("/api/state").json() == before


# M6 (ruling B10): the four page request models forbid unknown keys, so a
# typo such as "widht" is a clean 422 rather than a silently-ignored field.
@pytest.mark.parametrize(
    "url, body",
    [
        ("/api/pages/delete", {"page_index": 0, "extra_key": 1}),
        ("/api/pages/move", {"page_index": 0, "to_index": 1, "extra_key": 1}),
        ("/api/pages/rotate", {"page_index": 0, "rotation": 90, "extra_key": 1}),
        ("/api/pages/insert", {"at_index": 1, "widht": 300}),
        ("/api/pages/duplicate", {"page_index": 0, "extra_key": 1}),
    ],
    ids=["delete", "move", "rotate", "insert-typo", "duplicate"],
)
def test_an_unknown_field_on_a_page_route_is_a_422(url, body):
    _upload(_labelled(2))
    response = client.post(url, json=body)
    assert response.status_code == 422


def test_page_routes_still_coerce_lax_types():
    # B10: extra="forbid" must not disturb the existing lax type coercion
    # (e.g. an int where a float is expected).
    _upload(_labelled(2))
    response = client.post("/api/pages/rotate", json={"page_index": 0, "rotation": 90})
    assert response.status_code == 200


def test_an_unexpected_exception_is_a_json_500_not_an_html_traceback(monkeypatch):
    # M6: an exception that is neither ValueError nor LookupError (a real
    # bug, not a refusal) had no handler at all -- FastAPI/Starlette's
    # default is an HTML error page, which the frontend's JSON parser chokes
    # on ("Unexpected token 'I'..."). The generic Exception handler must
    # turn it into a JSON body instead, with raise_server_exceptions=False
    # so the TestClient reports the response rather than re-raising.
    _upload(_labelled(2))

    def _boom(page_index, rotation):
        raise RuntimeError("boom")

    monkeypatch.setattr(session, "rotate_page", _boom)
    from fastapi.testclient import TestClient as _TestClient
    from webui.main import app as _app

    local_client = _TestClient(_app, raise_server_exceptions=False)
    response = local_client.post("/api/pages/rotate", json={"page_index": 0, "rotation": 90})
    assert response.status_code == 500
    assert "RuntimeError: boom" in response.json()["error"]
