"""Adapter wrapping ``fastmcp.Context`` to fulfill ``a2kit.runtime.ToolContext``.

The ToolContext Protocol declares ``info``/``warning``/``error``/``debug`` as
sync methods, but ``fastmcp.Context``'s equivalents are coroutines. The
adapter schedules them as fire-and-forget tasks on the running event loop —
the loop always exists at tool-call time inside FastMCP. ``report_progress``
stays async, matching the Protocol.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


def _format_extra(fields: Mapping[str, Any]) -> dict[str, Any] | None:
    if not fields:
        return None
    return dict(fields)


def _schedule(coro: Any) -> None:
    """Fire-and-forget a coroutine on the running loop.

    FastMCP tool calls always execute inside an event loop, so ``get_running_loop``
    succeeds in the normal path. Outside a loop (defensive fallback — direct
    unit-test calls), close the coroutine cleanly to avoid `RuntimeWarning`.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        coro.close()
        return
    loop.create_task(coro)


class FastMCPContextAdapter:
    """Wraps ``fastmcp.Context`` to fulfill ``a2kit.runtime.ToolContext``."""

    __slots__ = ("_ctx",)

    def __init__(self, fastmcp_ctx: Any) -> None:
        self._ctx = fastmcp_ctx

    def info(self, msg: str, **fields: Any) -> None:
        _schedule(self._ctx.info(msg, extra=_format_extra(fields)))

    def warning(self, msg: str, **fields: Any) -> None:
        _schedule(self._ctx.warning(msg, extra=_format_extra(fields)))

    def error(self, msg: str, **fields: Any) -> None:
        _schedule(self._ctx.error(msg, extra=_format_extra(fields)))

    def debug(self, msg: str, **fields: Any) -> None:
        _schedule(self._ctx.debug(msg, extra=_format_extra(fields)))

    async def report_progress(
        self,
        current: int | float,
        total: int | float | None = None,
    ) -> None:
        await self._ctx.report_progress(current, total)


def bind_context(fn: Callable[..., Any], ctx_param_name: str) -> Callable[..., Any]:
    """Rewrite ``fn`` so its ``ctx_param_name`` parameter is typed as
    ``fastmcp.Context`` (so FastMCP injects it), and at call time the injected
    Context is wrapped with :class:`FastMCPContextAdapter` before delegating.

    Sync and async tool functions both supported.
    """
    from fastmcp import Context

    sig = inspect.signature(fn)
    params = []
    for name, p in sig.parameters.items():
        if name == ctx_param_name:
            params.append(p.replace(annotation=Context))
        else:
            params.append(p)
    new_sig = sig.replace(parameters=params)

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            raw = kwargs.get(ctx_param_name)
            if raw is not None and not isinstance(raw, FastMCPContextAdapter):
                kwargs[ctx_param_name] = FastMCPContextAdapter(raw)
            return await fn(*args, **kwargs)

        # why: functools.wraps returns _Wrapped which doesn't expose __signature__ in stubs
        cast("Any", async_wrapper).__signature__ = new_sig
        if "return" in fn.__annotations__:
            async_wrapper.__annotations__["return"] = fn.__annotations__["return"]
        async_wrapper.__annotations__[ctx_param_name] = Context
        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        raw = kwargs.get(ctx_param_name)
        if raw is not None and not isinstance(raw, FastMCPContextAdapter):
            kwargs[ctx_param_name] = FastMCPContextAdapter(raw)
        return fn(*args, **kwargs)

    # why: functools.wraps returns _Wrapped which doesn't expose __signature__ in stubs
    cast("Any", sync_wrapper).__signature__ = new_sig
    if "return" in fn.__annotations__:
        sync_wrapper.__annotations__["return"] = fn.__annotations__["return"]
    sync_wrapper.__annotations__[ctx_param_name] = Context
    return sync_wrapper


__all__ = ["FastMCPContextAdapter", "bind_context"]
