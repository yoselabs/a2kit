"""In-process tool invocation — protocol-neutral runtime for the CLI adapter."""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, cast

from a2kit.metadata import get_meta
from a2kit.packages.cli.context import StderrToolContext
from a2kit.packages.enrichers import wrap
from a2kit.packages.formatter import FormatHint, format_response
from a2kit.signature import strip_dependencies

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
) -> str:
    """Invoke ``fn`` with ``kwargs``, format the result, return formatter ``data``."""
    meta = get_meta(fn)
    enricher_fn = meta.enricher if meta is not None else None
    inner = strip_dependencies(fn)
    wrapped = wrap(inner, enricher_fn)

    if ctx_param_name:
        kwargs[ctx_param_name] = StderrToolContext(
            report_type=report_type,
            tool_name=tool_name,
            reports_enabled=reports_enabled,
            events_enabled=events_enabled,
        )

    if inspect.iscoroutinefunction(wrapped) or inspect.iscoroutinefunction(fn):
        raw = await wrapped(**kwargs)
    else:
        raw = wrapped(**kwargs)
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
        )
    )


__all__ = ["_invoke_tool_in_process", "invoke_tool_sync"]
