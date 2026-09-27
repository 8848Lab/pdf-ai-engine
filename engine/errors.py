"""Exceptions shared across the engine."""


class RefusedBeforeMutation(ValueError):
    """An operation refused its input before touching the document.

    A ValueError, so every existing caller and handler keeps working. The
    subtype tells a caller that the document is exactly as it was, so there
    is nothing to re-read -- so a caller such as webui/session.py can skip
    re-reading the document.

    Raise it ONLY from checks that run before the first mutation. A failure
    after a mutation must stay a plain ValueError, so callers re-read the
    document.
    """
