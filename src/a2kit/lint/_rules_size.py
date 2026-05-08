"""File-size budget rule.

A2K014 — file too long (measured in physical SLOC).
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.lint._common import (
    A2K014,
    DEFAULT_MAX_LINES,
    is_fixture_path,
    msg,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit.lint._common import LintMessage


def _physical_sloc(source: str) -> int:
    """Count physical SLOC: non-blank, non-comment-only lines.

    Docstrings are counted (they're code structure, not commentary).
    Inline comments after code (`x = 1  # note`) count as code lines.
    Pure comment lines (`# foo`) and blank lines do not.
    """
    count = 0
    for raw in source.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        count += 1
    return count


def rule_a2k014(_tree: ast.AST, filename: str, source: str, *, max_lines: int = DEFAULT_MAX_LINES) -> Iterable[LintMessage]:
    """A2K014 — file too long (measured in physical SLOC).

    Modules over `max_lines` SLOC (default 500) are hard to navigate, hard
    to reason about, and a smell that the file is doing too many things.
    Threshold is configurable via `[tool.a2kit.lint] max_lines`.

    Counted: lines that are neither blank nor comment-only. Docstrings count
    (they're structural). Inline `#` comments after code don't subtract.

    The rule is fixture-aware: tests / examples are exempt because long
    test suites are normal (and not user code).
    """
    if is_fixture_path(filename):
        return
    sloc = _physical_sloc(source)
    if sloc <= max_lines:
        return
    # Anchor the diagnostic at line 1, col 0. We need an `ast.AST` with
    # `lineno`/`col_offset` for `msg()`'s `getattr` lookup. `ast.Pass` is a
    # `stmt` subclass — both attrs are declared on `stmt` so ty is happy.
    fake = ast.Pass(lineno=1, col_offset=0)
    if suppressed(parse_noqa(source), A2K014, 1):
        return
    yield msg(
        A2K014,
        filename,
        fake,
        f"File is {sloc} SLOC (limit: {max_lines}). Consider splitting.",
    )


__all__ = ["rule_a2k014"]
