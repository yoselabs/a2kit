"""OTel span helpers — for the @tool wrapper and for plugin authors.

Public surface:

- `otel_span(tool_name, connection_key, write)` — context manager used by
  the @tool decorator. Wraps a real tracer (or OTel's `NoOpTracer` when no
  provider is configured) and stamps `tool.*` attributes.
- `get_tracer()` — cached, returns the a2kit tracer (real or NoOp).
- `plugin_span(name, **attrs)` — context manager that opens
  `a2kit.plugin.{name}` as a child of the current span; stamps caller attrs.

`opentelemetry-api` is a core a2kit dep (v0.13+). When no real provider is
configured we use `trace.NoOpTracer()` directly — no bespoke null classes.
"""

from __future__ import annotations

from typing import Any

from opentelemetry import trace


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
        # pragma below: NoOp span has set_attribute; real spans always do too
        if self._span is not None and hasattr(self._span, "set_attribute"):  # pragma: no branch
            self._span.set_attribute("tool.name", self._tool_name)
            self._span.set_attribute("tool.write", self._write)
            if self._connection_key is not None:
                self._span.set_attribute("tool.connection", "-".join(self._connection_key))
        return self

    def __exit__(self, *exc: object) -> None:
        self._cm.__exit__(*exc)


def _resolve_tracer() -> Any:
    """Return the active a2kit tracer; OTel `NoOpTracer` if no real provider."""
    provider = trace.get_tracer_provider()
    if provider.__class__.__name__ in {"ProxyTracerProvider", "NoOpTracerProvider"}:
        return trace.NoOpTracer()
    return trace.get_tracer("a2kit")  # pragma: no cover — exercised under real OTel instrumentation in production


def otel_span(tool_name: str, connection_key: tuple[str, ...] | None, write: bool) -> Any:
    """Return an OTel span CM wrapping `a2kit.tool.<tool_name>`.

    Falls back to OTel's `NoOpTracer` when no real provider is configured —
    the wrapper still works (its `set_attribute` calls become no-ops on the
    NoOp span), so the @tool decorator runs the same code path either way.
    """
    tracer = _resolve_tracer()
    span_cm = tracer.start_as_current_span(f"a2kit.tool.{tool_name}")
    return _OTelWrapper(span_cm, tool_name, connection_key, write)


_TRACER_CACHE: dict[str, Any] = {}


def get_tracer() -> Any:
    """Return the a2kit OTel tracer (real or NoOp). Cached after first call.

    Plugins use this to open child spans without importing `opentelemetry`
    themselves. Always safe to call.
    """
    if "tracer" in _TRACER_CACHE:
        return _TRACER_CACHE["tracer"]
    tracer = _resolve_tracer()
    _TRACER_CACHE["tracer"] = tracer
    return tracer


def plugin_span(name: str, **attrs: Any) -> Any:
    """Open `a2kit.plugin.{name}` as a child of the current span.

    Sets `a2kit.plugin.name = {name}` plus any caller-supplied attrs.
    Falls back to OTel's NoOpTracer when no real provider is configured —
    plugin authors can sprinkle `with plugin_span("connections.load", key=key):`
    without conditional checks.
    """
    tracer = _resolve_tracer()
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
        # pragma below: NoOp span has set_attribute
        if self._span is not None and hasattr(self._span, "set_attribute"):  # pragma: no branch
            self._span.set_attribute("a2kit.plugin.name", self._name)
            for key, value in self._attrs.items():
                self._span.set_attribute(key, value)
        return self

    def __exit__(self, *exc: object) -> None:
        self._cm.__exit__(*exc)


__all__ = ["get_tracer", "otel_span", "plugin_span"]
