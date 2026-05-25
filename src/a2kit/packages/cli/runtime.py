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


#: Default CLI exit code map from AppError base_kind (sysexits.h).
#: Per-class `cli_exit_code` ClassVar overrides this. From
#: `error-envelope-rendering` / `cli-response-encoding`.
_KIND_CLI_EXIT: dict[str, int] = {
    "input": 2,
    "auth": 77,
    "policy": 77,
    "infra": 75,
    "bug": 70,
}


def _cli_exit_for(exc: Any) -> int:
    override = type(exc).cli_exit_code
    if override is not None:
        return override
    return _KIND_CLI_EXIT.get(exc.base_kind, 70)


class CliErrorRenderStage:
    """Render a captured tool-body error for the CLI transport.

    The transport-neutral ``ErrorCaptureStage`` wraps every tool-body
    exception in :class:`~a2kit.packages.dispatch.CapturedError`; the
    enricher chain upstream guarantees ``ce.original`` is an
    ``AppError`` (non-AppError raises become ``UnexpectedDefect`` via
    quarantine).

    Renders ``rendered_prose`` (set by ``ErrorEnvelopeStage``) to stderr
    and raises ``typer.Exit(code)`` with the kind-mapped exit code
    (per-class ``cli_exit_code`` ClassVar wins; otherwise the
    base-kind default per sysexits.h).
    """

    name = "cli-error-render"

    def wrap(self, fn: Callable[..., Any], spec: ToolBuildSpec) -> Callable[..., Any]:
        from a2effect import AppError

        debug = bool(getattr(spec.app, "debug", False))

        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except CapturedError as ce:
                orig = ce.original
                if isinstance(orig, AppError):
                    prose = getattr(orig, "rendered_prose", None) or str(orig)
                    typer.echo(prose, err=True)
                    if debug:
                        typer.echo(ce.traceback_str, err=True)
                    raise typer.Exit(_cli_exit_for(orig)) from orig
                # Defensive: should be unreachable since the enricher chain
                # quarantines non-AppError into UnexpectedDefect. Kept so a
                # broken dispatch chain still produces a non-zero exit.
                typer.echo(f"error: {ce.message}", err=True)
                if debug:
                    typer.echo(ce.traceback_str, err=True)
                raise typer.Exit(70) from ce.original

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
