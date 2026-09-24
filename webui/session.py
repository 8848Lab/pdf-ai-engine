"""In-process session state: the current live PyMuPDF document handle and
the block and image registries built from its last parse.

A single module-level dict, not per-request/per-user state, is correct
here specifically because this tool is single-operator by design (see the
design spec's "Session and state handling" section) -- there is no
concurrent-session concern to design around.

Internal registry refresh reads the live handle through engine.export's
snapshot(), never export(): export()'s garbage-collection pass mutates the
document it runs against, and a refresh must not spend that pass on a
document the operator intends to keep editing. export_current() (the
download path) and sanitize_document() (which swaps the handle immediately
afterwards) are the deliberate exceptions -- they call export() for its
garbage=3 guarantees. See snapshot()'s and export()'s own docstrings.
"""
import contextlib

import pymupdf as fitz

from engine.document import Document
from engine.export import export, snapshot
from engine.operations import delete_block, insert_block, move_block
from engine.operations import get_metadata_summary as _get_metadata_summary
from engine.operations import redact_region, replace_text
from engine.operations import replace_image as _replace_image
from engine.operations import sanitize_document as _sanitize_document
from engine.parser import parse

_state: dict = {"handle": None, "blocks": [], "images": [], "next_block_id": 0}


def load_document(pdf_bytes: bytes) -> None:
    """Parse pdf_bytes, replacing any previously-loaded document.

    Parses BEFORE resetting the current session, so a bad/unparseable upload
    never destroys an in-progress document -- if parse() raises, nothing has
    been touched yet and the operator keeps whatever they were editing.
    """
    doc, handle = parse(pdf_bytes)
    reset()
    _state["handle"] = handle
    _state["blocks"], _state["images"] = _build_registries(doc)


@contextlib.contextmanager
def _registry_refreshed():
    """Re-derive the block/image registries around one engine operation,
    whether or not the operation succeeded, without ever masking what the
    operation itself raised.

    Why refresh on the failure path at all: engine operations can mutate the
    document and THEN raise (replace_text's documented "erase, then raise if
    it does not fit" contract; replace_image's insert_image failure after
    _clean_erase), and a registry left describing the pre-mutation document
    would show the operator blocks that no longer exist.

    Why this is not a plain `finally`, which is what it used to be: the
    refresh has to re-parse the document, and the very failures it exists to
    clean up after are the ones most likely to have left a document that
    cannot be re-parsed. A refresh raising inside a `finally` REPLACES the
    engine's own exception -- the operator gets an opaque MuPDF syntax error
    instead of "text does not fit", the route's ValueError handler never
    sees a ValueError so the response is a bare 500, and the registry is
    left exactly as stale as the `finally` existed to prevent. So on the
    failure path the refresh is best-effort and its own error is discarded
    in favour of the original; on the success path a refresh failure is a
    real fault with nothing to hide behind and propagates normally. Either
    way _refresh_state() clears the registries rather than leaving stale
    ones behind when it cannot rebuild them.

    Callers resolve their block/image id BEFORE entering this block: an
    unknown id means nothing was mutated and there is nothing to refresh.
    """
    try:
        yield
    except BaseException:
        with contextlib.suppress(Exception):
            _refresh_state()
        raise
    else:
        _refresh_state()


def redact(block_id: int) -> None:
    entry = get_block(block_id)
    with _registry_refreshed():
        redact_region(get_handle(), entry["page_index"], entry["block"].bbox)


def replace(block_id: int, new_text: str) -> None:
    entry = get_block(block_id)
    with _registry_refreshed():
        replace_text(get_handle(), entry["page_index"], entry["block"], new_text)


def delete(block_id: int) -> None:
    entry = get_block(block_id)
    with _registry_refreshed():
        delete_block(get_handle(), entry["page_index"], entry["block"])


def move(
    block_id: int,
    destination_page_index: int | None = None,
    target_position: tuple[float, float] | None = None,
    offset: tuple[float, float] | None = None,
) -> None:
    entry = get_block(block_id)
    with _registry_refreshed():
        move_block(
            get_handle(),
            entry["page_index"],
            entry["block"],
            destination_page_index=destination_page_index,
            target_position=target_position,
            offset=offset,
        )


def insert(
    page_index: int,
    bbox: tuple[float, float, float, float],
    text: str,
    size: float,
    font: str | None = None,
) -> None:
    handle = get_handle()
    with _registry_refreshed():
        insert_block(handle, page_index, bbox, text, size, font=font)


def replace_image(image_id: int, new_image_bytes: bytes) -> None:
    entry = get_image(image_id)
    with _registry_refreshed():
        _replace_image(get_handle(), entry["page_index"], entry["image"], new_image_bytes)


def sanitize_document() -> dict:
    handle = get_handle()
    try:
        result = _sanitize_document(handle)
    finally:
        # scrub() mutates the document's underlying PDF object structure
        # even though it never touches visible text content -- BOTH
        # registries (blocks and images) are re-derived unconditionally,
        # same as redact()/replace() above, rather than assuming this
        # particular operation couldn't have shifted anything. Unlike
        # redact/replace which only affect visible content, sanitize
        # modifies metadata which needs a fresh parse to fully apply the
        # removal, so we update the handle as well as the registries.
        #
        # This is the one place that legitimately calls export() rather than
        # snapshot(): the whole point is to leave the session holding a
        # document from which the un-referenced Info dictionary is
        # physically gone, which is exactly export()'s garbage pass. The
        # live handle it reads is replaced immediately afterwards, so the
        # non-mutation concern that governs _refresh_state() does not apply
        # here -- and export() no longer mutates its argument regardless.
        old_handle = get_handle()
        doc, new_handle = parse(export(old_handle))
        if old_handle is not None:
            old_handle.close()
        _state["handle"] = new_handle
        _state["blocks"], _state["images"] = _build_registries(doc)
    return result


def get_metadata_summary() -> dict:
    return _get_metadata_summary(get_handle())


def export_current() -> bytes:
    return export(get_handle())


def _refresh_state() -> None:
    # Re-derive the Document projection from the handle's CURRENT state via
    # its serialized bytes, since parse() is the only way to get a fresh
    # TextBlock/Image list -- the handle itself has no "give me a Document"
    # method. The re-parsed handle this produces is a throwaway: the real
    # handle we keep mutating stays _state["handle"], never this one, which
    # is closed immediately so it doesn't leak across many edits in one
    # session.
    #
    # snapshot(), NOT export(): this runs after EVERY operation on the live
    # handle, and export()'s garbage=3 pass used to compact and renumber
    # that handle's object table in place, corrupting the image the previous
    # replace_image had just inserted so the next one broke the document.
    # Nothing here needs garbage collection -- these bytes are parsed once
    # for their block/image list and discarded, never written to a file.
    handle = get_handle()
    try:
        doc, throwaway_handle = parse(snapshot(handle))
    except Exception:
        # The document cannot be re-parsed, so there is no honest registry
        # to publish. Keeping the pre-operation one would hand the operator
        # ids for content that may no longer exist -- precisely what
        # refreshing exists to prevent -- so clear both registries instead
        # and let the caller decide what to do with the failure.
        _state["blocks"], _state["images"] = [], []
        raise
    throwaway_handle.close()
    _state["blocks"], _state["images"] = _build_registries(doc)


def _build_registries(doc: Document) -> tuple[list[dict], list[dict]]:
    # Ids are drawn from a monotonically increasing counter that only resets
    # when the document is fully replaced, NOT from the entry's position in
    # its registry. Positional ids would be silently reassigned on every
    # refresh, so a stale id held by the frontend (e.g. a double-clicked
    # button firing twice) would resolve to a DIFFERENT surviving entry and
    # destroy it. With monotonic ids a stale id simply no longer exists, and
    # get_block()/get_image() raise the LookupError they were always meant to.
    #
    # Blocks and images share ONE counter, so an id is unambiguous across
    # both registries: a stale image id can never resolve to a block, or the
    # reverse.
    blocks, images = [], []
    for page in doc.pages:
        for block in page.text_blocks:
            blocks.append(
                {"id": _state["next_block_id"], "page_index": page.index, "block": block}
            )
            _state["next_block_id"] += 1
        for image in page.images:
            images.append(
                {"id": _state["next_block_id"], "page_index": page.index, "image": image}
            )
            _state["next_block_id"] += 1
    return blocks, images


def get_handle() -> fitz.Document:
    if _state["handle"] is None:
        raise LookupError("no document loaded -- POST a PDF to /api/upload first")
    return _state["handle"]


def get_block(block_id: int) -> dict:
    for entry in _state["blocks"]:
        if entry["id"] == block_id:
            return entry
    raise LookupError(
        f"no block with id {block_id} in the current document -- it may be stale after an edit"
    )


def get_blocks_summary() -> list[dict]:
    return [
        {
            "id": entry["id"],
            "page_index": entry["page_index"],
            "text": entry["block"].text,
            "font": entry["block"].font,
            "size": entry["block"].size,
        }
        for entry in _state["blocks"]
    ]


def get_image(image_id: int) -> dict:
    for entry in _state["images"]:
        if entry["id"] == image_id:
            return entry
    raise LookupError(
        f"no image with id {image_id} in the current document -- it may be stale after an edit"
    )


def get_images_summary() -> list[dict]:
    return [
        {
            "id": entry["id"],
            "page_index": entry["page_index"],
            "bbox": list(entry["image"].bbox),
            "width": entry["image"].width,
            "height": entry["image"].height,
            "placement_count": entry["image"].placement_count,
            "document_placement_count": entry["image"].document_placement_count,
            "document_page_count": entry["image"].document_page_count,
        }
        for entry in _state["images"]
    ]


def get_pages_summary() -> list[dict]:
    handle = get_handle()
    return [
        {"index": i, "width": handle[i].rect.width, "height": handle[i].rect.height}
        for i in range(handle.page_count)
    ]


def reset() -> None:
    if _state["handle"] is not None:
        _state["handle"].close()
    _state["handle"] = None
    _state["blocks"] = []
    _state["images"] = []
    _state["next_block_id"] = 0
