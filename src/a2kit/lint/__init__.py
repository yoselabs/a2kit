"""a2kit.lint — static + runtime lint rules for FastMCP MCPs.

Two layers:

- `a2kit.lint.static` — AST-only rules (`A2K001`..`A2K006`). No imports executed.
  Output ruff-style concise findings. Used by `uvx a2kit lint paths...`.
- `a2kit.lint.runtime` — checks that need an importable FastMCP server
  (`A2KR001`..`A2KR004`). Used by `uvx a2kit check --import path:server`.

Both layers honour `[tool.a2kit.lint] disabled = [...]` and per-line
`# noqa: A2KXXX` comments.
"""

from __future__ import annotations

from a2kit.lint._common import LintMessage
from a2kit.lint.cli import main
from a2kit.lint.runtime import CheckMessage, run_runtime_checks
from a2kit.lint.static import run_static_rules

__all__ = [
    "CheckMessage",
    "LintMessage",
    "main",
    "run_runtime_checks",
    "run_static_rules",
]
