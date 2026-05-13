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
    sinks: tuple[Any, ...] = (),
) -> str:
    """Invoke ``fn`` with ``kwargs``, format the result, return formatter ``data``.

    ``fn`` is expected to come from ``app.tools()`` (already enricher-wrapped
    by the CLI builder). The ``dispatch_hook`` resolves request-scoped DI
    kwargs (e.g., ``store: TrackerStore``) before the tool runs.

    LDD state (events/reports kill-switches, report type, tool name) is set
    via :func:`a2kit.ldd.ldd_state_for_call` for the duration of ``fn`` so
    free functions ``a2kit.ldd.event`` / ``a2kit.ldd.report`` honor flags.
    """
    from a2kit.ldd import ldd_state_for_call

    hook = dispatch_hook or identity_dispatch_hook
    resolved_any: Any = hook(fn, kwargs)
    if inspect.isawaitable(resolved_any):
        resolved_any = await resolved_any
    call_kwargs: dict[str, Any] = dict(resolved_any)

    if ctx_param_name and ctx_param_name not in call_kwargs:
        call_kwargs[ctx_param_name] = StderrToolContext()
    ctx_for_ldd: Any = call_kwargs.get(ctx_param_name) if ctx_param_name else None

    # Per-tool timeout (per ``dispatcher-timeout-decorator``):
    # read ``meta.extras.timeout_seconds`` and wrap the fn call in
    # ``anyio.fail_after`` for cross-transport parity with the MCP
    # path's ``_wrap_with_timeout``.
    from a2kit.metadata import get_meta

    _meta = get_meta(fn)
    _timeout_s: float | None = _meta.extras.timeout_seconds if _meta is not None else None

    async def _call_fn() -> Any:
        if inspect.iscoroutinefunction(fn):
            return await fn(**call_kwargs)
        out = fn(**call_kwargs)
        if inspect.isawaitable(out):
            return await out
        return out

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
                raw = await _call_fn()
        else:
            raw = await _call_fn()

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

    When ``app`` is provided and has a registered lifespan, the lifespan
    is entered before the tool body and exited after — both inside the
    same :func:`asyncio.run` loop so any state opened in startup
    (e.g. async sqlite connections) is bound to the loop the tool body
    uses. Lifecycle dispatches once per process; subsequent
    ``invoke_tool_sync`` calls within the same process skip the
    lifespan entirely — in practice the CLI dispatches one tool per
    process so this is rarely exercised.
    """

    sinks: tuple[Any, ...] = ()
    if app is not None and hasattr(app, "ldd"):
        sinks = app.ldd.sinks

    async def _runner() -> str:
        run_lifecycle = app is not None and getattr(app, "has_lifespan", lambda: False)()
        if run_lifecycle and not app._lifecycle_started:  # noqa: SLF001 -- intentional, lifecycle state is App-scoped
            app._lifecycle_started = True  # noqa: SLF001
            async with app.lifespan_cm():
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
