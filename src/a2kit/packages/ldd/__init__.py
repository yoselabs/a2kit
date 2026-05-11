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
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

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


#: Logger for sink-fan-out failures. Sinks that raise are caught here so a
#: bad sink can't break tool dispatch (see ``_dispatch_sinks``).
_SINK_LOGGER = logging.getLogger("a2kit.ldd.sinks")


@dataclass(frozen=True, slots=True)
class LddEmission:
    """Structured payload delivered to in-process LDD sinks.

    Built by :func:`event` / :func:`report` after their wire emit, then
    fan-out to each sink registered on ``app.ldd.add_sink(...)``.
    """

    kind: Literal["event", "report", "log"]
    name: str
    payload: dict[str, Any]
    elapsed_ms: int
    tool_name: str | None
    ctx: Any


class LddSink(Protocol):
    """Async callable that observes :class:`LddEmission` payloads.

    Registered via ``app.ldd.add_sink(sink)``. Invoked sequentially after
    each wire emit, in registration order. Sink exceptions are caught
    and logged on ``a2kit.ldd.sinks``; one bad sink never breaks tool
    dispatch.

    Sinks SHOULD return quickly — fan-out is sequential, so a slow sink
    delays the next emit. For heavy work (network export, batched writes),
    push to a queue from the sink and process out-of-band.
    """

    async def __call__(self, emission: LddEmission, /) -> None: ...


async def _dispatch_sinks(emission: LddEmission, sinks: tuple[LddSink, ...]) -> None:
    """Fan ``emission`` out to ``sinks`` sequentially; isolate exceptions."""
    for sink in sinks:
        try:
            await sink(emission)
        except Exception:
            _SINK_LOGGER.exception(
                "LDD sink %r raised; continuing",
                getattr(sink, "__name__", repr(sink)),
            )


@dataclass
class _LddState:
    events_enabled: bool = True
    reports_enabled: bool = True
    report_type: type | None = None
    tool_name: str | None = None
    start_monotonic: float = field(default_factory=time.monotonic)
    sinks: tuple[LddSink, ...] = ()


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
    sinks: tuple[LddSink, ...] = (),
) -> Iterator[None]:
    """Set the per-call LDD state for the lifetime of the wrapped block.

    Used by the runtime dispatch sites (CLI ``invoke_tool_sync`` and MCP
    middleware) to scope event/report semantics to a single tool invocation.
    Resets on exit.

    ``sinks`` is the tuple of in-process observers registered on the App via
    ``app.ldd.add_sink(...)``; :func:`event` and :func:`report` fan out to
    each after the wire emit.
    """
    token = _LDD_STATE.set(
        _LddState(
            events_enabled=events_enabled,
            reports_enabled=reports_enabled,
            report_type=report_type,
            tool_name=tool_name,
            start_monotonic=time.monotonic(),
            sinks=sinks,
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


def _typed_event_to_payload(instance: Any, extra: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Serialize an event instance to ``(name, payload_dict)``.

    Used by :func:`event`'s typed path. Honors a ``name=`` override pulled
    out of ``extra``; remaining ``extra`` kwargs are merged into the payload
    after the instance fields (caller wins on collisions).
    """
    import dataclasses
    from enum import Enum

    name_override = extra.pop("name", None)
    name = name_override if isinstance(name_override, str) else type(instance).__name__

    if hasattr(instance, "model_dump"):
        payload_dict = instance.model_dump(mode="json")
    elif dataclasses.is_dataclass(instance) and not isinstance(instance, type):
        payload_dict = dataclasses.asdict(instance)
    else:
        try:
            payload_dict = dict(vars(instance))
        except TypeError:
            payload_dict = {}

    # Enum → enum.value (recursive shallow walk for top-level fields).
    payload_dict = {k: (v.value if isinstance(v, Enum) else v) for k, v in payload_dict.items()}

    # Merge extra kwargs after instance fields; caller wins on collisions.
    payload_dict.update(extra)
    return name, payload_dict


async def event(__ctx: Any, __name_or_payload: Any, /, **payload: Any) -> None:
    """Emit a structured event on either transport.

    Two call shapes are accepted (positional-only ``ctx`` and the second arg
    via ``/`` syntax keep ``**payload`` open for any key including ``name``):

    1. **Kwargs form** (legacy): ``event(ctx, "name.string", key=value, ...)``.
       Second positional is the event name string; remaining kwargs form the
       payload.
    2. **Typed form**: ``event(ctx, instance)``. Second positional is any
       class instance. Name defaults to ``type(instance).__name__``. The
       payload is derived from the instance:

       - ``instance.model_dump(mode="json")`` if it has ``model_dump``
         (pydantic ``BaseModel``).
       - ``dataclasses.asdict(instance)`` if a dataclass instance.
       - ``vars(instance)`` as a fallback.

       Any ``Enum`` value in the resulting dict is replaced by
       ``value.value`` so wire payloads stay JSON-friendly.

       An optional ``name=`` kwarg overrides the default class-name. Any
       additional kwargs are merged into the payload after the instance
       fields (caller wins on key collisions).

    MCP path → ``ctx.log(level="info", extra={"a2kit_kind": "event", ...})``.
    CLI path → stderr line via :func:`format_ldd_line` (kind ``event``).

    Honors the events kill-switch set via :func:`ldd_state_for_call` (CLI flag
    ``--no-events``, env ``A2KIT_LDD=off``).
    """
    state = _current_state()
    if not state.events_enabled:
        return
    elapsed = _elapsed_ms()

    if isinstance(__name_or_payload, str):
        __name = __name_or_payload
        payload_dict = dict(payload)
    else:
        __name, payload_dict = _typed_event_to_payload(__name_or_payload, payload)
    if _is_fastmcp_context(__ctx):
        await __ctx.log(
            message=_cap_text(__name),
            level="info",
            extra={
                "a2kit_kind": "event",
                "name": __name,
                "payload": payload_dict,
                "elapsed_ms": elapsed,
            },
        )
    else:
        # CLI stub — internal _emit; preserves the LDD wire format.
        __ctx._emit("event", __name, payload_dict, elapsed_ms=elapsed)  # noqa: SLF001 -- LDD wire format owned here
    if state.sinks:
        await _dispatch_sinks(
            LddEmission(
                kind="event",
                name=__name,
                payload=payload_dict,
                elapsed_ms=elapsed,
                tool_name=state.tool_name,
                ctx=__ctx,
            ),
            state.sinks,
        )


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
    if state.sinks:
        await _dispatch_sinks(
            LddEmission(
                kind="report",
                name=type_name,
                payload=body,
                elapsed_ms=elapsed,
                tool_name=state.tool_name,
                ctx=ctx,
            ),
            state.sinks,
        )


_LOG_LEVEL_LABEL: dict[str, str] = {"debug": "DEBUG", "info": "INFO", "warning": "WARN", "error": "ERROR"}


async def log(
    __ctx: Any,
    __level: Literal["debug", "info", "warning", "error"],
    __msg_or_instance: Any,
    /,
    **fields: Any,
) -> None:
    """Emit a structured field-bearing log line on either transport.

    Third sibling of :func:`event` and :func:`report`; the missing
    protocol-neutral primitive for narrative-with-data logging. Two
    call shapes (mirrors :func:`event` verbatim, shares the same
    ``_typed_event_to_payload`` helper):

    1. **String form**: ``log(ctx, "info", "msg", k=v, ...)``. Third
       positional is the message; remaining kwargs are fields.
    2. **Instance form**: ``log(ctx, "info", instance)``. Third positional
       is a dataclass / pydantic ``BaseModel`` / object. Message defaults
       to ``type(instance).__name__``; fields derive via ``model_dump``
       (pydantic), ``dataclasses.asdict`` (dataclass), or ``vars(instance)``
       (fallback). Enum values are unwrapped to ``.value``.

    MCP path → ``await ctx.log(level=..., message=msg_capped, extra={**fields, "elapsed_ms": ...})``.
    CLI path → ``ctx._emit(LEVEL, msg, fields, elapsed_ms=...)`` (same backend
    that ``StderrToolContext.info/warning/error/debug`` use).

    Shares the events kill-switch (``--no-events`` / ``A2KIT_LDD=off``) so
    a single flag silences all three LDD primitives consistently.
    """
    state = _current_state()
    if not state.events_enabled:
        return
    elapsed = _elapsed_ms()

    if isinstance(__msg_or_instance, str):
        msg = __msg_or_instance
        payload_dict = dict(fields)
    else:
        msg, payload_dict = _typed_event_to_payload(__msg_or_instance, dict(fields))

    if _is_fastmcp_context(__ctx):
        wire_extra = {**payload_dict, "elapsed_ms": elapsed}
        await __ctx.log(level=__level, message=_cap_text(msg), extra=wire_extra)
    else:
        __ctx._emit(_LOG_LEVEL_LABEL[__level], msg, payload_dict, elapsed_ms=elapsed)  # noqa: SLF001 -- LDD wire format owned here

    if state.sinks:
        await _dispatch_sinks(
            LddEmission(
                kind="log",
                name=msg,
                payload=payload_dict,
                elapsed_ms=elapsed,
                tool_name=state.tool_name,
                ctx=__ctx,
            ),
            state.sinks,
        )


async def info(__ctx: Any, __msg_or_instance: Any, /, **fields: Any) -> None:
    """``a2kit.ldd.log(ctx, "info", ...)`` shorthand."""
    await log(__ctx, "info", __msg_or_instance, **fields)


async def warning(__ctx: Any, __msg_or_instance: Any, /, **fields: Any) -> None:
    """``a2kit.ldd.log(ctx, "warning", ...)`` shorthand."""
    await log(__ctx, "warning", __msg_or_instance, **fields)


async def error(__ctx: Any, __msg_or_instance: Any, /, **fields: Any) -> None:
    """``a2kit.ldd.log(ctx, "error", ...)`` shorthand."""
    await log(__ctx, "error", __msg_or_instance, **fields)


async def debug(__ctx: Any, __msg_or_instance: Any, /, **fields: Any) -> None:
    """``a2kit.ldd.log(ctx, "debug", ...)`` shorthand."""
    await log(__ctx, "debug", __msg_or_instance, **fields)


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

    Exposes:

    - ``events: EventRegistry`` — typed event registration + emission.
    - ``add_sink`` / ``remove_sink`` / ``sinks`` — in-process observer
      registration. Each registered sink receives every :class:`LddEmission`
      after the wire emit, in registration order. See :class:`LddSink`.
    """

    __slots__ = ("_sinks", "events")

    def __init__(self) -> None:
        self.events = EventRegistry()
        self._sinks: list[LddSink] = []

    def add_sink(self, sink: LddSink) -> None:
        """Append ``sink`` to the App's sink list.

        Idempotent on identity: re-adding the same sink object appends a
        second registration (the sink will be invoked twice per emission).
        Pass a wrapper if you need de-duplication.
        """
        self._sinks.append(sink)

    def remove_sink(self, sink: LddSink) -> None:
        """Remove ``sink`` from the App's sink list. Raises if not registered."""
        self._sinks.remove(sink)

    @property
    def sinks(self) -> tuple[LddSink, ...]:
        """Immutable snapshot of currently registered sinks."""
        return tuple(self._sinks)


__all__ = [
    "TEXT_CAP",
    "EventRegistry",
    "LddEmission",
    "LddSink",
    "_AppLdd",
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
