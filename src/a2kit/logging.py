"""Structured tool logger — auto-binds `tool.name` + `tool.connection`.

Public surface:

- ``get_tool_logger(name)`` — return a structlog ``BoundLogger`` for
  a tool/plugin author. Reads contextvars set by the logging middleware,
  so emitted records auto-include ``tool.name`` and (when present)
  ``tool.connection`` — the same labels the OTel span carries.

What this kit *does* and *does not* do:

- **Does**: bind ``tool.name`` / ``tool.connection`` into structlog
  contextvars for the duration of a tool call.
- **Does not**: ship structlog configuration (formatters, processors,
  handlers), nor inject OTel ``trace_id`` / ``span_id`` into log records.
  Trace/span correlation needs the host to bridge structlog→stdlib logging
  and enable OTel ``LoggingInstrumentor``. The kit only guarantees the
  ``tool.*`` labels match the labels on the active span.

`structlog` is imported lazily inside the helpers so the runtime cost lands
only on hosts that actually log.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import structlog


def get_tool_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog ``BoundLogger`` for tool/plugin author use.

    The returned logger reads ``structlog.contextvars`` at emit time, so any
    keys bound by the logging middleware (``tool.name``, ``tool.connection``)
    appear on every record without the caller threading them through.

    Hosts own structlog *configuration* (processors, formatter, handler).
    a2kit only binds context for the duration of a tool call.
    """
    import structlog  # noqa: PLC0415 — lazy: only hosts that log pay the import.

    return structlog.get_logger(name)


def build_tool_bindings(tool_name: str, connection_key: tuple[str, ...] | None) -> dict[str, str]:
    """Build the structlog/OTel binding dict for a tool call.

    Same shape used by ``bind_tool_context``, the logging middleware, and the
    sync tool wrapper — single source of truth for the key spelling.
    """
    bindings: dict[str, str] = {"tool.name": tool_name}
    if connection_key is not None:
        bindings["tool.connection"] = "-".join(connection_key)
    return bindings


def bind_tool_context(tool_name: str, connection_key: tuple[str, ...] | None) -> Any:
    """Bind ``tool.name`` (+ ``tool.connection``) into ``structlog.contextvars``.

    Returns the token-bag from ``structlog.contextvars.bind_contextvars`` —
    callers must ``unbind_contextvars`` (or ``reset_contextvars``) on exit
    to keep context isolated per-call. The logging middleware uses
    ``bound_contextvars`` (a context manager) instead; this helper is
    exposed for explicit-chain users.
    """
    import structlog  # noqa: PLC0415

    return structlog.contextvars.bind_contextvars(**build_tool_bindings(tool_name, connection_key))


__all__ = ["bind_tool_context", "build_tool_bindings", "get_tool_logger"]
