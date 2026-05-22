"""a2kit lint package — static AST rules + runtime checks for FastMCP MCPs.

Public API:
- ``run_static_rules`` — run all AST rules over a list of source paths.
- ``run_runtime_checks`` — run runtime checks against an importable FastMCP server.
- ``LintMessage`` / ``CheckMessage`` — finding records.
- ``main`` — Click entry point (``a2kit lint ...`` console script).

This package MUST NOT import fastmcp anywhere — cold-start budget forbids it,
and ``A2K-IMPORT-DISCIPLINE`` would (rightly) fire on us.
"""

from __future__ import annotations

from a2kit.packages.lint.runtime import CheckMessage, run_runtime_checks
from a2kit.packages.lint.static import LintMessage, run_static_rules

__all__ = [
    "CheckMessage",
    "LintMessage",
    "run_runtime_checks",
    "run_static_rules",
]
