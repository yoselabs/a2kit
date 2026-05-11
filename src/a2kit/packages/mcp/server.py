"""``build_mcp_server(app, **fastmcp_kwargs) -> FastMCP``.

Forwards ``**fastmcp_kwargs`` to ``FastMCP.__init__`` so users can plug in
auth providers, lifespans, transforms, etc., without a2kit owning an
abstraction. Walks ``app.tools()`` and registers each as a ``FunctionTool``;
``A2KitMeta`` round-trips into ``tool.meta["a2kit"]`` for middleware to read.

Request-scoped DI: when ``app`` has registered providers (via
``app.provide(T, factory)``), the dispatch hook resolves typed kwargs
(``store: TrackerStore`` etc.) before the tool body runs.
"""

from __future__ import annotations

import functools
import inspect
from dataclasses import asdict
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool

from a2kit.metadata import A2KitMeta, get_meta
from a2kit.packages.mcp.guards import GuardsMiddleware
from a2kit.packages.mcp.listview import ListViewMiddleware

_EXTRA_DROP_FROM_WIRE = ("a2kit.report_type",)


def _meta_to_dict(meta: A2KitMeta) -> dict[str, Any]:
    """JSON-serializable projection of ``A2KitMeta`` for ``tool.meta`` wire output."""
    d = asdict(meta)
    d["tags"] = sorted(meta.tags)
    annotations = d.get("annotations")
    if annotations is not None and hasattr(meta.annotations, "model_dump"):
        d["annotations"] = meta.annotations.model_dump(exclude_none=True)
    extra = dict(d.get("extra") or {})
    for key in _EXTRA_DROP_FROM_WIRE:
        extra.pop(key, None)
    list_view = extra.get("a2kit.list_view")
    if list_view is not None and hasattr(list_view, "__dataclass_fields__"):
        extra["a2kit.list_view"] = asdict(list_view)
    d["extra"] = extra
    return d


def _wrap_with_ldd_state(
    fn: Any,
    *,
    report_type: type | None,
    tool_name: str | None,
    reports_enabled: bool,
    events_enabled: bool,
) -> Any:
    """Set the per-call LDD contextvar before invoking ``fn``.

    Replaces the old ``bind_context`` adapter wrapping. The tool's signature is
    preserved unchanged; ``ctx: a2kit.ToolContext`` (= ``fastmcp.Context``) is
    injected directly by FastMCP. Free functions ``a2kit.ldd.event`` and
    ``a2kit.ldd.report`` read the contextvar to honor enable flags and report
    type without needing to wrap the Context object.
    """
    from a2kit.ldd import ldd_state_for_call

    @functools.wraps(fn)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        with ldd_state_for_call(
            events_enabled=events_enabled,
            reports_enabled=reports_enabled,
            report_type=report_type,
            tool_name=tool_name,
        ):
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result

    return _wrapped


def _wrap_with_router_enrichers(fn: Any, router: Any | None) -> Any:
    if router is None:
        return fn
    enrichers = list(getattr(type(router), "enrichers", None) or ())
    enrich_method = getattr(router, "enrich", None)
    if not enrichers and not callable(enrich_method):
        return fn

    @functools.wraps(fn)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result
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


def _wrap_with_debug_traceback(fn: Any) -> Any:
    """Augment exceptions with a full traceback in their message.

    Used when ``App(debug=True)`` — FastMCP unmasked-error path emits
    ``f"Error calling tool {name!r}: {e}"`` on the wire, so embedding the
    traceback in ``str(e)`` carries diagnostic detail through to the client.
    ``asyncio.CancelledError`` is re-raised unchanged so cancellation isn't
    wrapped (see OPERATIONAL_CONTRACTS.md Q1).
    """
    import asyncio
    import functools
    import traceback

    @functools.wraps(fn)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            tb = traceback.format_exc()
            augmented = type(exc)(f"{exc}\n\nTraceback:\n{tb}")
            raise augmented from exc

    return _wrapped


def _wrap_with_dispatch_hook(fn: Any, hook: Any, container: Any) -> Any:
    """Apply the App's dispatch hook to resolve injectable kwargs before fn.

    The wrapper's ``__signature__`` is rewritten to expose only wire kwargs
    (plus ``connection: str`` when the chain reaches it) so fastmcp's
    schema gen sees the agent-facing surface, not the injectables.
    """
    from a2kit.signature import wire_input_params

    wire_params, needs_conn = wire_input_params(fn, container)

    if not _has_injectables(fn, container):
        return fn  # no rewrite needed

    @functools.wraps(fn)
    async def _wrapped(**kwargs: Any) -> Any:
        resolved = hook(fn, kwargs)
        if inspect.isawaitable(resolved):
            resolved = await resolved
        result = fn(**resolved)
        if inspect.isawaitable(result):
            result = await result
        return result

    # Build a signature that only mentions wire params (+ connection if needed).
    new_params: list[inspect.Parameter] = []
    for name, p in wire_params.items():
        new_params.append(
            inspect.Parameter(
                name=name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=p.default if p.default is not inspect.Parameter.empty else inspect.Parameter.empty,
                annotation=p.annotation,
            )
        )
    if needs_conn and "connection" not in wire_params:
        new_params.append(
            inspect.Parameter(
                name="connection",
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=str,
            )
        )
    _wrapped.__signature__ = inspect.Signature(parameters=new_params)  # ty: ignore[unresolved-attribute]
    # Preserve return annotation for output-schema gen.
    import contextlib

    with contextlib.suppress(Exception):
        from typing import get_type_hints

        ret = get_type_hints(fn).get("return")
        if ret is not None:
            ann = dict(getattr(_wrapped, "__annotations__", {}))
            ann["return"] = ret
            _wrapped.__annotations__ = ann
    return _wrapped


def _has_injectables(fn: Any, container: Any) -> bool:
    if container is None:
        return False
    from a2kit.signature import wire_input_params

    base, needs_conn = wire_input_params(fn, container=None)
    wire, _ = wire_input_params(fn, container=container)
    return len(wire) < len(base) or needs_conn


def _router_for_tool(app: Any, fn: Any) -> Any | None:
    for r in app.routers():
        for tool_fn in r.tools():
            if tool_fn is fn or getattr(tool_fn, "__func__", None) is getattr(fn, "__func__", None):
                return r
    return None


def _merge_lifespan(app: Any, user_lifespan: Any | None) -> Any:
    """Build an async context manager that runs a2kit lifecycle around ``user_lifespan``.

    Order: dispatch_startup(app) → user_lifespan(server).__aenter__ → yield →
    user_lifespan(server).__aexit__ → dispatch_shutdown(app). If ``user_lifespan``
    is None, only the a2kit handlers run.
    """
    from contextlib import asynccontextmanager

    from a2kit.app import dispatch_shutdown, dispatch_startup

    @asynccontextmanager
    async def _lifespan(server: Any) -> Any:
        await dispatch_startup(app)
        try:
            if user_lifespan is None:
                yield None
            else:
                async with user_lifespan(server) as user_state:
                    yield user_state
        finally:
            await dispatch_shutdown(app)

    return _lifespan


def build_mcp_server(app: Any, **fastmcp_kwargs: Any) -> FastMCP:
    """Build a FastMCP server from an ``a2kit.App``.

    All ``fastmcp_kwargs`` flow straight to ``FastMCP.__init__`` — auth,
    providers, transforms, lifespan, tasks, sampling_handler, etc. a2kit owns
    no auth abstraction; FastMCP plugins work directly.

    When ``app`` has registered ``on_startup`` / ``on_shutdown`` handlers, this
    function derives a ``lifespan`` async context manager and merges it with
    any user-supplied ``lifespan=`` kwarg. Order: a2kit-startup → user-lifespan
    enter → user body → user-lifespan exit → a2kit-shutdown.
    """
    if hasattr(app, "has_lifecycle_handlers") and app.has_lifecycle_handlers():
        fastmcp_kwargs["lifespan"] = _merge_lifespan(app, fastmcp_kwargs.get("lifespan"))
    # `App(debug=True)` unmasks error details so the tool's exception message
    # reaches the wire. Tool wrappers further down append the traceback to
    # `str(exc)` when debug is on (see `_wrap_with_debug_traceback`).
    app_debug = bool(getattr(app, "debug", False))
    if "mask_error_details" not in fastmcp_kwargs:
        fastmcp_kwargs["mask_error_details"] = not app_debug
    server = FastMCP(name=app.name, **fastmcp_kwargs)

    reports_enabled = getattr(app, "ldd_reports", True)
    events_enabled = getattr(app, "ldd_events", True)

    container = app.container() if hasattr(app, "container") else None
    dispatch_hook = app.dispatch_hook() if hasattr(app, "dispatch_hook") else None

    for fn in app.tools():
        meta = get_meta(fn)
        if meta is None:
            continue

        router = _router_for_tool(app, fn)
        wrapped = _wrap_with_router_enrichers(fn, router)
        if container is not None and dispatch_hook is not None:
            wrapped = _wrap_with_dispatch_hook(wrapped, dispatch_hook, container)
        if meta.context_param_name:
            wrapped = _wrap_with_ldd_state(
                wrapped,
                report_type=meta.extra.get("a2kit.report_type"),
                tool_name=meta.tool_name,
                reports_enabled=reports_enabled,
                events_enabled=events_enabled,
            )
        if app_debug:
            wrapped = _wrap_with_debug_traceback(wrapped)

        # `_meta.*` tools are protocol-meta (e.g. `_meta.health`) — keep them
        # out of agent-facing `list_tools` by tagging with `_meta` and disabling
        # them at registration; clients can still invoke them by name.
        from a2kit.tool import _RESERVED_TOOL_NAME_PREFIX

        is_meta = meta.tool_name.startswith(_RESERVED_TOOL_NAME_PREFIX)
        tool_tags = {*meta.tags, "_meta"} if is_meta else set(meta.tags)
        tool = FunctionTool.from_function(
            wrapped,
            name=meta.tool_name,
            tags=tool_tags,
            annotations=meta.annotations,
            meta={"a2kit": _meta_to_dict(meta)},
        )
        if is_meta:
            tool.disable()
        server.add_tool(tool)

    # Built-in middleware first; user-attached middlewares (via add_mcp_middleware) after.
    server.add_middleware(ListViewMiddleware())
    server.add_middleware(GuardsMiddleware())
    for mw in app.mcp_middlewares():
        server.add_middleware(mw)
    return server


__all__ = ["build_mcp_server"]
