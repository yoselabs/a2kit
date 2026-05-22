"""The six transport-neutral dispatch stages.

Each stage is a :class:`~a2kit.packages.dispatch.spec.DispatchStage`: a
``wrap(fn, spec)`` that returns ``fn`` wrapped, or ``fn`` unchanged when
the concern does not apply. None of this module imports ``fastmcp`` —
that is the load-bearing constraint, so the CLI consumer can fold the
same pipeline without paying the cold-start cost.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import TYPE_CHECKING, Any

import anyio

from a2kit.ldd import ldd_state_for_call
from a2kit.packages.context import StderrToolContext
from a2kit.packages.dispatch.spec import (
    SYNTHESIZED_CTX_PARAM_NAME,
    CapturedError,
    has_injectables,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.packages.dispatch.spec import ToolBuildSpec


async def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Invoke ``fn`` and await the result if it is awaitable."""
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


class TimeoutStage:
    """Cancel the tool body after ``meta.extras.timeout_seconds``.

    Innermost stage — the timeout budget covers only the bare body, not
    DI resolution or LDD setup. Self-skips when no timeout is configured.
    """

    name = "timeout"

    def wrap(self, fn: Callable[..., Any], spec: ToolBuildSpec) -> Callable[..., Any]:
        seconds = spec.meta.extras.timeout_seconds if spec.meta is not None else None
        if seconds is None:
            return fn

        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            with anyio.fail_after(seconds):
                return await _call(fn, *args, **kwargs)

        return _wrapped


class EnricherStage:
    """Translate tool-body exceptions through the router's enricher chain.

    Self-skips when there is no router, or the router declares neither
    an ``enrichers`` class tuple nor an ``enrich`` method.
    """

    name = "enricher"

    def wrap(self, fn: Callable[..., Any], spec: ToolBuildSpec) -> Callable[..., Any]:
        router = spec.router
        if router is None:
            return fn
        enrichers = list(getattr(type(router), "enrichers", None) or ())
        enrich_method = getattr(router, "enrich", None)
        if not enrichers and not callable(enrich_method):
            return fn

        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return await _call(fn, *args, **kwargs)
            except Exception as exc:
                if callable(enrich_method):
                    msg = enrich_method(exc)
                    if msg is not None:
                        raise type(exc)(msg) from exc
                for enricher in enrichers:
                    msg = enricher(exc)
                    if msg is not None:
                        raise type(exc)(msg) from exc
                raise

        return _wrapped


class RouterLazyEnterStage:
    """Enter the bound router via ``__aenter__`` before first dispatch.

    Self-skips when there is no router or the router has no
    ``__aenter__``. First-touch coalesces under the App's per-router
    lock (:meth:`a2kit.App._ensure_router_entered`).
    """

    name = "router-lazy-enter"

    def wrap(self, fn: Callable[..., Any], spec: ToolBuildSpec) -> Callable[..., Any]:
        router = spec.router
        if router is None or not hasattr(router, "__aenter__"):
            return fn
        app = spec.app

        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            await app._ensure_router_entered(router)  # noqa: SLF001 -- framework lifecycle seam
            return await _call(fn, *args, **kwargs)

        return _wrapped


class DispatchHookStage:
    """Run the App's dispatch hook + per-call DI scope around the body.

    Routes through ``app._resolver.dispatch(fn, kwargs, pre_hook=hook)``:
    a per-call child container opens, the hook does wire-side conversion
    (e.g. connection-string -> typed config), DI resolves typed kwargs
    (``Lazy[T]`` aware), then per-call cleanups unwind on exit.

    Self-skips when the App carries the default identity hook *and* the
    tool declares no injectables — there would be nothing to resolve, so
    opening a per-call child container would be pure overhead. ``ctx``
    threads through untouched in that case.
    """

    name = "dispatch-hook"

    def wrap(self, fn: Callable[..., Any], spec: ToolBuildSpec) -> Callable[..., Any]:
        app = spec.app
        hook = app.dispatch_hook()
        ctx_param_name = spec.meta.context_param_name if spec.meta is not None else None
        container = app.container()
        is_identity = app.has_default_dispatch_hook()
        if is_identity and not has_injectables(fn, container):
            return fn

        @functools.wraps(fn)
        async def _wrapped(**kwargs: Any) -> Any:
            # ctx is supplied by the transport — keep it out of the wire
            # kwargs the pre_hook + DI see, then merge it back for the body.
            ctx_value = kwargs.pop(ctx_param_name, None) if ctx_param_name else None
            kwargs.pop(SYNTHESIZED_CTX_PARAM_NAME, None)
            async with app._resolver.dispatch(fn, kwargs, pre_hook=hook) as merged:  # noqa: SLF001 -- framework resolver seam
                if ctx_param_name is not None and ctx_value is not None:
                    merged[ctx_param_name] = ctx_value
                return await _call(fn, **merged)

        return _wrapped


class LddStateStage:
    """Bind the per-call LDD ambient (including ``ctx``) around the body.

    Reads ``ctx`` from kwargs by the tool's declared param name, or pops
    the synthesized name when the body did not declare ctx. Falls back to
    a fresh ``StderrToolContext`` so the ambient ``ctx`` is never None
    inside a dispatch. Never self-skips — every dispatched tool runs
    inside an LDD ambient.
    """

    name = "ldd-state"

    def wrap(self, fn: Callable[..., Any], spec: ToolBuildSpec) -> Callable[..., Any]:
        meta = spec.meta
        ctx_param_name = meta.context_param_name if meta is not None else None
        report_type = meta.extras.report_type if meta is not None else None
        tool_name = meta.tool_name if meta is not None else None

        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            if ctx_param_name:
                ctx_obj = kwargs.get(ctx_param_name)
            else:
                # Body did not declare ctx; the transport may have
                # synthesized one. Pop it so the body never sees it.
                ctx_obj = kwargs.pop(SYNTHESIZED_CTX_PARAM_NAME, None)
            if ctx_obj is None:
                ctx_obj = StderrToolContext()
            with ldd_state_for_call(
                ctx=ctx_obj,
                events_enabled=spec.events_enabled,
                reports_enabled=spec.reports_enabled,
                report_type=report_type,
                tool_name=tool_name,
                sinks=spec.sinks,
            ):
                return await _call(fn, *args, **kwargs)

        return _wrapped


class ErrorCaptureStage:
    """Capture a tool-body exception into a neutral :class:`CapturedError`.

    Outermost neutral stage — it sees every other stage's exceptions.
    Capturing the exception (class, message, traceback) is
    transport-neutral; rendering it to a wire shape is the per-transport
    render stage's job. A ``BaseExceptionGroup`` of pure
    ``CancelledError`` (anyio task-group cancellation) is re-raised
    unchanged. ``BaseException`` siblings (``KeyboardInterrupt``,
    ``SystemExit``, bare ``CancelledError``) fall outside ``except
    Exception`` and propagate untouched.
    """

    name = "error-capture"

    def wrap(self, fn: Callable[..., Any], spec: ToolBuildSpec) -> Callable[..., Any]:  # noqa: ARG002
        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return await _call(fn, *args, **kwargs)
            except BaseExceptionGroup as eg:
                if all(isinstance(e, asyncio.CancelledError) for e in eg.exceptions):
                    raise
                non_cancel = [e for e in eg.exceptions if not isinstance(e, asyncio.CancelledError)]
                raise CapturedError(non_cancel[0]) from non_cancel[0]
            except Exception as exc:
                raise CapturedError(exc) from exc

        return _wrapped


__all__ = [
    "DispatchHookStage",
    "EnricherStage",
    "ErrorCaptureStage",
    "LddStateStage",
    "RouterLazyEnterStage",
    "TimeoutStage",
]
