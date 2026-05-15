"""In-process tool invocation — protocol-neutral runtime for the CLI adapter."""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, cast

from a2kit.packages.cli.context import StderrToolContext
from a2kit.packages.formatter import FormatHint, format_response

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
    sinks: tuple[Any, ...] = (),
    app: Any | None = None,
) -> str:
    """Invoke ``fn`` with ``kwargs``, format the result, return formatter ``data``.

    ``fn`` is expected to come from ``app.tools()`` (already enricher-wrapped
    by the CLI builder). When ``app`` is provided, routes through
    ``app._resolver.dispatch(fn, kwargs, pre_hook=dispatch_hook)`` so
    per-call scope, ``Lazy[T]``, and provider chain resolution all flow
    through the v0.36 lifecycle path. Per-call cleanups unwind on exit
    with exception preservation.

    ``dispatch_hook`` is wire-side conversion only (e.g. connection-string
    → typed config); DI is the framework's job, run after the hook.

    LDD state (events/reports kill-switches, report type, tool name) is
    set via :func:`a2kit.ldd.ldd_state_for_call` for the duration of
    ``fn`` so free functions ``a2kit.ldd.event`` / ``a2kit.ldd.report``
    honor flags.
    """
    from a2kit.ldd import ldd_state_for_call
    from a2kit.metadata import get_meta

    _meta = get_meta(fn)
    _timeout_s: float | None = _meta.extras.timeout_seconds if _meta is not None else None

    async def _call_fn(call_kwargs: dict[str, Any]) -> Any:
        if inspect.iscoroutinefunction(fn):
            return await fn(**call_kwargs)
        out = fn(**call_kwargs)
        if inspect.isawaitable(out):
            return await out
        return out

    async def _run_inside_call(call_kwargs: dict[str, Any]) -> Any:
        # ctx + LDD scope + optional timeout wrap the fn body — all run
        # INSIDE the dispatch async-with so per-call cleanups see the
        # propagating exception (if any).
        #
        # Post relax-ldd-ambient-requirement: ambient ctx is always
        # non-None inside a framework dispatch. When the tool declared
        # ctx, inject the synthesized StderrToolContext into call_kwargs
        # so the body receives it. When the tool did NOT declare ctx,
        # still synthesize a StderrToolContext for ambient binding but
        # do NOT inject into call_kwargs (the body has no such param).
        if ctx_param_name and ctx_param_name not in call_kwargs:
            call_kwargs[ctx_param_name] = StderrToolContext()
        if ctx_param_name:
            ctx_for_ldd: Any = call_kwargs.get(ctx_param_name)
        else:
            ctx_for_ldd = StderrToolContext()
        # why: post relax-ldd-ambient-requirement, CLI always synthesizes a
        # StderrToolContext for ambient binding; ctx_for_ldd is never None.

        with ldd_state_for_call(
            ctx=ctx_for_ldd,
            events_enabled=events_enabled,
            reports_enabled=reports_enabled,
            report_type=report_type,
            tool_name=tool_name,
            sinks=sinks,
        ):
            if _timeout_s is not None:
                import anyio

                with anyio.fail_after(_timeout_s):
                    return await _call_fn(call_kwargs)
            return await _call_fn(call_kwargs)

    if app is not None:
        async with app._resolver.dispatch(fn, kwargs, pre_hook=dispatch_hook) as merged:
            raw = await _run_inside_call(dict(merged))
    else:
        # Standalone invocation (no App) — no DI, no lifecycle. Used by
        # tests / direct CLI calls of fn that have no injectables.
        call_kwargs = dict(kwargs)
        raw = await _run_inside_call(call_kwargs)

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
    app: Any | None = None,
) -> str:
    """Synchronous adapter — run :func:`_invoke_tool_in_process` to completion.

    When ``app`` is provided, the App's lifecycle (``async with app:``)
    wraps the tool body so singletons enter eagerly and routers enter
    lazily on dispatch — both inside the same :func:`asyncio.run` loop
    so any state opened in startup is bound to the loop the tool body
    uses.
    """

    sinks: tuple[Any, ...] = ()
    if app is not None:
        sinks = app.ldd.sinks

    async def _runner() -> str:
        if app is not None:
            async with app:
                return await _invoke_tool_in_process(
                    fn,
                    kwargs,
                    fmt=fmt,
                    ctx_param_name=ctx_param_name,
                    report_type=report_type,
                    tool_name=tool_name,
                    reports_enabled=reports_enabled,
                    events_enabled=events_enabled,
                    dispatch_hook=dispatch_hook,
                    sinks=sinks,
                    app=app,
                )
        return await _invoke_tool_in_process(
            fn,
            kwargs,
            fmt=fmt,
            ctx_param_name=ctx_param_name,
            report_type=report_type,
            tool_name=tool_name,
            reports_enabled=reports_enabled,
            events_enabled=events_enabled,
            dispatch_hook=dispatch_hook,
            sinks=sinks,
        )

    return asyncio.run(_runner())


__all__ = ["_invoke_tool_in_process", "invoke_tool_sync"]
