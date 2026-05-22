"""Tombstone — tool-context implementations moved to ``a2kit.packages.context``.

``StderrToolContext`` and ``MCPOnlyError`` were relocated to the
transport-neutral ``a2kit.packages.context`` package in the
import-acyclicity refactor: they are not CLI-specific and living under
``packages/cli`` formed an ``mcp -> cli`` import cycle.
"""

from __future__ import annotations

from typing import Any

_MOVED = ("MCPOnlyError", "StderrToolContext", "_StubResourceResult")


def __getattr__(name: str) -> Any:
    if name in _MOVED:
        msg = (
            f"a2kit.packages.cli.context.{name} moved to a2kit.packages.context "
            f"in the import-acyclicity refactor. Import it from the new home: "
            f"`from a2kit.packages.context import {name}`."
        )
        raise ImportError(msg)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
