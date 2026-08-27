"""Document handle -> PDF bytes."""
import pymupdf as fitz


def export(handle: fitz.Document) -> bytes:
    # Must stay a full rewrite (single startxref/%%EOF), never an incremental
    # save (e.g. handle.save(path, incremental=True)). An incremental save
    # keeps every prior-generation object -- including redacted content --
    # physically present in the file's object chain, which would defeat
    # redaction entirely. tobytes() with no incremental option always does a
    # full rewrite; do not "optimize" this into an incremental save.
    return handle.tobytes()
