"""LDD (logging / debug / diagnostic) primitives — protocol-neutral free functions.

Tools that previously called ``ctx.event(...)`` and ``ctx.report(...)`` now use
the module-level functions :func:`event` and :func:`report`, passing the live
context as the first argument. Both functions accept any ``fastmcp.Context``-
shaped object: the real ``fastmcp.Context`` (MCP transport) or the CLI stub.

Per-call state (event/report kill-switches, report type, tool name, elapsed-ms
basis) flows through a :class:`contextvars.ContextVar` set by the runtime
dispatch site before the tool body runs and reset after — no wrapper layer
needed, no monkey-patching of the Context class.

Wire format invariants (preserved across both transports):

- ``elapsed_ms`` integer carried in every emission, basis-stamped at dispatch
  start (``ldd_state_for_call`` ``contextmanager``); falls back to
  process-start when called outside a tool dispatch.
- Text portion (``msg``) capped at :data:`TEXT_CAP` chars with ``…`` elision
  via :func:`format_ldd_line`; both CLI rendering and MCP ``message`` field
  honor the cap so payloads stay terminal-friendly.
- MCP path emits ``ctx.log(level="info", extra={"a2kit_kind": ..., ...})``
- CLI path emits a stderr ``[ +s.mmm <kind>] msg key=val`` line via the same
  shared :func:`format_ldd_line` helper used by ``StderrToolContext._emit``.

Typed events: :class:`EventRegistry` lets a router declare ``MyEvent`` once
(optionally with a progress callback) and then emit instances via
``await app.ldd.events.emit_typed(ctx, evt)`` — handles ``model_dump`` →
``event(...)`` → ``ctx.report_progress(...)`` in a single call.
"""

from __future__ import annotations

import contextlib
import contextvars
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from a2kit.exceptions import ReportTypeMismatch, ReportTypeNotDeclared

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping


#: Process-start timestamp; used as the ``elapsed_ms`` basis when LDD calls
#: happen outside a tool dispatch (e.g. lifecycle hooks).
_APP_START_MONOTONIC: float = time.monotonic()

#: Maximum characters for the ``msg`` portion of an LDD line / log payload.
TEXT_CAP: int = 60


def _cap_text(text: str, cap: int = TEXT_CAP) -> str:
    """Truncate ``text`` to ``cap`` characters, replacing the last with ``…``."""
    if len(text) <= cap:
        return text
    return text[: cap - 1] + "…"


def _format_kv(fields: Mapping[str, Any]) -> str:
    if not fields:
        return ""
    return " ".join(f"{k}={v!r}" if isinstance(v, str) else f"{k}={v}" for k, v in fields.items())


def format_ldd_line(level: str, msg: str, fields: Mapping[str, Any], elapsed_ms: int) -> str:
    """Build the canonical LDD line: ``[ +s.mmm LEVEL] <msg-capped> key=val ...``.

    Used by both the CLI stub (``StderrToolContext._emit``) and any future
    transport that wants byte-identical rendering. ``msg`` is capped at
    :data:`TEXT_CAP` chars; ``fields`` are formatted via Python ``repr`` for
    strings (preserving quotes) and bare-printed for everything else.
    """
    elapsed_s = elapsed_ms / 1000.0
    msg_capped = _cap_text(msg)
    head = f"[ +{elapsed_s:6.3f} {level:<8}]"
    body = f" {msg_capped}" if msg_capped else ""
    kv = _format_kv(fields)
    tail = f" {kv}" if kv else ""
    return head + body + tail


@dataclass
class _LddState:
    events_enabled: bool = True
    reports_enabled: bool = True
    report_type: type | None = None
    tool_name: str | None = None
    start_monotonic: float = field(default_factory=time.monotonic)


_LDD_STATE: contextvars.ContextVar[_LddState | None] = contextvars.ContextVar("_a2kit_ldd_state", default=None)


def _current_state() -> _LddState:
    """Return the active per-call LDD state (or a fresh default outside a call)."""
    state = _LDD_STATE.get()
    if state is None:
        return _LddState(start_monotonic=_APP_START_MONOTONIC)
    return state


def _elapsed_ms() -> int:
    """Integer milliseconds since the active call's basis (or process start)."""
    return round((time.monotonic() - _current_state().start_monotonic) * 1000)


@contextlib.contextmanager
def ldd_state_for_call(
    *,
    events_enabled: bool = True,
    reports_enabled: bool = True,
    report_type: type | None = None,
    tool_name: str | None = None,
) -> Iterator[None]:
    """Set the per-call LDD state for the lifetime of the wrapped block.

    Used by the runtime dispatch sites (CLI ``invoke_tool_sync`` and MCP
    middleware) to scope event/report semantics to a single tool invocation.
    Resets on exit.
    """
    token = _LDD_STATE.set(
        _LddState(
            events_enabled=events_enabled,
            reports_enabled=reports_enabled,
            report_type=report_type,
            tool_name=tool_name,
            start_monotonic=time.monotonic(),
        )
    )
    try:
        yield
    finally:
        _LDD_STATE.reset(token)


def _is_fastmcp_context(ctx: Any) -> bool:
    """Identity check: distinguish real ``fastmcp.Context`` from CLI stub.

    Both expose ``log``, so duck typing isn't sufficient — the CLI stub
    needs the bespoke ``_emit`` wire format, while real ``fastmcp.Context``
    rides ``ctx.log(extra=...)`` notifications. Cold-start preserving:
    only consults ``sys.modules``; if fastmcp hasn't been imported, the
    object can't be a fastmcp Context.
    """
    import sys as _sys

    fastmcp_mod = _sys.modules.get("fastmcp")
    if fastmcp_mod is None:
        return False
    fastmcp_context = getattr(fastmcp_mod, "Context", None)
    if fastmcp_context is None:
        return False
    return isinstance(ctx, fastmcp_context)


async def event(__ctx: Any, __name: str, /, **payload: Any) -> None:
    """Emit a structured event on either transport.

    Positional-only ``ctx`` and event-name args (Python 3.8+ ``/`` syntax)
    so ``**payload`` keys can include ``name``, ``ctx``, etc. without
    colliding — important for typed-event registry emission where the
    payload is a Pydantic model dump.

    MCP path → ``ctx.log(level="info", extra={"a2kit_kind": "event", ...})``.
    CLI path → stderr line via :func:`format_ldd_line` (kind ``event``).

    Honors the events kill-switch set via :func:`ldd_state_for_call` (CLI flag
    ``--no-events``, env ``A2KIT_LDD=off``).
    """
    state = _current_state()
    if not state.events_enabled:
        return
    elapsed = _elapsed_ms()
    if _is_fastmcp_context(__ctx):
        await __ctx.log(
            message=_cap_text(__name),
            level="info",
            extra={
                "a2kit_kind": "event",
                "name": __name,
                "payload": dict(payload),
                "elapsed_ms": elapsed,
            },
        )
    else:
        # CLI stub — internal _emit; preserves the LDD wire format.
        __ctx._emit("event", __name, dict(payload), elapsed_ms=elapsed)  # noqa: SLF001 -- LDD wire format owned here


async def report(ctx: Any, payload: Any, /) -> None:
    """Emit a typed structured report on either transport.

    Validates the payload type against the tool's declared ``@reports(T)``
    even when reports are disabled — keeps tests deterministic regardless of
    LDD flag state.
    """
    state = _current_state()
    if state.report_type is None:
        raise ReportTypeNotDeclared(state.tool_name)
    if not isinstance(payload, state.report_type):
        raise ReportTypeMismatch(state.report_type, type(payload), state.tool_name)
    if not state.reports_enabled:
        return
    elapsed = _elapsed_ms()
    body = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else dict(payload)
    type_name = type(payload).__name__
    if _is_fastmcp_context(ctx):
        await ctx.log(
            message=_cap_text(type_name),
            level="info",
            extra={
                "a2kit_kind": "report",
                "type": type_name,
                "payload": body,
                "elapsed_ms": elapsed,
            },
        )
    else:
        ctx._emit("report", type_name, body, elapsed_ms=elapsed)  # noqa: SLF001 -- LDD wire format owned here


# --- Typed event registry --------------------------------------------------- #

ProgressFn = "Callable[[Any], tuple[float, float | None]]"


class EventRegistry:
    """Registry of typed event models with optional progress callbacks.

    Routers register Pydantic models once at module load
    (``app.ldd.events.register(MyEvent, progress=lambda e: (e.done, e.total))``)
    and emit instances via ``await app.ldd.events.emit_typed(ctx, evt)``.

    ``emit_typed`` does three things:

    1. ``payload = evt.model_dump(mode="json")`` (datetime → ISO, etc.)
    2. ``await event(ctx, type(evt).__name__, **payload)``
    3. If a progress callback is registered, ``await ctx.report_progress(...)``

    Re-registering a model **replaces** the prior progress callback
    (last-write-wins) — keeps test fixtures simple, no warnings.
    """

    __slots__ = ("_progress",)

    def __init__(self) -> None:
        self._progress: dict[type, Callable[[Any], tuple[float, float | None]] | None] = {}

    def register(
        self,
        model: type,
        *,
        progress: Callable[[Any], tuple[float, float | None]] | None = None,
    ) -> None:
        """Register ``model`` (last-write-wins on the optional progress callback)."""
        self._progress[model] = progress

    def is_registered(self, model: type) -> bool:
        return model in self._progress

    async def emit_typed(self, ctx: Any, evt: Any) -> None:
        """Emit ``evt`` as a structured event + optional progress update."""
        dumped: dict[str, Any] = evt.model_dump(mode="json") if hasattr(evt, "model_dump") else dict(evt)
        await event(ctx, type(evt).__name__, **dumped)
        progress_fn = self._progress.get(type(evt))
        if progress_fn is not None:
            current, total = progress_fn(evt)
            await ctx.report_progress(current, total)


class _AppLdd:
    """Namespace mounted on :class:`a2kit.App` as ``app.ldd``.

    Currently exposes ``events: EventRegistry``. Kept as a small object so
    future LDD facets (e.g. structured-log filters) can be added without
    cluttering the App namespace.
    """

    __slots__ = ("events",)

    def __init__(self) -> None:
        self.events = EventRegistry()


__all__ = [
    "TEXT_CAP",
    "EventRegistry",
    "_AppLdd",
    "event",
    "format_ldd_line",
    "ldd_state_for_call",
    "report",
]
