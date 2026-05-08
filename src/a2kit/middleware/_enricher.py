"""Error-enricher middleware — wraps the chain so any exception that bubbles
through the inner body is passed to the configured enricher.

The enricher itself may be sync or async; we delegate to `apply_enricher_async`
which handles both shapes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2kit.enrichers import EnricherFn
    from a2kit.middleware._chain import Middleware, ToolContext


def enrich_errors_factory(enricher: EnricherFn) -> Middleware:
    """Return a middleware that funnels exceptions through `enricher`."""

    async def _enrich_mw(
        call_next: Callable[..., Awaitable[Any]],
        ctx: ToolContext,
        /,
        **kwargs: Any,
    ) -> Any:
        try:
            return await call_next(**kwargs)
        except Exception as exc:
            from a2kit.enrichers import apply_enricher_async  # noqa: PLC0415

            raise (await apply_enricher_async(enricher, exc, ctx.tool_name)) from exc

    return _enrich_mw


__all__ = ["enrich_errors_factory"]
