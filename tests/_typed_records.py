"""Shared typed view over a stdlib ``logging.LogRecord``.

a2kit injects per-call context (``call_id`` / ``tool_name`` / ``elapsed_ms`` /
``surface``) and the structured user payload (``a2kit_fields``) onto stdlib
``LogRecord`` instances via a logging ``Filter`` / ``extra=``. Production code
reads these defensively with ``getattr(record, "call_id", None)`` (see
``src/a2kit/packages/log/call_log.py``), but tests assert on them directly.

This ``Protocol`` gives the type-checker a precise view: ``cast`` a captured
``LogRecord`` to ``A2kitLogRecord`` before reading the injected attributes.
Only the base ``LogRecord`` members the cast variables actually touch
(``levelno`` / ``getMessage``) are declared alongside the injected fields.
"""

from __future__ import annotations

from typing import Any, Protocol


class A2kitLogRecord(Protocol):
    """Typed view of a ``LogRecord`` carrying a2kit's injected fields."""

    # a2kit-injected per-call context (via _CallScopeFilter / extra=).
    call_id: str | None
    tool_name: str | None
    elapsed_ms: int | None
    surface: str | None
    a2kit_fields: dict[str, Any]

    # Base LogRecord members the same cast variables also read.
    levelno: int

    def getMessage(self) -> str: ...  # noqa: N802 -- mirrors stdlib LogRecord.getMessage


class Named(Protocol):
    """A callable that carries a ``__name__`` (the bound tools from a Router).

    ``Router.bound_tools()`` is typed ``(...) -> Any``; ty rightly notes not
    every callable has ``__name__``. Casting to this Protocol restores the
    attribute view without an ``Any`` widening or a ``getattr`` literal.
    """

    __name__: str
