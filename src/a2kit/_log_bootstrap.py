"""App-boot helper to wire the ``a2kit`` + ``a2kit.calls`` loggers from config.

Lives at the runtime layer (alongside ``app.py``) so it can import ``LogConfig``
(kernel) and the log front door (L0) without inverting the layer DAG.

Topology (the structural guarantee):

- ``a2kit`` (author commentary) gets the ``_CallScopeFilter`` + the configured
  streaming handlers (stderr / otel / live), each at ``wire_level``. The MCP
  wire is NOT a handler — it streams inline from the emission primitive.
- ``a2kit.calls`` (the access-log) gets ``propagate=False`` + ONLY the call-log
  file handler, so call records can never reach the streaming handlers.
- When the call-log is on, the file handler is ALSO attached to ``a2kit`` so the
  author's ``debug`` enrichment rows land in the same file, correlated by
  ``call_id``.

Idempotent: only handlers/filters this module added (tagged ``_a2kit_managed``)
are reset on re-entry, so constructing many Apps in a test session does not
stack handlers.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from a2kit.packages.log import emission
from a2kit.packages.log.call_log import CallLogFileHandler
from a2kit.packages.log.handlers import LiveHandler, OtelHandler, StderrJsonHandler, StderrPrettyHandler
from a2kit.packages.log.levels import LOG_LEVEL_NUMBER, install_trace_level
from a2kit.packages.log.scope import _CallScopeFilter

if TYPE_CHECKING:
    from a2kit.config import LogConfig

_DISABLED_LEVEL = logging.CRITICAL + 10


def _reset_managed(logger: logging.Logger) -> None:
    """Remove only the handlers/filters this module previously installed."""
    for handler in list(logger.handlers):
        if getattr(handler, "_a2kit_managed", False):
            logger.removeHandler(handler)
    for flt in list(logger.filters):
        if getattr(flt, "_a2kit_managed", False):
            logger.removeFilter(flt)


def _managed(obj: object) -> object:
    obj._a2kit_managed = True  # type: ignore[attr-defined]  # noqa: SLF001 -- marker for idempotent reset
    return obj


def configure_logging(log_config: LogConfig) -> None:
    """Wire the ``a2kit`` + ``a2kit.calls`` loggers from ``log_config``."""
    install_trace_level()

    a2kit = logging.getLogger("a2kit")
    calls = logging.getLogger("a2kit.calls")
    _reset_managed(a2kit)
    _reset_managed(calls)

    if not log_config.enabled:
        a2kit.setLevel(_DISABLED_LEVEL)
        emission.set_wire_level(_DISABLED_LEVEL)
        calls.setLevel(_DISABLED_LEVEL)
        return

    # Logger sits at DEBUG so the call-log file can capture debug rows; each
    # handler self-filters (wire/stderr at wire_level, file at call_log_level).
    a2kit.setLevel(logging.DEBUG)
    a2kit.addFilter(_managed(_CallScopeFilter()))  # type: ignore[arg-type]
    emission.set_wire_level(LOG_LEVEL_NUMBER[log_config.wire_level])

    wire_no = LOG_LEVEL_NUMBER[log_config.wire_level]
    streaming: list[logging.Handler] = []
    if log_config.stderr_sink == "pretty":
        streaming.append(StderrPrettyHandler())
    elif log_config.stderr_sink == "json":
        streaming.append(StderrJsonHandler())
    if _should_register_otel(log_config.otel_sink):
        streaming.append(OtelHandler())
    if log_config.live_sink == "on":
        streaming.append(LiveHandler(event_prefixes=log_config.live_event_prefixes))
    for handler in streaming:
        handler.setLevel(wire_no)
        a2kit.addHandler(_managed(handler))  # type: ignore[arg-type]

    if log_config.call_log != "off":
        log_dir = log_config.call_log_dir if log_config.call_log == "on" else log_config.call_log
        file_level = logging.DEBUG if log_config.call_log_level == "DEBUG" else logging.INFO
        file_handler = CallLogFileHandler(log_dir=log_dir, inline_threshold=log_config.call_log_inline_threshold)
        file_handler.setLevel(file_level)
        _managed(file_handler)
        # On a2kit: capture the author's debug/info enrichment rows (call_id-correlated).
        a2kit.addHandler(file_handler)
        # On a2kit.calls: the auto call-records, file-only, never streamed.
        calls.propagate = False
        calls.setLevel(logging.DEBUG)
        calls.addFilter(_managed(_CallScopeFilter()))  # type: ignore[arg-type]
        calls.addHandler(file_handler)


def _should_register_otel(mode: str) -> bool:
    """``on`` → always; ``off`` → never; ``auto`` → SDK present AND an exporter env set."""
    if mode == "off":
        return False
    if mode == "on":
        return True
    try:
        import opentelemetry  # noqa: F401
    except ImportError:
        return False
    return any(key.startswith("OTEL_EXPORTER_") for key in os.environ)


__all__ = ["configure_logging"]
