"""LDD (Logging / Data / Diagnostics) — protocol-neutral diagnostics primitives.

Tools call :func:`event`, :func:`report`, :func:`log` (and the
``info`` / ``warning`` / ``error`` / ``debug`` shorthands) with **no**
``ctx`` argument. The live context is bound to a ContextVar by the runtime
dispatch site for the lifetime of one tool invocation; the primitives read
it from there. Calling a primitive outside an active dispatch raises
:exc:`a2kit.exceptions.AmbientContextMissing` — fail loud, never silently
no-op.

Internal layout:

- :mod:`a2kit.packages.ldd.wire` — the ``[ +s.mmm LEVEL] msg key=val`` line.
- :mod:`a2kit.packages.ldd.sinks` — the in-process sink payload + protocol.
- :mod:`a2kit.packages.ldd.ambient` — the dispatch-bound per-call state.
- :mod:`a2kit.packages.ldd.emission` — ``event`` / ``report`` / ``log`` and
  the typed :class:`EventRegistry`.
"""

from __future__ import annotations

from a2kit.exceptions import AmbientContextMissing
from a2kit.packages.ldd.ambient import ldd_state_for_call
from a2kit.packages.ldd.emission import (
    EventRegistry,
    _AppLdd,
    debug,
    error,
    event,
    info,
    log,
    report,
    warning,
)
from a2kit.packages.ldd.levels import LDD_LEVEL_RANK, LddLevel
from a2kit.packages.ldd.sinks import LddEmission, LddSink
from a2kit.packages.ldd.wire import TEXT_CAP, format_ldd_line

__all__ = [
    "LDD_LEVEL_RANK",
    "TEXT_CAP",
    "AmbientContextMissing",
    "EventRegistry",
    "LddEmission",
    "LddLevel",
    "LddSink",
    "_AppLdd",
    "debug",
    "error",
    "event",
    "format_ldd_line",
    "info",
    "ldd_state_for_call",
    "log",
    "report",
    "warning",
]
