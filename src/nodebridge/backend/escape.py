"""One escaping helper for text copied from a graph into generated code.

Source names, labels, comments, attribute names and file paths are not
identifiers. Splicing them into Python, VEX or HScript with an f-string
lets a quote or a newline close the literal and become a new statement.
Every backend inserts those strings through :func:`escape`.
"""

from __future__ import annotations


def escape(text: object, *, language: str = "python") -> str:
    """Return ``text`` safe to splice into generated source.

    ``python``
        A complete Python literal, including quotes (``repr``).
    ``doc``
        Like ``python`` when that literal cannot close a triple-quoted
        docstring; otherwise a single-line comment fragment.
    ``comment``
        One physical line. Newlines, backslashes and ``\"\"\"`` stay inside
        the comment or docstring that contains this text.
    ``vex`` / ``hscript``
        The interior of a double-quoted string. Quotes, newlines and
        backslashes are hex-escaped so they cannot end the literal.
    """
    raw = "" if text is None else str(text)
    if language == "python":
        return repr(raw)
    if language == "doc":
        literal = repr(raw)
        if '"""' in literal or "\n" in raw or "\r" in raw:
            return escape(raw, language="comment")
        return literal
    if language == "comment":
        cleaned = (
            raw.replace("\\", "\\\\")
            .replace('"""', '\\"\\"\\"')
            .replace("\r\n", "\\n")
            .replace("\n", "\\n")
            .replace("\r", "\\n")
        )
        if cleaned.endswith("\\"):
            cleaned += " "
        return cleaned
    if language in ("vex", "hscript"):
        return "".join(_hex(ch) for ch in raw)
    raise ValueError(f"unknown escape language {language!r}")


def _hex(ch: str) -> str:
    if ch in '\\"\'\n\r\t' or ord(ch) < 32:
        return f"\\x{ord(ch):02x}"
    return ch
