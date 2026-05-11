"""Public alias for ``a2kit.packages.ldd``.

Lets tools import the discoverable surface as ``from a2kit.ldd import event, report``.
Implementation lives in ``a2kit.packages.ldd`` to keep the canonical layout under
``packages/`` and satisfy the ``A2K-CORE-CLEAN`` boundary (core source MUST NOT
reference feature identifiers).
"""

from __future__ import annotations

from a2kit.packages.ldd import (
    EventRegistry,
    LddEmission,
    LddSink,
    debug,
    error,
    event,
    format_ldd_line,
    info,
    ldd_state_for_call,
    log,
    report,
    warning,
)

__all__ = [
    "EventRegistry",
    "LddEmission",
    "LddSink",
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
