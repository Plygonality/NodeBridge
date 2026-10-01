"""Helpers for readable generated Python."""

from __future__ import annotations

import math
from typing import Any


def literal(value: Any) -> str:
    """Readable Python literal: short floats, tuples for vectors."""
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "0.0"
        text = f"{value:.6f}".rstrip("0")
        return text + "0" if text.endswith(".") else text
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        items = ", ".join(literal(v) for v in value)
        return f"({items},)" if len(value) == 1 else f"({items})"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{literal(k)}: {literal(v)}" for k, v in value.items()) + "}"
    return repr(value)


def clean_number(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


class PyWriter:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.level = 0

    def line(self, text: str = "") -> "PyWriter":
        self.lines.append(("    " * self.level + text) if text else "")
        return self

    def comment(self, text: str) -> "PyWriter":
        for part in text.splitlines() or [""]:
            self.line(f"# {part}".rstrip())
        return self

    def blank(self) -> "PyWriter":
        if self.lines and self.lines[-1] != "":
            self.lines.append("")
        return self

    def indent(self) -> "PyWriter":
        self.level += 1
        return self

    def dedent(self) -> "PyWriter":
        self.level = max(0, self.level - 1)
        return self

    def raw(self, text: str) -> "PyWriter":
        """Append a line without indentation (contents of triple-quoted strings)."""
        self.lines.append(text)
        return self

    def mark(self) -> int:
        return len(self.lines)

    def insert(self, index: int, lines: list[str]) -> None:
        self.lines[index:index] = lines

    def multiline(self, target: str, prefix: str, text: str) -> "PyWriter":
        """``target = prefix + \"\"\"text\"\"\"`` with the text kept verbatim."""
        if '"""' in text or "\\" in text:
            return self.line(f"{target} = {prefix + ' + ' if prefix else ''}{text!r}")
        self.line(f'{target} = {prefix + " + " if prefix else ""}"""\\')
        for part in text.rstrip("\n").splitlines():
            self.raw(part)
        self.raw('"""')
        return self

    def block(self, text: str) -> "PyWriter":
        for part in text.strip("\n").splitlines():
            self.line(part)
        return self

    def text(self) -> str:
        while self.lines and self.lines[-1] == "":
            self.lines.pop()
        return "\n".join(self.lines) + "\n"
