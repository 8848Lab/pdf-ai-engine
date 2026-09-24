"""In-process session state: the current live PyMuPDF document handle and
the block registry built from its last parse.

A single module-level dict, not per-request/per-user state, is correct
here specifically because this tool is single-operator by design (see the
design spec's "Session and state handling" section) -- there is no
concurrent-session concern to design around.
"""
import pymupdf as fitz

from engine.document import Document
from engine.export import export
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


def redact(block_id: int) -> None:
    entry = get_block(block_id)
    # get_block() runs BEFORE the try: if the id is unknown, nothing has been
    # mutated and there is nothing to refresh. Once the operation starts, the
    # registry must be re-derived whether or not it succeeded -- engine
    # operations can mutate the document and THEN raise (see replace_text's
    # documented "erase, then raise if it does not fit" contract), and a
    # registry left describing the pre-mutation document would show the
    # operator blocks that no longer exist.
    try:
        redact_region(get_handle(), entry["page_index"], entry["block"].bbox)
    finally:
        _refresh_state()


def replace(block_id: int, new_text: str) -> None:
    entry = get_block(block_id)
    try:
        replace_text(get_handle(), entry["page_index"], entry["block"], new_text)
    finally:
        _refresh_state()


def delete(block_id: int) -> None:
    entry = get_block(block_id)
    try:
        delete_block(get_handle(), entry["page_index"], entry["block"])
    finally:
        _refresh_state()


def move(
    block_id: int,
    destination_page_index: int | None = None,
    target_position: tuple[float, float] | None = None,
    offset: tuple[float, float] | None = None,
) -> None:
    entry = get_block(block_id)
    try:
        move_block(
            get_handle(),
            entry["page_index"],
            entry["block"],
            destination_page_index=destination_page_index,
            target_position=target_position,
            offset=offset,
        )
    finally:
        _refresh_state()


def insert(
    page_index: int,
    bbox: tuple[float, float, float, float],
    text: str,
    size: float,
    font: str | None = None,
) -> None:
    handle = get_handle()
    try:
        insert_block(handle, page_index, bbox, text, size, font=font)
    finally:
        _refresh_state()


def replace_image(image_id: int, new_image_bytes: bytes) -> None:
    entry = get_image(image_id)
    try:
        _replace_image(get_handle(), entry["page_index"], entry["image"], new_image_bytes)
    finally:
        _refresh_state()


def sanitize_document() -> dict:
    handle = get_handle()
    try:
        result = _sanitize_document(handle)
    finally:
        # scrub() mutates the document's underlying PDF object structure
        # even though it never touches visible text content -- the block
        # registry is re-derived unconditionally, same as redact()/
        # replace() above, rather than assuming this particular operation
        # couldn't have shifted anything. Unlike redact/replace which only
        # affect visible content, sanitize modifies metadata which needs a
        # fresh parse to fully apply the removal, so we update the handle
        # as well as the blocks.
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
    # its exported bytes, since parse() is the only way to get a fresh
    # TextBlock/Image list -- the handle itself has no "give me a Document"
    # method. The re-parsed handle this produces is a throwaway: the real
    # handle we keep mutating stays _state["handle"], never this one, which
    # is closed immediately so it doesn't leak across many edits in one
    # session.
    handle = get_handle()
    doc, throwaway_handle = parse(export(handle))
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
