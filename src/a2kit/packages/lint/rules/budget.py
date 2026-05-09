"""A2K014 — file-size budget."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.static import (
    A2K014,
    LintMessage,
    _msg,
    is_fixture_path,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

DEFAULT_MAX_LINES = 500
BUILTIN_CAPS = frozenset({"read", "write", "destructive", "expensive", "pii", "external"})


def _physical_sloc(source: str) -> int:
    count = 0
    for raw in source.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        count += 1
    return count


def rule_a2k014(_tree: ast.AST, filename: str, source: str, *, max_lines: int = DEFAULT_MAX_LINES) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    sloc = _physical_sloc(source)
    if sloc <= max_lines:
        return
    fake = ast.Pass(lineno=1, col_offset=0)
    if suppressed(parse_noqa(source), A2K014, 1):
        return
    yield _msg(A2K014, filename, fake, f"File is {sloc} SLOC (limit: {max_lines}). Consider splitting.")


__all__ = ["BUILTIN_CAPS", "DEFAULT_MAX_LINES", "rule_a2k014"]
