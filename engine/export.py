"""Document handle -> PDF bytes."""
import pymupdf as fitz


def export(handle: fitz.Document) -> bytes:
    # Must stay a full rewrite (single startxref/%%EOF), never an incremental
    # save (e.g. handle.save(path, incremental=True)). An incremental save
    # keeps every prior-generation object -- including redacted content --
    # physically present in the file's object chain, which would defeat
    # redaction entirely. tobytes() with no incremental option always does a
    # full rewrite; do not "optimize" this into an incremental save.
    #
    # garbage=3 is load-bearing, not an optimization: scrub(metadata=True)
    # un-references the Info dictionary object (nulls the trailer's /Info
    # pointer) rather than overwriting its contents, so a plain tobytes()
    # with no garbage collection writes that now-orphaned object straight
    # into the output -- every "removed" metadata value stays physically
    # present and trivially recoverable, even though every in-app check
    # reports it gone. garbage=3 removes objects nothing references, which
    # cannot weaken the redaction guarantee (a referenced object is never
    # touched) and is exactly what closes this leak. Do not remove it for
    # the same reason the paragraph above warns against incremental=True.
    return handle.tobytes(garbage=3)
