"""Tool-call-contamination guard + capability guard middleware.

`tool_call_guard` — checks kwargs for accidental tool-call shapes (a model
trying to invoke another tool by passing its name as a string arg).

`capability_guard` — placeholder. v0.13: capability filtering happens at
select-expression evaluation (lint-time + serve-time), not per-call. The
middleware exists so the chain has a slot for future per-call enforcement
(e.g. dynamic scope changes) without restructuring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.tools._runtime import _check_tool_call_contamination

if TYPE_CHECKING:
    import inspect
    from collections.abc import Awaitable, Callable

    from a2kit.middleware._chain import ToolContext


async def tool_call_guard(
    call_next: Callable[..., Awaitable[Any]],
    ctx: ToolContext,
    /,
    **kwargs: Any,
) -> Any:
    """Detect tool-call contamination in kwargs before the inner body runs.

    The guard reads the inner-fn signature out of `ctx.state["sig"]` (set by
    the decorator at build time) so it can `bind_partial` the kwargs.
    """
    sig: inspect.Signature | None = ctx.state.get("sig")
    if sig is not None:
        bound = sig.bind_partial(**kwargs)
        bound.apply_defaults()
        _check_tool_call_contamination(bound, ctx.tool_name)
    return await call_next(**kwargs)


async def capability_guard(
    call_next: Callable[..., Awaitable[Any]],
    ctx: ToolContext,  # placeholder slot
    /,
    **kwargs: Any,
) -> Any:
    """Placeholder capability gate.

    v0.13 keeps capability enforcement at select time (lint + scope filter at
    serve build). This middleware simply forwards; later versions may layer
    per-call dynamic checks (e.g. runtime scope downgrade) here.
    """
    return await call_next(**kwargs)


__all__ = ["capability_guard", "tool_call_guard"]
