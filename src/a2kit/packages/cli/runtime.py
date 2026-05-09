"""In-process tool invocation — protocol-neutral runtime for the CLI adapter."""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, cast

from a2kit.packages.cli.context import StderrToolContext
from a2kit.packages.formatter import FormatHint, format_response
from a2kit.tool import identity_dispatch_hook

if TYPE_CHECKING:
    from collections.abc import Callable


async def _invoke_tool_in_process(
    fn: Callable[..., Any],
    kwargs: dict[str, Any],
    *,
    fmt: str = "auto",
    ctx_param_name: str | None = None,
    report_type: type | None = None,
    tool_name: str | None = None,
    reports_enabled: bool = True,
    events_enabled: bool = True,
    dispatch_hook: Callable[..., Any] | None = None,
) -> str:
    """Invoke ``fn`` with ``kwargs``, format the result, return formatter ``data``.

    ``fn`` is expected to come from ``app.tools()`` (already enricher-wrapped
    by the CLI builder). The ``dispatch_hook`` resolves request-scoped DI
    kwargs (e.g., ``store: TrackerStore``) before the tool runs.
    """
    hook = dispatch_hook or identity_dispatch_hook
    resolved_any: Any = hook(fn, kwargs)
    if inspect.isawaitable(resolved_any):
        resolved_any = await resolved_any
    call_kwargs: dict[str, Any] = dict(resolved_any)

    if ctx_param_name and ctx_param_name not in call_kwargs:
        call_kwargs[ctx_param_name] = StderrToolContext(
            report_type=report_type,
            tool_name=tool_name,
            reports_enabled=reports_enabled,
            events_enabled=events_enabled,
        )

    if inspect.iscoroutinefunction(fn):
        raw = await fn(**call_kwargs)
    else:
        raw = fn(**call_kwargs)
        if inspect.isawaitable(raw):
            raw = await raw

    response = format_response(raw, format_hint=cast("FormatHint", fmt))
    return response.data


def invoke_tool_sync(
    fn: Callable[..., Any],
    kwargs: dict[str, Any],
    *,
    fmt: str = "auto",
    ctx_param_name: str | None = None,
    report_type: type | None = None,
    tool_name: str | None = None,
    reports_enabled: bool = True,
    events_enabled: bool = True,
    dispatch_hook: Callable[..., Any] | None = None,
) -> str:
    """Synchronous adapter — run :func:`_invoke_tool_in_process` to completion."""
    return asyncio.run(
        _invoke_tool_in_process(
            fn,
            kwargs,
            fmt=fmt,
            ctx_param_name=ctx_param_name,
            report_type=report_type,
            tool_name=tool_name,
            reports_enabled=reports_enabled,
            events_enabled=events_enabled,
            dispatch_hook=dispatch_hook,
        )
    )


__all__ = ["_invoke_tool_in_process", "invoke_tool_sync"]
