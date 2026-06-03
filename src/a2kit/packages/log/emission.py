"""Author-facing emission primitives, refounded on stdlib ``logging``.

The four level methods (``debug`` / ``info`` / ``warning`` / ``error``) are
the sole emission surface. Each emits ONE stdlib ``LogRecord`` on the
``a2kit`` logger at the matching severity. User fields ride a single
structured ``a2kit_fields`` attribute on the record (a single dict avoids
clobbering reserved ``LogRecord`` attribute names such as ``name``/``msg``).

The methods stay ``async`` because the MCP wire path is an inline
``await ctx.log(...)`` (live, mid-call streaming — never deferred behind a
sync handler). The stdlib emit drives the sync handlers (stderr / otel /
live / call-log file); the wire is awaited separately.
"""

from __future__ import annotations

import dataclasses
import logging
from enum import Enum
from typing import Any, Literal

from a2kit.packages.log.formatter import _cap_text
from a2kit.packages.log.scope import _active_scope, _elapsed_ms, _is_fastmcp_context

_LOGGER = logging.getLogger("a2kit")

#: MCP wire vocabulary. The custom ``trace`` level has no MCP counterpart, so
#: it maps to ``debug`` on the wire.
_MCP_LEVEL: dict[int, Literal["debug", "info", "warning", "error"]] = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warning",
    logging.ERROR: "error",
}

#: Minimum level that streams on the MCP wire. The logger itself sits at DEBUG
#: (so the call-log file can capture debug), and each handler self-filters; the
#: wire is the one channel not expressed as a stdlib handler, so its threshold
#: lives here. App boot sets it from ``LogConfig.wire_level`` (and raises it
#: above CRITICAL to honour the ``enabled=False`` kill-switch).
_WIRE_LEVEL: int = logging.INFO


def set_wire_level(levelno: int) -> None:
    """Set the minimum level that streams on the MCP wire (called at app boot)."""
    global _WIRE_LEVEL  # noqa: PLW0603 -- module-level wire threshold, set once per app boot
    _WIRE_LEVEL = levelno


def _resolve(__msg_or_instance: Any, fields: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Resolve ``(msg, fields)`` for either a string message or a typed instance.

    A string first-positional is the message; ``fields`` are the kwargs. A
    typed instance (pydantic / dataclass / object) IS the structured payload:
    the message defaults to the type name, the payload derives from
    ``model_dump`` / ``dataclasses.asdict`` / ``vars`` with ``Enum`` values
    unwrapped to ``.value``; extra kwargs merge in after the instance fields.
    """
    if isinstance(__msg_or_instance, str):
        return __msg_or_instance, fields

    instance = __msg_or_instance
    if hasattr(instance, "model_dump"):
        payload = instance.model_dump(mode="json")
    elif dataclasses.is_dataclass(instance) and not isinstance(instance, type):
        payload = dataclasses.asdict(instance)
    else:
        try:
            payload = dict(vars(instance))
        except TypeError:
            payload = {}
    payload = {k: (v.value if isinstance(v, Enum) else v) for k, v in payload.items()}
    payload.update(fields)
    return type(instance).__name__, payload


async def _emit(levelno: int, __msg_or_instance: Any, fields: dict[str, Any]) -> None:
    """Emit one record on the ``a2kit`` logger, then stream it on the wire.

    Two channels: (1) the sync stdlib handlers (stderr / otel / live / call-log
    file) via ``_LOGGER.log``; (2) the MCP wire, an inline ``await ctx.log(...)``
    so a long-running call surfaces its emissions live, mid-call — never
    deferred behind a sync handler. The wire fires only for a real fastmcp
    Context; the CLI/stderr path is owned by the stdlib handlers.
    """
    msg, resolved = _resolve(__msg_or_instance, fields)
    _LOGGER.log(levelno, msg, extra={"a2kit_fields": resolved})

    scope = _active_scope()
    if scope is None or scope.ctx is None or levelno < _WIRE_LEVEL:
        return
    if _is_fastmcp_context(scope.ctx):
        await scope.ctx.log(
            level=_MCP_LEVEL.get(levelno, "info"),
            message=_cap_text(msg),
            extra={**resolved, "a2kit_elapsed_ms": _elapsed_ms(scope)},
        )


async def info(__msg: Any, /, **fields: Any) -> None:
    """Emit an INFO record — commentary; streams on the wire."""
    await _emit(logging.INFO, __msg, dict(fields))


async def debug(__msg: Any, /, **fields: Any) -> None:
    """Emit a DEBUG record — bulky diagnostic detail; file-only by level."""
    await _emit(logging.DEBUG, __msg, dict(fields))


async def warning(__msg: Any, /, **fields: Any) -> None:
    """Emit a WARNING record."""
    await _emit(logging.WARNING, __msg, dict(fields))


async def error(__msg: Any, /, **fields: Any) -> None:
    """Emit an ERROR record."""
    await _emit(logging.ERROR, __msg, dict(fields))
