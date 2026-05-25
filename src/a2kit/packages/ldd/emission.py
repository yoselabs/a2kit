"""LDD emission primitives — protocol-neutral free functions.

Tools call :func:`event`, :func:`report`, :func:`log` (and the
``info`` / ``warning`` / ``error`` / ``debug`` shorthands) with **no**
``ctx`` argument. The live context is bound to the ambient ``_LDD_STATE``
ContextVar by the runtime dispatch site for the lifetime of one tool
invocation; the primitives read it from there. Calling a primitive outside
an active dispatch raises :exc:`a2kit.exceptions.AmbientContextMissing` —
fail loud, never silently no-op.

Wire format invariants (preserved across both transports):

- ``elapsed_ms`` integer carried in every emission, basis-stamped at dispatch
  start (``ldd_state_for_call``); see :mod:`a2kit.packages.ldd.ambient`.
- Text portion (``msg``) capped at :data:`a2kit.packages.ldd.wire.TEXT_CAP`
  chars via :func:`a2kit.packages.ldd.wire.format_ldd_line`.
- MCP path emits ``ctx.log(level="info", extra={"a2kit_kind": ..., ...})``.
- CLI path emits a stderr ``[ +s.mmm <kind>] msg key=val`` line.

Typed events: :class:`EventRegistry` lets a router declare ``MyEvent`` once
(optionally with a progress callback) and then emit instances via
``await app.ldd.events.emit_typed(evt)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from a2kit.exceptions import ReportTypeMismatch, ReportTypeNotDeclared
from a2kit.packages.ldd.ambient import _elapsed_ms_from, _is_fastmcp_context, _require_ambient_state
from a2kit.packages.ldd.levels import LDD_LEVEL_RANK, LddLevel
from a2kit.packages.ldd.sinks import LddEmission, LddSink, _dispatch_sinks
from a2kit.packages.ldd.wire import _cap_text


def _below_threshold(level: LddLevel, threshold: int) -> bool:
    """Return True when ``level``'s rank is strictly below ``threshold``."""
    return LDD_LEVEL_RANK[level] < threshold


if TYPE_CHECKING:
    from collections.abc import Callable


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


async def event(__name_or_payload: Any, /, *, level: LddLevel = "info", **payload: Any) -> None:
    """Emit a structured event on either transport. Reads ``ctx`` from the
    ambient ``_LDD_STATE`` set by the dispatcher.

    Two call shapes:

    1. **Kwargs form**: ``event("name.string", key=value, ...)``. First
       positional is the event name string; kwargs form the payload.
    2. **Typed form**: ``event(instance)``. First positional is any class
       instance. Name defaults to ``type(instance).__name__``. The payload
       is derived from the instance:

       - ``instance.model_dump(mode="json")`` if it has ``model_dump``.
       - ``dataclasses.asdict(instance)`` if a dataclass instance.
       - ``vars(instance)`` as a fallback.

       Any ``Enum`` value is replaced by ``.value``. An optional ``name=``
       kwarg overrides the default class-name. Additional kwargs are
       merged into the payload after the instance fields (caller wins on
       key collisions).

    MCP path → ``ctx.log(level="info", extra={"a2kit_kind": "event", ...})``.
    CLI path → stderr line via ``format_ldd_line`` (kind ``event``).

    Honors the events kill-switch set via ``ldd_state_for_call``
    (CLI flag ``--no-events``, env ``A2KIT_LDD__ENABLED=false``). Raises
    :exc:`AmbientContextMissing` if called outside an active dispatch.
    """
    state = _require_ambient_state("a2kit.ldd.event")
    if not state.events_enabled:
        return
    if _below_threshold(level, state.level_threshold):
        return
    ctx = state.ctx
    elapsed = _elapsed_ms_from(state)

    if isinstance(__name_or_payload, str):
        __name = __name_or_payload
        payload_dict = dict(payload)
    else:
        __name, payload_dict = _typed_event_to_payload(__name_or_payload, payload)
    if _is_fastmcp_context(ctx):
        # Prefix a2kit-internal keys with `a2kit_` to dodge Python
        # `LogRecord` reserved attribute names. FastMCP's
        # `_log_to_server_and_client` passes `extra` to a Python logger
        # as a server-side side-effect; reserved keys (`name`, `msg`,
        # `levelname`, ...) crash `logging.makeRecord`. See
        # `rebuild-test-client-on-real-context` design D-LDD-WIRE-PREFIX.
        await ctx.log(
            message=_cap_text(__name),
            level="info",
            extra={
                "a2kit_kind": "event",
                "a2kit_name": __name,
                "a2kit_payload": payload_dict,
                "a2kit_elapsed_ms": elapsed,
            },
        )
    else:
        ctx._emit("event", __name, payload_dict, elapsed_ms=elapsed)  # noqa: SLF001 -- LDD wire format owned here
    if state.sinks:
        await _dispatch_sinks(
            LddEmission(
                kind="event",
                name=__name,
                payload=payload_dict,
                elapsed_ms=elapsed,
                tool_name=state.tool_name,
                ctx=ctx,
            ),
            state.sinks,
        )


async def report(payload: Any, /, *, level: LddLevel = "info") -> None:
    """Emit a typed structured report on either transport. Reads ``ctx``
    from the ambient ``_LDD_STATE``.

    Validates the payload type against the tool's declared ``@reports(T)``
    even when reports are disabled — keeps tests deterministic regardless
    of LDD flag state. Raises :exc:`AmbientContextMissing` if called
    outside an active dispatch.
    """
    state = _require_ambient_state("a2kit.ldd.report")
    if state.report_type is None:
        raise ReportTypeNotDeclared(state.tool_name)
    if not isinstance(payload, state.report_type):
        raise ReportTypeMismatch(state.report_type, type(payload), state.tool_name)
    if not state.reports_enabled:
        return
    if _below_threshold(level, state.level_threshold):
        return
    ctx = state.ctx
    elapsed = _elapsed_ms_from(state)
    body = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else dict(payload)
    type_name = type(payload).__name__
    if _is_fastmcp_context(ctx):
        # See `event` for the prefix rationale.
        await ctx.log(
            message=_cap_text(type_name),
            level="info",
            extra={
                "a2kit_kind": "report",
                "a2kit_type": type_name,
                "a2kit_payload": body,
                "a2kit_elapsed_ms": elapsed,
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


_LOG_LEVEL_LABEL: dict[str, str] = {
    "trace": "TRACE",
    "debug": "DEBUG",
    "info": "INFO",
    "warning": "WARN",
    "error": "ERROR",
}

#: MCP's wire-level vocabulary (debug/info/warning/error). The a2kit-internal
#: ``"trace"`` level has no MCP counterpart, so it maps to ``"debug"`` on the
#: wire — clients see debug; the framework still tracks it as trace internally.
_MCP_LOG_LEVEL: dict[str, Literal["debug", "info", "warning", "error"]] = {
    "trace": "debug",
    "debug": "debug",
    "info": "info",
    "warning": "warning",
    "error": "error",
}


async def log(
    __level: LddLevel,
    __msg_or_instance: Any,
    /,
    **fields: Any,
) -> None:
    """Emit a structured field-bearing log line on either transport. Reads
    ``ctx`` from the ambient ``_LDD_STATE``.

    Two call shapes:

    1. **String form**: ``log("info", "msg", k=v, ...)``. Second positional
       is the message; remaining kwargs are fields.
    2. **Instance form**: ``log("info", instance)``. Second positional is a
       dataclass / pydantic ``BaseModel`` / object. Message defaults to
       ``type(instance).__name__``; fields derive via ``model_dump``
       (pydantic), ``dataclasses.asdict`` (dataclass), or
       ``vars(instance)`` (fallback). Enum values are unwrapped to
       ``.value``.

    MCP path → ``await ctx.log(level=..., message=msg_capped, extra={**fields, "elapsed_ms": ...})``.
    CLI path → ``ctx._emit(LEVEL, msg, fields, elapsed_ms=...)`` (same
    backend that ``StderrToolContext.info/warning/error/debug`` use).

    Shares the events kill-switch (``--no-events`` / ``A2KIT_LDD__ENABLED=false``).
    Raises :exc:`AmbientContextMissing` if called outside an active dispatch.
    """
    state = _require_ambient_state("a2kit.ldd.log")
    if not state.events_enabled:
        return
    if _below_threshold(__level, state.level_threshold):
        return
    ctx = state.ctx
    elapsed = _elapsed_ms_from(state)

    if isinstance(__msg_or_instance, str):
        msg = __msg_or_instance
        payload_dict = dict(fields)
    else:
        msg, payload_dict = _typed_event_to_payload(__msg_or_instance, dict(fields))

    if _is_fastmcp_context(ctx):
        # Prefix only the a2kit-internal `elapsed_ms` key; user-supplied
        # fields stay un-prefixed (users sanitizing their own keys is on
        # them, not the framework). See `event` for the rationale.
        wire_extra = {**payload_dict, "a2kit_elapsed_ms": elapsed}
        await ctx.log(level=_MCP_LOG_LEVEL[__level], message=_cap_text(msg), extra=wire_extra)
    else:
        ctx._emit(_LOG_LEVEL_LABEL[__level], msg, payload_dict, elapsed_ms=elapsed)  # noqa: SLF001 -- LDD wire format owned here

    if state.sinks:
        await _dispatch_sinks(
            LddEmission(
                kind="log",
                name=msg,
                payload=payload_dict,
                elapsed_ms=elapsed,
                tool_name=state.tool_name,
                ctx=ctx,
            ),
            state.sinks,
        )


async def info(__msg_or_instance: Any, /, **fields: Any) -> None:
    """``a2kit.ldd.log("info", ...)`` shorthand."""
    _require_ambient_state("a2kit.ldd.info")
    await log("info", __msg_or_instance, **fields)


async def warning(__msg_or_instance: Any, /, **fields: Any) -> None:
    """``a2kit.ldd.log("warning", ...)`` shorthand."""
    _require_ambient_state("a2kit.ldd.warning")
    await log("warning", __msg_or_instance, **fields)


async def error(__msg_or_instance: Any, /, **fields: Any) -> None:
    """``a2kit.ldd.log("error", ...)`` shorthand."""
    _require_ambient_state("a2kit.ldd.error")
    await log("error", __msg_or_instance, **fields)


async def debug(__msg_or_instance: Any, /, **fields: Any) -> None:
    """``a2kit.ldd.log("debug", ...)`` shorthand."""
    _require_ambient_state("a2kit.ldd.debug")
    await log("debug", __msg_or_instance, **fields)


class EventRegistry:
    """Registry of typed event models with optional progress callbacks.

    Routers register Pydantic models once at module load
    (``app.ldd.events.register(MyEvent, progress=lambda e: (e.done, e.total))``)
    and emit instances via ``await app.ldd.events.emit_typed(evt)``.

    ``emit_typed`` does three things:

    1. ``payload = evt.model_dump(mode="json")`` (datetime → ISO, etc.)
    2. ``await event(type(evt).__name__, **payload)``
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

    async def emit_typed(self, evt: Any) -> None:
        """Emit ``evt`` as a structured event + optional progress update.

        Reads ``ctx`` from the ambient ``_LDD_STATE``. The progress
        callback path uses the same ambient ctx — call from inside a
        tool dispatch only.
        """
        dumped: dict[str, Any] = evt.model_dump(mode="json") if hasattr(evt, "model_dump") else dict(evt)
        await event(type(evt).__name__, **dumped)
        progress_fn = self._progress.get(type(evt))
        if progress_fn is not None:
            state = _require_ambient_state("EventRegistry.emit_typed")
            current, total = progress_fn(evt)
            await state.ctx.report_progress(current, total)


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
