"""OTel span middleware — opens a span around the inner call.

Reads `ctx.state["connection_key"]` if a connection-aware upstream middleware
set it; otherwise records `tool.connection` as absent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opentelemetry import trace as _trace

from a2kit._otel import otel_span as _otel_span
from a2kit.formatter import Page as _Page
from a2kit.middleware._chain import STATE_CONNECTION_KEY

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2kit.middleware._chain import Middleware, ToolContext

_NOOP_TRACER = _trace.NoOpTracer()


def _stamp_result_count(span_wrapper: Any, result: Any) -> None:
    """Stamp `tool.result.count` on the active span when `result` is list-shaped.

    Cardinality only — PII-safe. Covers `list`, `tuple`, and `Page[T]`.
    No-op when the span has no `set_attribute` (defensive against null adapters).
    """
    if isinstance(result, _Page):
        count = len(result.items)
    elif isinstance(result, (list, tuple)):
        count = len(result)
    else:
        return
    span = getattr(span_wrapper, "_span", None)
    if span is not None and hasattr(span, "set_attribute"):
        span.set_attribute("tool.result.count", count)


def otel_span_factory() -> Middleware:
    """Return an OTel-span middleware bound to the kit's tracer.

    Factory shape (rather than a bare function) keeps parity with the other
    parametric middleware (enricher, listview).

    v0.17: stamps ``tool.result.count`` on the span when the inner call
    returns a ``list`` / ``tuple`` / ``Page[T]``. Cardinality only —
    PII-safe and stamped after success (meaningless on error). Exception
    recording + ERROR status are handled by OTel's
    ``start_as_current_span`` defaults.
    """

    async def _otel_mw(
        call_next: Callable[..., Awaitable[Any]],
        ctx: ToolContext,
        /,
        **kwargs: Any,
    ) -> Any:
        conn_key = ctx.state.get(STATE_CONNECTION_KEY)
        span_cm = _otel_span(ctx.tool_name, conn_key, ctx.write)
        with span_cm as span_wrapper:
            result = await call_next(**kwargs)
            _stamp_result_count(span_wrapper, result)
            return result

    return _otel_mw


def otel_noop_span_factory() -> Middleware:
    """Return a no-op span middleware — used when `otel=False`.

    Kept for symmetry / future uses; the implicit chain simply omits the OTel
    middleware when opted out.
    """

    async def _noop_mw(
        call_next: Callable[..., Awaitable[Any]],
        ctx: ToolContext,
        /,
        **kwargs: Any,
    ) -> Any:
        with _NOOP_TRACER.start_as_current_span(f"a2kit.tool.{ctx.tool_name}"):
            return await call_next(**kwargs)

    return _noop_mw


__all__ = ["otel_noop_span_factory", "otel_span_factory"]
