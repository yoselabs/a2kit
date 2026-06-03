"""Operator handlers — the built-in sinks re-expressed as stdlib ``logging.Handler``s.

Each attaches to the ``a2kit`` logger (commentary). They read the structured
``a2kit_fields`` payload + filter-injected ``elapsed_ms`` off the record. A
failing handler NEVER aborts its siblings, the wire, or the producing tool:
``emit`` catches, logs at WARN under ``a2kit.log.sink_failed`` (a non-streaming
logger), and drops the record.

The MCP wire is deliberately NOT a handler here — it stays an inline
``await ctx.log()`` in the emission primitive (live streaming).
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from a2kit.packages.log.formatter import CondensedFormatter

#: Failures route here; ``propagate=False`` + a NullHandler keep them from
#: recursing back through the ``a2kit`` handlers that may have failed.
_FAILURE_LOGGER = logging.getLogger("a2kit.log.sink_failed")
_FAILURE_LOGGER.propagate = False
if not _FAILURE_LOGGER.handlers:
    _FAILURE_LOGGER.addHandler(logging.NullHandler())


class _IsolatingHandler(logging.Handler):
    """Base handler whose failures are isolated + logged, never propagated."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._safe_emit(record)
        except Exception as exc:  # noqa: BLE001 -- isolation is the contract
            _FAILURE_LOGGER.warning(
                "log handler %s failed on %s: %s: %s",
                type(self).__name__,
                record.getMessage(),
                type(exc).__name__,
                exc,
            )

    def _safe_emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class StderrPrettyHandler(_IsolatingHandler):
    """One human-readable condensed line per record, to stderr."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(CondensedFormatter())

    def _safe_emit(self, record: logging.LogRecord) -> None:
        print(self.format(record), file=sys.stderr, flush=True)  # noqa: T201


class StderrJsonHandler(_IsolatingHandler):
    """One JSON record per line, to stderr."""

    def _safe_emit(self, record: logging.LogRecord) -> None:
        payload = {
            "level": record.levelname,
            "msg": record.getMessage(),
            "elapsed_ms": getattr(record, "elapsed_ms", None),
            "call_id": getattr(record, "call_id", None),
            "tool": getattr(record, "tool_name", None),
            "fields": getattr(record, "a2kit_fields", {}),
        }
        print(json.dumps(payload, separators=(",", ":"), default=str), file=sys.stderr, flush=True)  # noqa: T201


class LiveHandler(_IsolatingHandler):
    """One stdout line per record whose message matches a name prefix.

    Simplified from the former async live sink to a sync stdout handler
    (per §4.3 — the live feed is "write now"). The async heartbeat is
    dropped; the per-record line remains.
    """

    def __init__(self, *, event_prefixes: tuple[str, ...] = ("",)) -> None:
        super().__init__()
        self._prefixes = event_prefixes

    def _safe_emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if not any(msg.startswith(p) for p in self._prefixes):
            return
        secs = (getattr(record, "elapsed_ms", None) or 0) / 1000.0
        print(f"[+{secs:>6.3f}s] {msg}", file=sys.stdout, flush=True)  # noqa: T201


class OtelHandler(_IsolatingHandler):
    """One OTel span per ``*Ended`` record; drains silently when no SDK."""

    def _safe_emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if not msg.endswith("Ended"):
            return
        tracer = _get_tracer()
        if tracer is None:
            return
        with tracer.start_as_current_span(msg) as span:
            if getattr(record, "tool_name", None):
                span.set_attribute("a2kit.tool", getattr(record, "tool_name", ""))
            span.set_attribute("a2kit.elapsed_ms", getattr(record, "elapsed_ms", None) or 0)
            for key, value in getattr(record, "a2kit_fields", {}).items():
                if isinstance(value, str | int | float | bool):
                    span.set_attribute(f"a2kit.{key}", value)


def _get_tracer() -> Any | None:
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    try:
        return trace.get_tracer("a2kit")
    except Exception:  # noqa: BLE001 -- defensive against SDK init quirks
        return None


__all__ = [
    "LiveHandler",
    "OtelHandler",
    "StderrJsonHandler",
    "StderrPrettyHandler",
]
