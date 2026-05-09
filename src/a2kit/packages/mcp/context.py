"""Adapter wrapping ``fastmcp.Context`` to fulfill ``a2kit.runtime.ToolContext``.

Wire format: every emission carries ``elapsed_ms`` (int milliseconds since
adapter construction) under ``extra``. Custom channels (event, report) flow
through MCP ``notifications/message`` at ``level="info"`` with a discriminator
``extra.a2kit_kind`` — keeps everything inside the MCP spec while letting
a2kit-aware clients dispatch on the kind. ``ctx.report`` validates payload
type before emit (raises even when reports are disabled).
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import time
from typing import TYPE_CHECKING, Any, cast

from a2kit.exceptions import ReportTypeMismatch, ReportTypeNotDeclared

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

    __slots__ = (
        "_ctx",
        "_events_enabled",
        "_report_type",
        "_reports_enabled",
        "_start_ts",
        "_tool_name",
    )

    def __init__(
        self,
        fastmcp_ctx: Any,
        *,
        report_type: type | None = None,
        tool_name: str | None = None,
        reports_enabled: bool = True,
        events_enabled: bool = True,
    ) -> None:
        self._ctx = fastmcp_ctx
        self._start_ts = time.monotonic()
        self._report_type = report_type
        self._tool_name = tool_name
        self._reports_enabled = reports_enabled
        self._events_enabled = events_enabled

    def _elapsed_ms(self) -> int:
        return round((time.monotonic() - self._start_ts) * 1000)

    def _stamped(self, fields: Mapping[str, Any]) -> dict[str, Any]:
        out = dict(fields)
        out["elapsed_ms"] = self._elapsed_ms()
        return out

    def info(self, msg: str, **fields: Any) -> None:
        _schedule(self._ctx.info(msg, extra=self._stamped(fields)))

    def warning(self, msg: str, **fields: Any) -> None:
        _schedule(self._ctx.warning(msg, extra=self._stamped(fields)))

    def error(self, msg: str, **fields: Any) -> None:
        _schedule(self._ctx.error(msg, extra=self._stamped(fields)))

    def debug(self, msg: str, **fields: Any) -> None:
        _schedule(self._ctx.debug(msg, extra=self._stamped(fields)))

    async def report_progress(
        self,
        current: int | float,
        total: int | float | None = None,
    ) -> None:
        await self._ctx.report_progress(current, total)

    async def event(self, name: str, **payload: Any) -> None:
        if not self._events_enabled:
            return
        await self._ctx.log(
            message=name,
            level="info",
            extra={
                "a2kit_kind": "event",
                "name": name,
                "payload": dict(payload),
                "elapsed_ms": self._elapsed_ms(),
            },
        )

    async def report(self, payload: Any) -> None:
        # why: type-validate even when reports are disabled — keeps tests
        # deterministic regardless of ldd flags.
        if self._report_type is None:
            raise ReportTypeNotDeclared(self._tool_name)
        if not isinstance(payload, self._report_type):
            raise ReportTypeMismatch(self._report_type, type(payload), self._tool_name)
        if not self._reports_enabled:
            return
        body = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        await self._ctx.log(
            message=type(payload).__name__,
            level="info",
            extra={
                "a2kit_kind": "report",
                "type": type(payload).__name__,
                "payload": body,
                "elapsed_ms": self._elapsed_ms(),
            },
        )


def bind_context(
    fn: Callable[..., Any],
    ctx_param_name: str,
    *,
    report_type: type | None = None,
    tool_name: str | None = None,
    reports_enabled: bool = True,
    events_enabled: bool = True,
) -> Callable[..., Any]:
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
                kwargs[ctx_param_name] = FastMCPContextAdapter(
                    raw,
                    report_type=report_type,
                    tool_name=tool_name,
                    reports_enabled=reports_enabled,
                    events_enabled=events_enabled,
                )
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
            kwargs[ctx_param_name] = FastMCPContextAdapter(
                raw,
                report_type=report_type,
                tool_name=tool_name,
                reports_enabled=reports_enabled,
                events_enabled=events_enabled,
            )
        return fn(*args, **kwargs)

    # why: functools.wraps returns _Wrapped which doesn't expose __signature__ in stubs
    cast("Any", sync_wrapper).__signature__ = new_sig
    if "return" in fn.__annotations__:
        sync_wrapper.__annotations__["return"] = fn.__annotations__["return"]
    sync_wrapper.__annotations__[ctx_param_name] = Context
    return sync_wrapper


__all__ = ["FastMCPContextAdapter", "bind_context"]
