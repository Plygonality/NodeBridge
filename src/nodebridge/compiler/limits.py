"""Recursion budgets for expression compilers and group lifting.

Both limits sit well under CPython's default recursion limit (1000) so a
deep graph becomes a diagnostic instead of a RecursionError.
"""

MAX_EXPRESSION_DEPTH = 128
MAX_GROUP_DEPTH = 128


def note_depth(diagnostics, code: str, message: str) -> None:
    """Record ``code`` once. Further hits stay silent so a deep tree emits one diagnostic."""
    if diagnostics is None or any(getattr(item, "code", None) == code for item in diagnostics):
        return
    diagnostics.error(code, message)
