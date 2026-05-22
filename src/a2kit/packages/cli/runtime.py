"""In-process CLI tool invocation — folds the shared dispatch pipeline."""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any, cast

import typer

from a2kit.packages.context import StderrToolContext
from a2kit.packages.dispatch import CapturedError, ToolBuildSpec, fold_pipeline
from a2kit.packages.formatter import FormatHint, format_response

if TYPE_CHECKING:
    from collections.abc import Callable


class CliErrorRenderStage:
    """Render a captured tool-body error for the CLI transport.

    The transport-neutral ``ErrorCaptureStage`` turns the exception into
    a :class:`~a2kit.packages.dispatch.CapturedError`; this stage renders
    it — an ``error: <message>`` line to stderr, the full traceback when
    the App is in debug mode — then raises ``typer.Exit(1)`` so the
    process exits non-zero. The MCP transport's render stage produces a
    ``ToolError`` envelope from the same neutral capture instead.
    """

    name = "cli-error-render"

    def wrap(self, fn: Callable[..., Any], spec: ToolBuildSpec) -> Callable[..., Any]:
        debug = bool(getattr(spec.app, "debug", False))

        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except CapturedError as ce:
                typer.echo(f"error: {ce.message}", err=True)
                if debug:
                    typer.echo(ce.traceback_str, err=True)
                raise typer.Exit(1) from ce.original

        return _wrapped


async def _invoke_tool_in_process(
    fn: Callable[..., Any],
    kwargs: dict[str, Any],
    *,
    fmt: str = "auto",
    spec: ToolBuildSpec,
) -> str:
    """Fold the dispatch pipeline onto ``fn``, invoke it, format the result.

    Folds the transport-neutral ``DISPATCH_PIPELINE`` (timeout, enrichers,
    router-lazy-enter, dispatch-hook + DI, LDD ambient, error-capture) and
    appends the CLI error-render stage. ``ctx`` is synthesized into the
    declared ctx kwarg the same way FastMCP injects it on the MCP side, so
    the shared stages handle ctx identically on both transports.
    """
    ctx_param_name = spec.meta.context_param_name if spec.meta is not None else None
    call_kwargs = dict(kwargs)
    if ctx_param_name and ctx_param_name not in call_kwargs:
        call_kwargs[ctx_param_name] = StderrToolContext()

    wrapped = fold_pipeline(fn, spec)
    wrapped = CliErrorRenderStage().wrap(wrapped, spec)
    raw = await wrapped(**call_kwargs)

    response = format_response(raw, format_hint=cast("FormatHint", fmt))
    return response.data


def invoke_tool_sync(
    fn: Callable[..., Any],
    kwargs: dict[str, Any],
    *,
    fmt: str = "auto",
    spec: ToolBuildSpec,
) -> str:
    """Synchronous CLI tool invocation — run :func:`_invoke_tool_in_process`.

    The App's lifecycle (``async with app:``) wraps the tool body so
    singletons enter eagerly and routers enter lazily on first dispatch,
    all inside the same :func:`asyncio.run` loop.
    """

    async def _runner() -> str:
        async with spec.app:
            return await _invoke_tool_in_process(fn, kwargs, fmt=fmt, spec=spec)

    return asyncio.run(_runner())


__all__ = ["CliErrorRenderStage", "_invoke_tool_in_process", "invoke_tool_sync"]
