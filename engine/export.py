"""Document handle -> PDF bytes.

Two serializers, deliberately distinct:

- export()   -- the real download path. Garbage-collected and compacted, so
                nothing un-referenced (scrubbed metadata, a replaced image's
                orphaned original) survives into the file the operator gets.
- snapshot() -- a plain, non-destructive serialization for internal callers
                that only need a parseable copy of the CURRENT state and
                must not disturb the live handle.

Both are non-mutating with respect to the handle passed in; see export()'s
own comment for why that took work.
"""
import pymupdf as fitz


def snapshot(handle: fitz.Document) -> bytes:
    """Serialize `handle` exactly as it stands, without garbage collection.

    Deliberately NOT export(): this is for callers that hold a live,
    still-being-edited handle and only want a parseable copy of its current
    state (webui/session.py re-derives its block/image registry this way
    after every operation). Such a caller needs no compaction -- these bytes
    are parsed once and thrown away, never handed to the operator -- and
    tobytes()'s default garbage=0 is the only setting verified not to
    disturb the source document at all.

    Not a substitute for export() on any path whose bytes reach a file: with
    no garbage collection, un-referenced objects (scrubbed metadata, a
    replaced image's orphaned original) are written out verbatim.
    """
    return handle.tobytes()


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
    # reports it gone. The same applies to replace_image, which leaves the
    # original bitmap un-referenced when it swaps the last placement of an
    # xref. garbage=3 removes objects nothing references, which cannot
    # weaken the redaction guarantee (a referenced object is never touched)
    # and is exactly what closes both leaks. Do not remove it for the same
    # reason the paragraph above warns against incremental=True.
    #
    # The garbage pass runs on a THROWAWAY copy, never on `handle` itself,
    # and that indirection is as load-bearing as the garbage=3. Verified on
    # PyMuPDF 1.28.2: tobytes(garbage=N) with N >= 2 does not just decide
    # what to write, it compacts and renumbers the LIVE document's object
    # table in place. Calling it straight on a session's handle left the
    # image a just-completed insert_image had added holding a dangling
    # /ColorSpace reference (and PyMuPDF's own doc.InsertedImages md5->xref
    # cache pointing at freed xrefs), so the NEXT insert_image into that
    # handle produced a document MuPDF could no longer parse: "invalid ICC
    # colorspace". Isolation matrix, two replace_image calls varying only
    # the intervening call: none/garbage=0/garbage=1 all fine, garbage=2/3/4
    # all corrupt. Serializing plainly first and collecting on the reopened
    # copy gives byte-for-byte the same guarantees -- an object un-referenced
    # in the original is still un-referenced in the copy -- while leaving the
    # caller's handle untouched, so a session survives any number of edits.
    # See test_two_replace_images_with_an_export_between_them_both_land.
    scratch = fitz.open(stream=snapshot(handle), filetype="pdf")
    try:
        return scratch.tobytes(garbage=3)
    finally:
        scratch.close()
