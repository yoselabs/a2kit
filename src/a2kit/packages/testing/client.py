"""In-process test client — runs the full dispatcher with capture surfaces.

Round-2 a2web feedback (item 7): every consumer today bypasses a2kit's
dispatcher in tests, leaving the adapter layer (DI, schema, ctx wiring,
rendering, error envelope) untested. This client invokes tools through the
**same** dispatch path as production (same DI hook, same `_invoke_tool_in_process`
machinery) with the live ToolContext replaced by a capturing variant whose
`_emit` writes into per-instance buffers instead of stderr.

Cold-start preserving: the module is lazy-imported via
:mod:`a2kit.testing` and never pulled by a bare ``import a2kit``.

Example::

    async with a2kit.testing.client(app) as c:
        result = await c.invoke("tasks.create_project", name="P1")
        assert any(e["name"] == "ProjectCreated" for e in c.events)
        assert c.progress[-1] == (1.0, 1.0)
        assert c.render_as("json", result) == {...}
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from a2kit.packages.cli.context import StderrToolContext
from a2kit.packages.formatter import FormatHint, format_response

if TYPE_CHECKING:
    from collections.abc import Mapping

    from a2kit.app import App
    from a2kit.tool import ToolDescriptor


class _CapturingContext(StderrToolContext):
    """``StderrToolContext`` subclass that captures emissions into lists.

    The base class's ``_emit`` would print to stderr; we override it to
    append a structured dict. Logging methods (``info``/``warning``/...) and
    ``log`` continue to delegate to ``_emit`` via the parent class, so they
    land in ``logs`` automatically. ``report_progress`` also routes through
    ``_emit`` (level=``"progress"``); we additionally capture a tidy
    ``(current, total)`` tuple so tests don't have to parse fields.
    """

    def __init__(
        self,
        *,
        events: list[dict[str, Any]],
        progress: list[tuple[float, float | None]],
        logs: list[dict[str, Any]],
        reports: list[dict[str, Any]],
    ) -> None:
        super().__init__()
        self._events = events
        self._progress = progress
        self._logs = logs
        self._reports = reports

    async def report_progress(
        self,
        progress: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        self._progress.append((progress, total))
        await super().report_progress(progress, total, message)

    def _emit(
        self,
        level: str,
        msg: str,
        fields: Mapping[str, Any],
        *,
        elapsed_ms: int | None = None,
    ) -> None:
        # No stderr write — capture only.
        if elapsed_ms is None:
            elapsed_ms = round((time.monotonic() - self._start_ts) * 1000)
        record = {"level": level, "msg": msg, "fields": dict(fields), "elapsed_ms": elapsed_ms}
        if level == "event":
            # Event payload shape mirrors the LDD wire format: `msg` is the event
            # name and `fields` is the payload dict.
            self._events.append({"name": msg, "payload": dict(fields), "elapsed_ms": elapsed_ms})
        elif level == "progress":
            # Progress is captured separately via report_progress; suppress the
            # _emit-level duplicate from logs to keep assertions clean.
            return
        elif level == "report":
            # Report path: `msg` is the type name; `fields` is the model_dump body.
            self._reports.append({"type": msg, "body": dict(fields), "elapsed_ms": elapsed_ms})
        else:
            self._logs.append(record)


class TestClient:
    """In-process test client — capture-only ToolContext, full dispatcher."""

    def __init__(self, app: App) -> None:
        self.app = app
        self.events: list[dict[str, Any]] = []
        self.progress: list[tuple[float, float | None]] = []
        self.logs: list[dict[str, Any]] = []
        self.reports: list[dict[str, Any]] = []
        self._lifecycle_started = False

    async def __aenter__(self) -> TestClient:
        if self.app.has_lifecycle_handlers() and not self.app._lifecycle_started:  # noqa: SLF001
            from a2kit.app import dispatch_startup

            self.app._lifecycle_started = True  # noqa: SLF001
            self._lifecycle_started = True
            await dispatch_startup(self.app)
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._lifecycle_started:
            from a2kit.app import dispatch_shutdown

            await dispatch_shutdown(self.app)
            self.app._lifecycle_started = False  # noqa: SLF001 -- reset for re-entry

    def tools(self) -> list[ToolDescriptor]:
        """Return tool descriptors, sorted by name."""
        return sorted(self.app.tool_descriptors(), key=lambda d: d.name)

    def render_as(self, fmt: str, value: Any) -> Any:
        """Render ``value`` through the same formatter the transports use."""
        response = format_response(value, format_hint=cast("FormatHint", fmt))
        return response.data

    async def invoke(
        self,
        tool_name: str,
        *,
        connection: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Invoke ``tool_name`` through the dispatcher; return the tool's value.

        Looks up the descriptor by `name`, sets up `ldd_state_for_call` with the
        capturing context bound, runs the dispatch hook (DI resolution), and
        invokes the underlying function. Reports captured into ``self.reports``
        via a monkey-patched ``report`` hook for the duration of the call.
        """
        from a2kit.ldd import ldd_state_for_call

        descriptor = self._descriptor(tool_name)
        fn = descriptor.fn
        meta = _meta_for(fn)

        ctx = _CapturingContext(
            events=self.events,
            progress=self.progress,
            logs=self.logs,
            reports=self.reports,
        )
        kwargs_for_call: dict[str, Any] = dict(kwargs)
        if connection is not None and "connection" not in kwargs_for_call:
            kwargs_for_call["connection"] = connection
        if meta.context_param_name and meta.context_param_name not in kwargs_for_call:
            kwargs_for_call[meta.context_param_name] = ctx

        # Reports go through `a2kit.ldd.report(ctx, payload)` which routes via
        # `_is_fastmcp_context` → CLI path → `ctx._emit("report", type_name, body)`.
        # The capturing context's `_emit` branch on `level == "report"` writes to
        # `self.reports`, so we don't need to monkey-patch the report function.
        report_type = meta.extra.get("a2kit.report_type") if meta.extra else None

        with ldd_state_for_call(
            events_enabled=True,
            reports_enabled=True,
            report_type=report_type,
            tool_name=tool_name,
            sinks=self.app.ldd.sinks if hasattr(self.app, "ldd") else (),
        ):
            return await _invoke_through_dispatcher(
                self.app,
                fn,
                kwargs_for_call,
                ctx_param_name=meta.context_param_name,
            )

    # --- internals ----------------------------------------------------- #

    def _descriptor(self, tool_name: str) -> ToolDescriptor:
        for d in self.app.tool_descriptors():
            if d.name == tool_name or _qualified(d) == tool_name:
                return d
        available = sorted(d.name for d in self.app.tool_descriptors())
        raise KeyError(f"tool {tool_name!r} not found. Available: {available}")


def _qualified(descriptor: ToolDescriptor) -> str:
    """Return ``<router-slug>.<tool-name>`` if the router has a slug."""
    slug = getattr(descriptor.router, "slug", None)
    return f"{slug}.{descriptor.name}" if slug else descriptor.name


def _meta_for(fn: Any) -> Any:
    from a2kit.metadata import get_meta

    return get_meta(fn)


async def _invoke_through_dispatcher(
    app: App,
    fn: Any,
    kwargs: dict[str, Any],
    *,
    ctx_param_name: str | None,
) -> Any:
    """Run the dispatch hook (DI resolution) and call ``fn`` with the resolved kwargs.

    Mirrors the dispatch step of :func:`a2kit.packages.cli.runtime._invoke_tool_in_process`
    but returns the raw value (no formatter).
    """
    import inspect

    hook = app._dispatch_hook  # noqa: SLF001 -- intentional, dispatch hook is App-scoped
    resolved_any: Any = hook(fn, kwargs)
    if inspect.isawaitable(resolved_any):
        resolved_any = await resolved_any
    call_kwargs = dict(resolved_any)
    if ctx_param_name and ctx_param_name not in call_kwargs and ctx_param_name in kwargs:
        call_kwargs[ctx_param_name] = kwargs[ctx_param_name]
    if inspect.iscoroutinefunction(fn):
        result = await fn(**call_kwargs)
    else:
        result = fn(**call_kwargs)
        if inspect.isawaitable(result):
            result = await result
    return result


def client(app: App) -> TestClient:
    """Construct a test client; use as ``async with client(app) as c: ...``."""
    return TestClient(app)


__all__ = ["TestClient", "client"]
