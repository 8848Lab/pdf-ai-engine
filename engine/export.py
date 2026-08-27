"""Document handle -> PDF bytes."""
import fitz


def export(handle: fitz.Document) -> bytes:
    return handle.tobytes()
