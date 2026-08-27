"""Document handle -> PDF bytes."""
import pymupdf as fitz


def export(handle: fitz.Document) -> bytes:
    return handle.tobytes()
