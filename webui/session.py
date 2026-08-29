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
from engine.operations import redact_region, replace_text
from engine.parser import parse

_state: dict = {"handle": None, "blocks": [], "next_block_id": 0}


def load_document(pdf_bytes: bytes) -> None:
    """Parse pdf_bytes, replacing any previously-loaded document.

    Parses BEFORE resetting the current session, so a bad/unparseable upload
    never destroys an in-progress document -- if parse() raises, nothing has
    been touched yet and the operator keeps whatever they were editing.
    """
    doc, handle = parse(pdf_bytes)
    reset()
    _state["handle"] = handle
    _state["blocks"] = _build_block_registry(doc)


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
        _refresh_blocks()


def replace(block_id: int, new_text: str) -> None:
    entry = get_block(block_id)
    try:
        replace_text(get_handle(), entry["page_index"], entry["block"], new_text)
    finally:
        _refresh_blocks()


def export_current() -> bytes:
    return export(get_handle())


def _refresh_blocks() -> None:
    # Re-derive the Document projection from the handle's CURRENT state via
    # its exported bytes, since parse() is the only way to get a fresh
    # TextBlock list -- the handle itself has no "give me a Document" method.
    # The re-parsed handle this produces is a throwaway: the real handle we
    # keep mutating stays _state["handle"], never this one, which is closed
    # immediately so it doesn't leak across many edits in one session.
    handle = get_handle()
    doc, throwaway_handle = parse(export(handle))
    throwaway_handle.close()
    _state["blocks"] = _build_block_registry(doc)


def _build_block_registry(doc: Document) -> list[dict]:
    # Ids are drawn from a monotonically increasing counter that only resets
    # when the document is fully replaced, NOT from the block's position in
    # this registry. Positional ids would be silently reassigned on every
    # refresh, so a stale id held by the frontend (e.g. a double-clicked
    # button firing twice) would resolve to a DIFFERENT surviving block and
    # destroy it. With monotonic ids a stale id simply no longer exists, and
    # get_block() raises the LookupError it was always meant to raise.
    registry = []
    for page in doc.pages:
        for block in page.text_blocks:
            registry.append(
                {"id": _state["next_block_id"], "page_index": page.index, "block": block}
            )
            _state["next_block_id"] += 1
    return registry


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
    _state["next_block_id"] = 0
