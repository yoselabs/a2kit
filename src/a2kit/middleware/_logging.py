"""structlog contextvar-binding middleware.

Binds ``tool.name`` and (when present) ``tool.connection`` into
``structlog.contextvars`` for the duration of the inner call. The bindings
are scoped via ``structlog.contextvars.bound_contextvars`` so concurrent
tool invocations stay isolated (each task sees only its own context).

`get_tool_logger` (in ``a2kit.logging``) reads these bindings at emit time
— authors don't need to thread them through.

Lazy import: ``structlog`` only loads when the middleware actually runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2kit.middleware._chain import Middleware, ToolContext


def structlog_context_factory() -> Middleware:
    """Return a middleware that binds ``tool.*`` keys into structlog contextvars.

    Outer middleware (placed alongside the OTel span) so logs emitted from
    *any* inner middleware or the tool body inherit the bindings. Uses
    ``bound_contextvars`` so the bindings unwind cleanly even on exceptions
    and never leak across concurrent calls.
    """
    import structlog  # noqa: PLC0415 — lazy import keeps cold-start cheap.

    bound_contextvars = structlog.contextvars.bound_contextvars

    async def _logging_mw(
        call_next: Callable[..., Awaitable[Any]],
        ctx: ToolContext,
        /,
        **kwargs: Any,
    ) -> Any:
        conn_key = ctx.state.get("connection_key")
        bindings: dict[str, Any] = {"tool.name": ctx.tool_name}
        if conn_key is not None:
            bindings["tool.connection"] = "-".join(conn_key)
        with bound_contextvars(**bindings):
            return await call_next(**kwargs)

    return _logging_mw


__all__ = ["structlog_context_factory"]
