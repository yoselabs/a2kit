"""Public alias for ``a2kit.packages.ldd``.

Lets tools import the discoverable surface as ``from a2kit.ldd import event, report``.
Implementation lives in ``a2kit.packages.ldd`` to keep the canonical layout under
``packages/``.
"""

from __future__ import annotations

from a2kit.packages.ldd import (
    LDD_LEVEL_RANK,
    EventRegistry,
    LddLevel,
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

# Sink-author types (LddEmission, LddSink) demoted from this re-export;
# import them from `a2kit.packages.ldd` directly when implementing sinks.

__all__ = [
    "LDD_LEVEL_RANK",
    "EventRegistry",
    "LddLevel",
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
