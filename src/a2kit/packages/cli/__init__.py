"""CLI adapter — Click-based, in-process tool dispatch.

Public surface:
  - :func:`build_full_cli` — build the top-level Click group for an :class:`a2kit.App`.

The single-entry ``a2kit.run(app)`` (in ``a2kit/__init__.py``) is the only
caller. No fastmcp import at module load — the ``serve`` subcommand is
lazily resolved through :class:`a2kit.packages.cli.builder.LazyGroup`.
"""

from __future__ import annotations

from a2kit.packages.cli.builder import build_full_cli

__all__ = ["build_full_cli"]
