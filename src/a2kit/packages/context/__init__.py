"""Transport-neutral :class:`a2kit.ToolContext` implementations.

The implementation lives in :mod:`a2kit.packages.context.stderr`:
``StderrToolContext`` (the CLI / direct-call context) and
``MCPOnlyError`` (raised by methods with no CLI-side semantics).
"""

from __future__ import annotations

from a2kit.packages.context.stderr import MCPOnlyError, StderrToolContext

__all__ = ["MCPOnlyError", "StderrToolContext"]
