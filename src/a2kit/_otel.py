"""OTel span helper for the fat `@a2kit.tool` decorator.

Lazy-imported so consumers without the `[otel]` extra don't pay the import.
Detects a real (non-default) tracer provider; if none, returns a no-op span.

Public surface:

- `otel_span(tool_name, connection_key, write)` — returns a context manager.
  Always safe to call; falls back to `_NullSpan` when OTel is unavailable.
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


__all__ = ["otel_span"]
