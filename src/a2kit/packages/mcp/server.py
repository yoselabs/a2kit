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
from a2kit.packages.mcp.context import bind_context
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


def build_mcp_server(app: Any, **fastmcp_kwargs: Any) -> FastMCP:
    """Build a FastMCP server from an ``a2kit.App``.

    All ``fastmcp_kwargs`` flow straight to ``FastMCP.__init__`` — auth,
    providers, transforms, lifespan, tasks, sampling_handler, etc. a2kit owns
    no auth abstraction; FastMCP plugins work directly.
    """
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
            wrapped = bind_context(
                wrapped,
                meta.context_param_name,
                report_type=meta.extra.get("a2kit.report_type"),
                tool_name=meta.tool_name,
                reports_enabled=reports_enabled,
                events_enabled=events_enabled,
            )

        tool = FunctionTool.from_function(
            wrapped,
            name=meta.tool_name,
            tags=set(meta.tags),
            annotations=meta.annotations,
            meta={"a2kit": _meta_to_dict(meta)},
        )
        server.add_tool(tool)

    # Built-in middleware first; user-attached middlewares (via add_mcp_middleware) after.
    server.add_middleware(ListViewMiddleware())
    server.add_middleware(GuardsMiddleware())
    for mw in app.mcp_middlewares():
        server.add_middleware(mw)
    return server


__all__ = ["build_mcp_server"]
