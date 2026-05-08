"""Shared lint types and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import ast

# Rule codes — declared here so each rule module can import its own.
A2K001 = "A2K001"
A2K002 = "A2K002"
A2K003 = "A2K003"
A2K004 = "A2K004"
A2K005 = "A2K005"
A2K006 = "A2K006"
A2K008 = "A2K008"
A2K009 = "A2K009"
A2K010 = "A2K010"
A2K011 = "A2K011"
A2K012 = "A2K012"
A2K013 = "A2K013"
A2K014 = "A2K014"

ALL_RULES = (A2K001, A2K002, A2K003, A2K004, A2K005, A2K006, A2K008, A2K009, A2K010, A2K011, A2K012, A2K013, A2K014)

# Default file-size budget for A2K014. Override via `[tool.a2kit.lint] max_lines`.
DEFAULT_MAX_LINES = 500

BUILTIN_CAPS = frozenset({"read", "write", "destructive", "expensive", "pii", "external"})
_FIXTURE_PATH_TOKENS = ("tests/", "tests\\", "examples/", "examples\\")


def is_fixture_path(filename: str) -> bool:
    """True if `filename` is under tests/ or examples/ (lint exempts these)."""
    return any(token in filename for token in _FIXTURE_PATH_TOKENS)


@dataclass(frozen=True)
class LintMessage:
    """Single lint finding from a static rule."""

    rule: str
    filename: str
    line: int
    col: int
    message: str

    def format_concise(self) -> str:
        """ruff-concise format: `path:line:col: RULE message`."""
        return f"{self.filename}:{self.line}:{self.col}: {self.rule} {self.message}"


def parse_noqa(source: str) -> dict[int, set[str]]:
    """Map line number → set of rule codes suppressed via `# noqa: CODE` on that line.

    `# noqa` (no codes) suppresses everything; we use the sentinel `"*"`.
    """
    out: dict[int, set[str]] = {}
    for i, line in enumerate(source.splitlines(), start=1):
        idx = line.find("# noqa")
        if idx == -1:
            continue
        rest = line[idx + len("# noqa") :].lstrip()
        if rest.startswith(":"):
            codes = {c.strip() for c in rest[1:].split(",") if c.strip()}
            out[i] = codes
        else:
            out[i] = {"*"}
    return out


def suppressed(noqa_map: dict[int, set[str]], rule: str, line: int) -> bool:
    codes = noqa_map.get(line)
    if not codes:
        return False
    return "*" in codes or rule in codes


def msg(rule: str, filename: str, node: ast.AST, text: str) -> LintMessage:
    """Build a LintMessage anchored at `node`'s position."""
    return LintMessage(
        rule=rule,
        filename=filename,
        line=getattr(node, "lineno", 1),
        col=getattr(node, "col_offset", 0),
        message=text,
    )
