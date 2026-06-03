"""In-process CLI tool invocation — folds the shared dispatch pipeline."""

from __future__ import annotations

import asyncio
import functools
import json as _json
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

import typer

from a2kit.packages.context import StderrToolContext
from a2kit.packages.dispatch import (
    CapturedError,
    ToolBuildSpec,
    close_render_state,
    fold_pipeline,
    get_rendered_error,
    open_render_state,
)
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


#: Per-invocation flag for end-to-end JSON mode (`--json` flag). When True,
#: the success path emits raw `model_dump()` JSON to stdout and the error
#: path emits the typed envelope JSON to stdout (stderr stays silent). Set
#: by the per-tool CLI callback under a try/finally; never leaks across
#: invocations.
_cli_json_mode: ContextVar[bool] = ContextVar("a2kit_cli_json_mode", default=False)


class CliErrorRenderStage:
    """Render a captured tool-body error for the CLI transport.

    The transport-neutral ``ErrorCaptureStage`` wraps every tool-body
    exception in :class:`~a2kit.packages.dispatch.CapturedError`; the
    enricher chain upstream guarantees ``ce.original`` is an
    ``AppError`` (non-AppError raises become ``UnexpectedDefect`` via
    quarantine).

    Renders the prose written by ``ErrorEnvelopeStage`` (carried via
    the render-state side channel) to stderr and raises
    ``typer.Exit(code)`` with the kind-mapped exit code (per-class
    ``cli_exit_code`` ClassVar wins; otherwise the base-kind default
    per sysexits.h).
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
                json_mode = _cli_json_mode.get()
                if isinstance(orig, AppError):
                    if json_mode:
                        # `--json` end-to-end mode: envelope JSON to stdout,
                        # stderr silent. Exit code unchanged from prose mode.
                        envelope = orig.to_envelope_dict()
                        typer.echo(_json.dumps({"error": envelope}, separators=(",", ":"), default=str))
                        raise typer.Exit(_cli_exit_for(orig)) from orig
                    # The render-state side channel (opened by the CLI
                    # entry point) carries the prose written by
                    # ErrorEnvelopeStage. The ``else`` branch is a
                    # defensive fallback for the rare case where the
                    # entry point did not open the slot (e.g. a stage
                    # exercised in isolation by a unit test).
                    rendered = get_rendered_error(orig)
                    prose = rendered.prose if rendered is not None else str(orig)
                    typer.echo(prose, err=True)
                    if debug:
                        typer.echo(ce.traceback_str, err=True)
                    raise typer.Exit(_cli_exit_for(orig)) from orig
                # Defensive: should be unreachable since the enricher chain
                # quarantines non-AppError into UnexpectedDefect. Kept so a
                # broken dispatch chain still produces a non-zero exit.
                if json_mode:
                    defect = {"type": type(orig).__name__, "message": ce.message}
                    typer.echo(_json.dumps({"error": defect}, separators=(",", ":"), default=str))
                else:
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
    router-lazy-enter, dispatch-hook + DI, call scope, error-capture) and
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
    token = open_render_state()
    try:
        raw = await wrapped(**call_kwargs)
    finally:
        close_render_state(token)

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


async def _invoke_tool_in_process_raw(
    fn: Callable[..., Any],
    kwargs: dict[str, Any],
    *,
    spec: ToolBuildSpec,
) -> Any:
    """Raw-passthrough sibling of `_invoke_tool_in_process` for `--json` mode.

    Returns the dispatch pipeline's raw output (BaseModel / list / dict /
    primitive) instead of running it through `format_response`. The caller
    is responsible for JSON serialization. The error path is unchanged —
    `CliErrorRenderStage` still emits the envelope on `--json` via the
    `_cli_json_mode` ContextVar.
    """
    ctx_param_name = spec.meta.context_param_name if spec.meta is not None else None
    call_kwargs = dict(kwargs)
    if ctx_param_name and ctx_param_name not in call_kwargs:
        call_kwargs[ctx_param_name] = StderrToolContext()

    wrapped = fold_pipeline(fn, spec)
    wrapped = CliErrorRenderStage().wrap(wrapped, spec)
    token = open_render_state()
    try:
        return await wrapped(**call_kwargs)
    finally:
        close_render_state(token)


def invoke_tool_sync_raw(
    fn: Callable[..., Any],
    kwargs: dict[str, Any],
    *,
    spec: ToolBuildSpec,
) -> Any:
    """Synchronous raw-passthrough invocation — for `--json` mode."""

    async def _runner() -> Any:
        async with spec.app:
            return await _invoke_tool_in_process_raw(fn, kwargs, spec=spec)

    return asyncio.run(_runner())


def invoke_tool_sync_json(fn: Callable[..., Any], kwargs: dict[str, Any], *, spec: ToolBuildSpec) -> str:
    """`--json` mode runner: set the mode var, raw-invoke, serialize. One-shot."""
    token = _cli_json_mode.set(True)
    try:
        raw = invoke_tool_sync_raw(fn, kwargs, spec=spec)
    finally:
        _cli_json_mode.reset(token)
    return serialize_for_json_mode(raw)


def serialize_for_json_mode(raw: Any) -> str:
    """Serialize a tool's raw return for `--json` mode (compact, one-line).

    BaseModel → `model_dump()`; list of BaseModels → list of dumps;
    primitive/dict/None pass through. Uses `default=str` as a permissive
    fallback for non-JSON-native values.
    """
    from pydantic import BaseModel

    if isinstance(raw, BaseModel):
        return _json.dumps(raw.model_dump(mode="json"), separators=(",", ":"), default=str)
    if isinstance(raw, list):
        out = [item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in raw]
        return _json.dumps(out, separators=(",", ":"), default=str)
    return _json.dumps(raw, separators=(",", ":"), default=str)


__all__ = [
    "CliErrorRenderStage",
    "_cli_json_mode",
    "_invoke_tool_in_process",
    "invoke_tool_sync",
    "invoke_tool_sync_json",
    "invoke_tool_sync_raw",
    "serialize_for_json_mode",
]
