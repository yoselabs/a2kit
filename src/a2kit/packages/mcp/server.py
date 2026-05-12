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
import logging
from dataclasses import asdict
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool

from a2kit.metadata import A2KitMeta, get_meta
from a2kit.packages.mcp.guards import GuardsMiddleware
from a2kit.packages.mcp.listview import ListViewMiddleware

_log = logging.getLogger(__name__)
_WARN_ONCE: set[str] = set()


def _meta_to_dict(meta: A2KitMeta) -> dict[str, Any]:
    """JSON-serializable projection of ``A2KitMeta`` for ``tool.meta`` wire output.

    ``meta.extras`` is dumped via pydantic's ``model_dump(mode="json")``;
    ``report_type`` (a ``type`` object, not JSON-safe) is excluded by name.
    The typed model is never mutated by this projection — wire serialization
    is the wire layer's job.
    """
    d = asdict(meta)
    d["tags"] = sorted(meta.tags)
    # Skip the internal annotation-storage fields; project the wire shape via
    # ``annotations_as_dict`` which avoids the ``mcp.types`` lazy import when
    # the consumer didn't pass an explicit ``ToolAnnotations`` instance.
    d.pop("_annotations_kwargs", None)
    d.pop("_annotations_explicit", None)
    d["annotations"] = meta.annotations_as_dict()
    # ``asdict`` on a frozen dataclass walks fields but does not descend into
    # pydantic models — d["extras"] is the BaseModel instance itself. Replace
    # it with a JSON-safe dump, excluding ``report_type`` (a ``type`` object).
    d["extras"] = meta.extras.model_dump(mode="json", exclude={"report_type"})
    return d


def _wrap_with_ldd_state(
    fn: Any,
    *,
    ctx_param_name: str,
    report_type: type | None,
    tool_name: str | None,
    reports_enabled: bool,
    events_enabled: bool,
    sinks: tuple[Any, ...] = (),
) -> Any:
    """Set the per-call LDD contextvar (including the ambient ``ctx``)
    before invoking ``fn``.

    The tool's signature is preserved unchanged; ``ctx: a2kit.ToolContext``
    (= ``fastmcp.Context``) is injected directly by FastMCP. The free
    functions ``a2kit.ldd.event``/``report``/``log`` (and shorthands)
    read the ambient ``_LDD_STATE`` set here — tool authors and helper
    functions never pass ``ctx`` explicitly.
    """
    from a2kit.ldd import ldd_state_for_call

    @functools.wraps(fn)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        ctx_obj = kwargs.get(ctx_param_name)
        with ldd_state_for_call(
            ctx=ctx_obj,
            events_enabled=events_enabled,
            reports_enabled=reports_enabled,
            report_type=report_type,
            tool_name=tool_name,
            sinks=sinks,
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

    wire_params, wire_scopes_needed = wire_input_params(fn, container)
    needs_conn = "connection" in wire_scopes_needed

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
    # ``__signature__`` is an established convention for callable objects
    # (PEP 362) but isn't part of the static function-attribute set, so we
    # set it via ``setattr`` to keep the type checker happy without a
    # suppression marker.
    setattr(_wrapped, "__signature__", inspect.Signature(parameters=new_params))  # noqa: B010
    # Preserve return annotation for output-schema gen.
    try:
        from typing import get_type_hints

        ret = get_type_hints(fn).get("return")
        if ret is not None:
            ann = dict(getattr(_wrapped, "__annotations__", {}))
            ann["return"] = ret
            _wrapped.__annotations__ = ann
    except Exception as exc:  # noqa: BLE001 -- decoration must not raise; degrade observably
        name = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
        if name not in _WARN_ONCE:
            _WARN_ONCE.add(name)
            _log.warning("_wrap_with_dispatch_hook: failed to copy return annotation for %s: %s", name, exc)
    return _wrapped


def _has_injectables(fn: Any, container: Any) -> bool:
    if container is None:
        return False
    from a2kit.signature import wire_input_params

    base, _ = wire_input_params(fn, container=None)
    wire, wire_scopes = wire_input_params(fn, container=container)
    return len(wire) < len(base) or bool(wire_scopes)


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


def build_mcp_server(app: Any, **fastmcp_kwargs: Any) -> FastMCP:  # noqa: C901 -- Surface filter adds one branch; extracting per-tool body would reduce clarity
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
    app_sinks: tuple[Any, ...] = app.ldd.sinks if hasattr(app, "ldd") else ()

    container = app.container() if hasattr(app, "container") else None
    dispatch_hook = app.dispatch_hook() if hasattr(app, "dispatch_hook") else None

    from a2kit.surface import Surface
    from a2kit.tool import _BUILTIN_RESERVED_TOOL_NAMES, _RESERVED_TOOL_NAME_PREFIX

    for fn in app.tools():
        meta = get_meta(fn)
        if meta is None:
            continue

        tool_surfaces = meta.extras.surfaces or Surface.ALL
        if Surface.MCP not in tool_surfaces:
            continue

        router = _router_for_tool(app, fn)
        wrapped = _wrap_with_router_enrichers(fn, router)
        if container is not None and dispatch_hook is not None:
            wrapped = _wrap_with_dispatch_hook(wrapped, dispatch_hook, container)
        if meta.context_param_name:
            wrapped = _wrap_with_ldd_state(
                wrapped,
                ctx_param_name=meta.context_param_name,
                report_type=meta.extras.report_type,
                tool_name=meta.tool_name,
                reports_enabled=reports_enabled,
                events_enabled=events_enabled,
                sinks=app_sinks,
            )
        if app_debug:
            wrapped = _wrap_with_debug_traceback(wrapped)

        # `_meta.*` tools are protocol-meta (e.g. `_meta.health`) — tagged so
        # the post-loop `server.disable(tags={"_meta"})` filter excludes them
        # from default `list_tools` while keeping them callable by name.
        is_meta = meta.tool_name.startswith(_RESERVED_TOOL_NAME_PREFIX)
        if is_meta and meta.tool_name not in _BUILTIN_RESERVED_TOOL_NAMES:
            msg = (
                f"tool {meta.tool_name!r} uses reserved namespace "
                f"{_RESERVED_TOOL_NAME_PREFIX!r}; this prefix is reserved for "
                "built-in protocol-meta tools (e.g. `_meta.health`). See "
                "OPERATIONAL_CONTRACTS.md → 'The _meta.* tool namespace'."
            )
            raise ValueError(msg)
        tool_tags = {*meta.tags, "_meta"} if is_meta else set(meta.tags)
        tool = FunctionTool.from_function(
            wrapped,
            name=meta.tool_name,
            tags=tool_tags,
            annotations=meta.annotations,
            meta={"a2kit": _meta_to_dict(meta)},
        )
        server.add_tool(tool)

    # Hide `_meta.*` tools from default `list_tools` output via FastMCP 3's
    # visibility-transform API. Selector is the `"_meta"` tag stamped above,
    # so future `_meta.*` additions inherit the rule.
    server.disable(tags={"_meta"})

    # Built-in middleware first; user-attached middlewares (via add_mcp_middleware) after.
    server.add_middleware(ListViewMiddleware())
    server.add_middleware(GuardsMiddleware())
    for mw in app.mcp_middlewares():
        server.add_middleware(mw)
    return server


__all__ = ["build_mcp_server"]
