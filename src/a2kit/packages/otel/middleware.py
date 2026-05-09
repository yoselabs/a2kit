"""FastMCP middleware that wraps tool calls in OTel spans + counters.

Span attributes are pulled from ``A2KitMeta`` round-tripped through the
FastMCP tool's ``meta["a2kit"]`` payload (same source the listview
middleware reads). The FastMCP-side request id is read from
``MiddlewareContext.fastmcp_context.request_id`` when available.

a2kit core does not depend on OpenTelemetry. This module lazy-imports
``opentelemetry-api`` inside :func:`install` / on first call, raising a
friendly :class:`ImportError` if the optional extras are missing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from a2kit.packages.otel.tracer import get_meter, get_tracer

if TYPE_CHECKING:
    from fastmcp import FastMCP


async def _meta_a2kit(fastmcp_ctx: Any, tool_name: str | None) -> dict[str, Any]:
    """Best-effort lookup of the tool's ``meta["a2kit"]`` blob via ``server.get_tool``."""
    if not tool_name or fastmcp_ctx is None:
        return {}
    server = getattr(fastmcp_ctx, "fastmcp", None)
    if server is None:
        return {}
    try:
        tool = await server.get_tool(tool_name)
    except Exception:  # noqa: BLE001
        return {}
    meta_full = getattr(tool, "meta", None) or {}
    if not isinstance(meta_full, dict):
        return {}
    meta_a2kit = meta_full.get("a2kit")
    return meta_a2kit if isinstance(meta_a2kit, dict) else {}


class OTelMiddleware(Middleware):
    """Wraps each FastMCP tool call in an OTel span + counter increments.

    Span name: ``mcp.tool.{tool_name}``. Attributes:

    - ``a2kit.tool_name``
    - ``a2kit.verb``
    - ``a2kit.router``
    - ``a2kit.tags`` (comma-joined sorted string)
    - ``mcp.request_id`` when FastMCP exposes one

    Counter ``a2kit.tool.calls`` is incremented per call with attributes
    ``tool``, ``verb``, ``status`` (``ok`` or ``error``).
    """

    def __init__(self, *, tracer_name: str = "a2kit", meter_name: str = "a2kit") -> None:
        self._tracer = get_tracer(tracer_name)
        self._meter = get_meter(meter_name)
        self._counter = self._meter.create_counter(
            "a2kit.tool.calls",
            description="Count of FastMCP tool calls observed by a2kit OTel middleware.",
        )

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: Any,
    ) -> Any:
        from opentelemetry import trace

        params = context.message
        tool_name = getattr(params, "name", None) or "<unknown>"
        fastmcp_ctx = getattr(context, "fastmcp_context", None)
        meta_a2kit = await _meta_a2kit(fastmcp_ctx, tool_name)

        attrs: dict[str, Any] = {"a2kit.tool_name": tool_name}
        verb = meta_a2kit.get("verb")
        if isinstance(verb, str):
            attrs["a2kit.verb"] = verb
        extra = meta_a2kit.get("extra") if isinstance(meta_a2kit, dict) else None
        router = extra.get("a2kit.router_slug") if isinstance(extra, dict) else None
        if isinstance(router, str):
            attrs["a2kit.router"] = router
        tags = meta_a2kit.get("tags")
        if isinstance(tags, (list, tuple)):
            attrs["a2kit.tags"] = ",".join(sorted(str(t) for t in tags))

        request_id = getattr(fastmcp_ctx, "request_id", None)
        if request_id is not None:
            attrs["mcp.request_id"] = str(request_id)

        span_name = f"mcp.tool.{tool_name}"
        with self._tracer.start_as_current_span(span_name, attributes=attrs) as span:
            try:
                result = await call_next(context)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(trace.StatusCode.ERROR, str(exc))
                self._counter.add(
                    1,
                    {
                        "tool": tool_name,
                        "verb": str(verb) if verb else "",
                        "status": "error",
                    },
                )
                raise
            span.set_status(trace.StatusCode.OK)
            self._counter.add(
                1,
                {
                    "tool": tool_name,
                    "verb": str(verb) if verb else "",
                    "status": "ok",
                },
            )
            return result


def install(
    server: FastMCP,
    *,
    tracer_name: str = "a2kit",
    meter_name: str = "a2kit",
) -> OTelMiddleware:
    """Add an :class:`OTelMiddleware` to ``server``. Returns the middleware.

    Lazy-imports OTel; raises :class:`ImportError` with an install hint if
    the optional ``otel`` extras are not present.
    """
    middleware = OTelMiddleware(tracer_name=tracer_name, meter_name=meter_name)
    server.add_middleware(middleware)
    return middleware


__all__ = ["OTelMiddleware", "install"]
