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
from typing import Any

_LOGGER = logging.getLogger("a2kit")


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
    """Emit one record on the ``a2kit`` logger carrying ``fields``."""
    msg, resolved = _resolve(__msg_or_instance, fields)
    _LOGGER.log(levelno, msg, extra={"a2kit_fields": resolved})


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
