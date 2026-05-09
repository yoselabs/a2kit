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
) -> str:
    """Invoke ``fn`` with ``kwargs``, format the result, return formatter ``data``.

    - DI parameters are stripped via :func:`a2kit.signature.strip_dependencies`.
    - The :class:`a2kit.runtime.ToolContext` parameter (if any) is supplied as
      a :class:`StderrToolContext`.
    - The function's enricher (if any, from :class:`A2KitMeta`) is applied
      before invocation.
    - The return value is fed to :func:`a2kit.packages.formatter.format_response`.
    """
    meta = get_meta(fn)
    enricher_fn = meta.enricher if meta is not None else None
    inner = strip_dependencies(fn)
    wrapped = wrap(inner, enricher_fn)

    if ctx_param_name:
        kwargs[ctx_param_name] = StderrToolContext()

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
) -> str:
    """Synchronous adapter — run :func:`_invoke_tool_in_process` to completion."""
    return asyncio.run(_invoke_tool_in_process(fn, kwargs, fmt=fmt, ctx_param_name=ctx_param_name))


__all__ = ["_invoke_tool_in_process", "invoke_tool_sync"]
