"""OTel span helpers — for the @tool wrapper and for plugin authors.

Lazy-imported so consumers without the `[otel]` extra don't pay the import.
Detects a real (non-default) tracer provider; if none, returns a no-op span.

Public surface:

- `otel_span(tool_name, connection_key, write)` — context manager used by
  the @tool decorator. Falls back to `_NullSpan` if OTel unavailable.
- `get_tracer()` (v0.12) — cached, returns the a2kit tracer. Plugins call
  this instead of `from opentelemetry import trace; trace.get_tracer(...)`.
- `plugin_span(name, **attrs)` (v0.12) — context manager that opens
  `a2kit.plugin.{name}` as a child of the current span. Falls back to
  `_NullSpan` if no real provider is configured.
"""

from __future__ import annotations

from typing import Any


class _NullSpan:
    """No-op CM used when OTel isn't installed/configured."""

    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _OTelWrapper:
    """Adapter that sets `tool.*` attributes on the entered span."""

    def __init__(self, cm: Any, tool_name: str, connection_key: tuple[str, ...] | None, write: bool) -> None:
        self._cm = cm
        self._span: Any = None
        self._tool_name = tool_name
        self._connection_key = connection_key
        self._write = write

    def __enter__(self) -> _OTelWrapper:
        self._span = self._cm.__enter__()
        if self._span is not None and hasattr(self._span, "set_attribute"):
            self._span.set_attribute("tool.name", self._tool_name)
            self._span.set_attribute("tool.write", self._write)
            if self._connection_key is not None:
                self._span.set_attribute("tool.connection", "-".join(self._connection_key))
        return self

    def __exit__(self, *exc: object) -> None:
        self._cm.__exit__(*exc)


def otel_span(tool_name: str, connection_key: tuple[str, ...] | None, write: bool) -> Any:
    """Return an OTel span CM, or a `_NullSpan` if OTel isn't installed/configured.

    Detection: if the active tracer provider is FastMCP's default
    `ProxyTracerProvider` (or the SDK's `NoOpTracerProvider`), we treat that as
    "no provider" and return a no-op. Once a real provider is set, we open a
    span named `a2kit.tool.<tool_name>` and stamp the standard attributes.
    """
    try:
        from opentelemetry import trace  # noqa: PLC0415
    except ImportError:
        return _NullSpan()

    provider = trace.get_tracer_provider()
    if provider.__class__.__name__ in {"ProxyTracerProvider", "NoOpTracerProvider"}:
        return _NullSpan()

    tracer = trace.get_tracer("a2kit")
    span_cm = tracer.start_as_current_span(f"a2kit.tool.{tool_name}")
    return _OTelWrapper(span_cm, tool_name, connection_key, write)


_TRACER_CACHE: dict[str, Any] = {}


def get_tracer() -> Any:
    """Return the a2kit OTel tracer (or a no-op tracer if OTel isn't installed).

    Cached after first call. Plugins use this to open child spans without
    importing `opentelemetry` themselves. Always safe to call.
    """
    if "tracer" in _TRACER_CACHE:
        return _TRACER_CACHE["tracer"]
    try:
        from opentelemetry import trace  # noqa: PLC0415

        tracer = trace.get_tracer("a2kit")
    except ImportError:
        tracer = _NoOpTracer()
    _TRACER_CACHE["tracer"] = tracer
    return tracer


def plugin_span(name: str, **attrs: Any) -> Any:
    """Open `a2kit.plugin.{name}` as a child of the current span.

    Sets `a2kit.plugin.name = {name}` plus any caller-supplied attrs.
    Returns a `_NullSpan` if no real OTel provider is configured (so plugin
    authors can sprinkle `with plugin_span("connections.load", key=key):`
    without conditional checks).

    Usage:
        async def get(self, key: tuple[str, ...]) -> JiraConn:
            with a2kit.plugin_span("connections.load", connection_key="-".join(key)):
                return await self._load_from_disk(key)
    """
    try:
        from opentelemetry import trace  # noqa: PLC0415
    except ImportError:
        return _NullSpan()

    provider = trace.get_tracer_provider()
    if provider.__class__.__name__ in {"ProxyTracerProvider", "NoOpTracerProvider"}:
        return _NullSpan()

    tracer = get_tracer()
    span_cm = tracer.start_as_current_span(f"a2kit.plugin.{name}")
    return _PluginSpanWrapper(span_cm, name, attrs)


class _PluginSpanWrapper:
    """Adapter that stamps `a2kit.plugin.name` + caller attrs on entry."""

    def __init__(self, cm: Any, name: str, attrs: dict[str, Any]) -> None:
        self._cm = cm
        self._span: Any = None
        self._name = name
        self._attrs = attrs

    def __enter__(self) -> _PluginSpanWrapper:
        self._span = self._cm.__enter__()
        if self._span is not None and hasattr(self._span, "set_attribute"):
            self._span.set_attribute("a2kit.plugin.name", self._name)
            for key, value in self._attrs.items():
                self._span.set_attribute(key, value)
        return self

    def __exit__(self, *exc: object) -> None:
        self._cm.__exit__(*exc)


class _NoOpTracer:
    """Stand-in for `opentelemetry.trace.Tracer` when OTel isn't installed.

    Provides `start_as_current_span` returning a `_NullSpan`. Plugins that
    cache the tracer at startup don't have to special-case the OTel-missing
    branch — the cached object is duck-compatible.
    """

    def start_as_current_span(self, _name: str, *_args: Any, **_kwargs: Any) -> Any:
        return _NullSpan()


__all__ = ["get_tracer", "otel_span", "plugin_span"]
