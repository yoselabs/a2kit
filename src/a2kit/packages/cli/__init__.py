"""CLI adapter — Click-based, in-process tool dispatch.

Public surface:
  - :class:`a2kit.packages.cli.surface.CliSurface` — the CLI ``Surface``
    (ADR 0028 Wave 1); ``CliSurface.bind`` owns the Typer build.
  - :func:`build_full_cli` — build the top-level Click group for an
    :class:`a2kit.App` (``CliSurface.bind``'s implementation).

Cold-start: ``build_full_cli`` lives in ``builder``, which imports
``typer`` at module scope. To keep ``import a2kit`` and the lazy
``app.cli`` accessor (which imports the ``surface`` submodule, and thus
this package) typer-free, ``build_full_cli`` is exported lazily via
module ``__getattr__`` — ``typer`` loads only when the name is actually
accessed (i.e. when ``CliSurface.bind`` runs). The ``serve`` subcommand
further defers ``fastmcp`` through :class:`builder.LazyGroup`.
"""

from __future__ import annotations

from typing import Any

__all__ = ["build_full_cli"]


def __getattr__(name: str) -> Any:
    if name == "build_full_cli":
        from a2kit.packages.cli.builder import build_full_cli

        return build_full_cli
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
