"""``a2kit.log`` — the author-facing emission surface, on stdlib ``logging``.

One concept: stdlib level methods (``debug`` / ``info`` / ``warning`` /
``error``). Each accepts a message + fields OR a typed instance. There is no
``event()`` / ``report()`` / loose ``log()`` verb, and no second public
namespace for durable records — the call access-log is internal plumbing
(the ``a2kit.calls`` logger + an opt-in file handler), configured not called.

The package front door re-exports the PUBLIC names so external modules import
``from a2kit.packages.log import X`` rather than reaching past it. Private
framework seams (``_CallScope`` / ``_active_scope`` / ``_CallScopeFilter`` /
``_AppLog``) stay in their submodules and are deep-imported with an explicit
``# noqa: A2K-PKG-FRONT-DOOR`` by the few framework files that need them.
"""

from __future__ import annotations

from a2kit.packages.log.call_log import CallLogFileHandler, CallRecord
from a2kit.packages.log.emission import debug, error, info, set_wire_level, warning
from a2kit.packages.log.formatter import CondensedFormatter, format_condensed_line
from a2kit.packages.log.handlers import LiveHandler, OtelHandler, StderrJsonHandler, StderrPrettyHandler
from a2kit.packages.log.levels import LOG_LEVEL_NUMBER, TRACE_LEVEL, LogLevel, install_trace_level
from a2kit.packages.log.scope import bind_call_scope, current_surface, current_surface_client_id

__all__ = [
    "LOG_LEVEL_NUMBER",
    "TRACE_LEVEL",
    "CallLogFileHandler",
    "CallRecord",
    "CondensedFormatter",
    "LiveHandler",
    "LogLevel",
    "OtelHandler",
    "StderrJsonHandler",
    "StderrPrettyHandler",
    "bind_call_scope",
    "current_surface",
    "current_surface_client_id",
    "debug",
    "error",
    "format_condensed_line",
    "info",
    "install_trace_level",
    "set_wire_level",
    "warning",
]
