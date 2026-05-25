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
    """Translate tool-body exceptions through the router + app enricher chains.

    Chain order: router enrichers (registration order), then app enrichers
    (registration order), then defect quarantine. Each enricher is either
    wide (first-param annotation is BaseException / Exception, called for
    every exception) or narrow (specific type, called only on isinstance
    match). The first enricher returning a non-None AppError wins; later
    layers are not tried. Any exception escaping all enrichers is wrapped
    in a2effect.UnexpectedDefect via quarantine().

    Self-skips when neither the router nor the app has any enrichers AND
    the body never raises a non-AppError. Always wraps when any enricher
    is registered, since quarantine must run on uncaught raises.
    """

    name = "enricher"

    def wrap(self, fn: Callable[..., Any], spec: ToolBuildSpec) -> Callable[..., Any]:
        from a2effect import AppError
        from a2effect.defect import quarantine

        router = spec.router
        app = spec.app
        router_enrichers = list(getattr(router, "_enrichers", ()) or ())
        app_enrichers = list(getattr(app, "_enrichers", ()) or ())
        chain = router_enrichers + app_enrichers

        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return await _call(fn, *args, **kwargs)
            except AppError:
                # Authors who raise AppError directly bypass the enricher
                # chain — the typed envelope is already in hand.
                raise
            except BaseException as exc:
                for filter_type, enricher in chain:
                    if not isinstance(exc, filter_type):
                        continue
                    result = enricher(exc)
                    if result is None:
                        continue
                    if not isinstance(result, AppError):
                        raise TypeError(f"enricher {enricher!r} returned {type(result).__name__}, expected AppError | None") from exc
                    if result.__cause__ is None:
                        result.__cause__ = exc
                    raise result from exc
                raise quarantine(exc) from exc

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

    Routes through ``app._resolver.call_scope(fn, kwargs, pre_hook=hook)``:
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
            from a2kit.packages.context import _a2kit_request_principal

            # ctx is supplied by the transport — keep it out of the wire
            # kwargs the pre_hook + DI see, then merge it back for the body.
            ctx_value = kwargs.pop(ctx_param_name, None) if ctx_param_name else None
            kwargs.pop(SYNTHESIZED_CTX_PARAM_NAME, None)
            principal = _a2kit_request_principal.get()
            if principal is not None:
                kwargs.setdefault("_a2kit_principal", principal)
            async with app._resolver.call_scope(fn, kwargs, pre_hook=hook) as merged:  # noqa: SLF001 -- framework resolver seam
                if ctx_param_name is not None and ctx_value is not None:
                    merged[ctx_param_name] = ctx_value
                return await _call(fn, **merged)

        return _wrapped


async def _run_authorize_gate(authorize: Callable[..., Any], container: Any) -> None:
    """Resolve and invoke an `authorize=` callable; raise on falsy return.

    Opens a fresh `call_scope` to resolve the callable's DI params (Principal
    seeded via `_a2kit_request_principal` contextvar), invokes it, raises
    `AuthorizationDenied` on falsy return. Shared by `AuthorizeGateStage`
    (CLI / MCP via DISPATCH_PIPELINE) and the HTTP substrate path.
    """
    from a2kit.exceptions import AuthorizationDenied
    from a2kit.packages.context import _a2kit_request_principal

    callable_name = getattr(authorize, "__qualname__", getattr(authorize, "__name__", "<authorize>"))
    principal = _a2kit_request_principal.get()
    seed: dict[str, Any] = {}
    if principal is not None:
        seed["_a2kit_principal"] = principal
    async with container.call_scope(authorize, seed) as merged:
        fn_param_names = {p.name for p in inspect.signature(authorize).parameters.values()}
        call_kwargs = {k: v for k, v in merged.items() if k in fn_param_names}
        if principal is not None and "principal" in fn_param_names and "principal" not in call_kwargs:
            call_kwargs["principal"] = principal
        decision = await _call(authorize, **call_kwargs)
    if not decision:
        raise AuthorizationDenied(
            reason=str(decision) if decision is not None else "authorize callable returned falsy",
            callable_name=callable_name,
        )


class AuthorizeGateStage:
    """Gate a tool body on its declared `authorize=` callable.

    Self-skips when `spec.meta.extras.authorize` is None. Otherwise runs
    `_run_authorize_gate`. The tool body is not invoked on denial.
    """

    name = "authorize-gate"

    def wrap(self, fn: Callable[..., Any], spec: ToolBuildSpec) -> Callable[..., Any]:
        authorize = spec.meta.extras.authorize if spec.meta is not None else None
        if authorize is None:
            return fn
        app = spec.app

        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            await _run_authorize_gate(authorize, app._resolver)  # noqa: SLF001 -- framework resolver seam
            return await _call(fn, *args, **kwargs)

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
            # Read the LDD level threshold off App config per-call; mutating
            # `app.config.ldd.level` between calls is observed on the next
            # dispatch. Sentinel 0 if the App somehow lacks a config — keeps
            # tests that build half-stubs from breaking.
            from a2kit.packages.ldd import LDD_LEVEL_RANK

            cfg = getattr(spec.app, "config", None)
            level: Any = getattr(getattr(cfg, "ldd", None), "level", None) if cfg is not None else None
            threshold: int = LDD_LEVEL_RANK.get(level, 0)
            with ldd_state_for_call(
                ctx=ctx_obj,
                events_enabled=spec.events_enabled,
                reports_enabled=spec.reports_enabled,
                report_type=report_type,
                tool_name=tool_name,
                sinks=spec.sinks,
                level_threshold=threshold,
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
    "AuthorizeGateStage",
    "DispatchHookStage",
    "EnricherStage",
    "ErrorCaptureStage",
    "LddStateStage",
    "RouterLazyEnterStage",
    "TimeoutStage",
    "_run_authorize_gate",
]
