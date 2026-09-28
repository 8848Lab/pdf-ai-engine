"""Exceptions shared across the engine."""


class RefusedBeforeMutation(ValueError):
    """An operation refused its input before touching the document.

    A ValueError, so every existing caller and handler keeps working. The
    subtype tells a caller that the document is exactly as it was, so there
    is nothing to re-read -- webui/session.py skips its registry refresh for
    it, which keeps every block and image id valid after a refusal.

    Raise it ONLY from checks that run before the first mutation. A failure
    after a mutation must stay a plain ValueError, so callers re-read the
    document.
    """
