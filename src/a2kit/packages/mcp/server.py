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
    ctx_param_name: str | None,
    report_type: type | None,
    tool_name: str | None,
    reports_enabled: bool,
    events_enabled: bool,
    sinks: tuple[Any, ...] = (),
) -> Any:
    """Set the per-call LDD contextvar (including the ambient ``ctx``)
    before invoking ``fn``.

    Post relax-ldd-ambient-requirement: ambient ``ctx`` is always
    non-None inside a framework dispatch. When the tool declared
    ``ctx``, the dispatcher reads it from kwargs by the declared name.
    When the tool did NOT declare ctx, the rewritten wrapper signature
    carries a synthesized ``_a2kit_ctx`` parameter
    (see :data:`SYNTHESIZED_CTX_PARAM_NAME`); FastMCP injects ctx by
    type, and the wrapper extracts via that synthesized name. In
    either case, the wrapper pops the synthesized name from kwargs
    before invoking ``fn`` so the tool body never sees a kwarg it
    didn't declare.

    The free functions ``a2kit.ldd.event``/``report``/``log`` (and
    shorthands) read the ambient ``_LDD_STATE`` set here — tool
    authors and helper functions never pass ``ctx`` explicitly.
    """
    from a2kit.ldd import ldd_state_for_call

    @functools.wraps(fn)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        if ctx_param_name:
            ctx_obj = kwargs.get(ctx_param_name)
        else:
            # Tool body did not declare ctx; the rewritten signature
            # carries the synthesized name so FastMCP injected ctx.
            # Pop so the body never sees the framework-internal kwarg.
            ctx_obj = kwargs.pop(SYNTHESIZED_CTX_PARAM_NAME, None)
        # why: under FastMCP dispatch the rewritten signature always has a
        # ctx param so FastMCP injects a live Context. Direct-call test
        # paths (e.g. ``bt.fn()`` bypassing FastMCP) hit None — fall back
        # to a StderrToolContext so ambient binding is still non-None and
        # LDD primitives don't trip Mode B unrelated to the actual issue.
        if ctx_obj is None:
            from a2kit.packages.cli.context import StderrToolContext

            ctx_obj = StderrToolContext()
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


def _wrap_with_router_lazy_enter(fn: Any, app: Any, router: Any | None) -> Any:
    """Ensure the bound router has entered via ``__aenter__`` before dispatch.

    No-op when the router has no ``__aenter__`` method (most routers).
    First-touch coalesces under a per-router lock owned by the App
    (see :meth:`a2kit.App._ensure_router_entered`).
    """
    if router is None or not hasattr(router, "__aenter__"):
        return fn

    @functools.wraps(fn)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        await app._ensure_router_entered(router)
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


def _wrap_with_timeout(fn: Any, *, seconds: float) -> Any:
    """Wrap ``fn`` in ``anyio.fail_after(seconds)`` per
    ``dispatcher-timeout-decorator`` D-WRAPPER.

    Installed as the innermost wrapper (closest to ``fn``). On
    timeout, raises Python's built-in ``TimeoutError`` which the
    outermost error-envelope wrapper serializes into the standard
    structured payload.
    """
    import functools

    import anyio

    @functools.wraps(fn)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        with anyio.fail_after(seconds):
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result

    return _wrapped


def _wrap_with_error_envelope(fn: Any, *, debug: bool) -> Any:
    """a2kit-owned wire-error envelope — independent of FastMCP semantics.

    Catches every uncaught ``Exception`` from the wrapper chain and
    re-raises ``ToolError(json.dumps({"class", "message", [traceback]}))``.
    FastMCP's tool-dispatch path re-raises ``FastMCPError`` subclasses
    (including ``ToolError``) **unchanged** before any masking — so the
    JSON payload reaches the wire verbatim as ``content[0].text`` with
    ``isError: true``, regardless of ``mask_error_details``.

    Exclusions:

    - ``FastMCPError`` (incl. author-raised ``ToolError``) — passes
      through unwrapped so author-shaped messages reach the wire
      on FastMCP's own path. Double-wrapping their message would
      corrupt it.
    - ``asyncio.CancelledError``, ``KeyboardInterrupt``, ``SystemExit``
      — ``BaseException`` siblings, naturally outside ``except Exception``.
    - ``BaseExceptionGroup`` containing only ``CancelledError``s —
      anyio task-group cancellation per Q1.

    Replaces the legacy ``_wrap_with_debug_traceback`` (which embedded
    the traceback in ``str(exc)`` as a workaround for the same problem).
    """
    import asyncio
    import functools
    import json
    import traceback

    from fastmcp.exceptions import FastMCPError, ToolError

    def _payload(exc: BaseException) -> dict[str, Any]:
        out: dict[str, Any] = {
            "class": type(exc).__name__,
            "message": str(exc),
        }
        if debug:
            out["traceback"] = traceback.format_exc()
        return out

    @functools.wraps(fn)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except FastMCPError:
            raise
        except BaseExceptionGroup as eg:
            if all(isinstance(e, asyncio.CancelledError) for e in eg.exceptions):
                raise
            non_cancel = [e for e in eg.exceptions if not isinstance(e, asyncio.CancelledError)]
            first = non_cancel[0]
            raise ToolError(json.dumps(_payload(first))) from first
        except Exception as exc:
            raise ToolError(json.dumps(_payload(exc))) from exc

    return _wrapped


def _ctx_annotation_passthrough(fn: Any, ctx_param_name: str) -> Any:
    """Wrap ``fn`` rewriting the ctx param annotation to ``fastmcp.Context``.

    Used when no DI is needed but the tool's ctx annotation is the a2kit
    Protocol; pydantic cannot schema-generate Protocols, so we swap to the
    concrete fastmcp class for FastMCP's introspection while preserving
    call semantics.
    """
    import fastmcp as _fastmcp

    orig_sig = inspect.signature(fn)
    passthrough_params: list[inspect.Parameter] = []
    for name, p in orig_sig.parameters.items():
        if name == ctx_param_name:
            passthrough_params.append(p.replace(annotation=_fastmcp.Context))
        else:
            passthrough_params.append(p)

    @functools.wraps(fn)
    async def _passthrough(*args: Any, **kwargs: Any) -> Any:
        result = fn(*args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result

    _install_rewritten_signature(fn, _passthrough, passthrough_params)
    return _passthrough


def _wrap_with_dispatch_hook(
    fn: Any,
    hook: Any,
    app: Any,
    *,
    ctx_param_name: str | None = None,
) -> Any:
    """Apply the App's dispatch hook + per-call lifecycle scope before fn.

    Routes every dispatch through ``app._resolver.dispatch(fn, kwargs,
    pre_hook=hook)`` (di-scoped-lifecycle §3): the async-CM opens a
    per-call child container, runs ``hook`` for wire-side resolution
    (e.g. connection-string → typed config), runs DI resolution on the
    child (``Lazy[T]`` aware), yields merged kwargs, then unwinds
    per-call cleanups on exit with exception preservation.

    The wrapper's ``__signature__`` is rewritten to expose only wire
    kwargs (plus ``connection: str`` when the chain reaches it) so
    fastmcp's schema gen sees the agent-facing surface, not the
    injectables. ``Lazy[T]`` params are filtered out by
    ``wire_input_params``.

    When ``ctx_param_name`` is set, the tool's original ``ctx``
    parameter is re-appended to the rewritten signature so FastMCP's
    introspection sees it and injects the live ``Context`` at call
    time (closes the v0.32 MCP-transport regression).
    """
    from a2kit.signature import wire_input_params

    container = app.container()
    wire_params, wire_scopes_needed = wire_input_params(fn, container)
    needs_conn = "connection" in wire_scopes_needed

    # Skip wrapping only when there's truly nothing to do: no DI
    # injectables AND the tool already declares ctx (so FastMCP can
    # introspect ctx from fn's original signature without our help).
    # Post relax-ldd-ambient-requirement: tools without a declared
    # ctx still need a wrapper to synthesize ``_a2kit_ctx`` into the
    # rewritten signature so FastMCP injects ctx for ambient binding.
    if not _has_injectables(fn, container) and ctx_param_name is not None:
        # ctx already in fn's signature, no DI to wire — but ``__annotations__``
        # may still carry the ``a2kit.ToolContext`` Protocol, which pydantic
        # cannot schema-generate. Build a thin passthrough that rewrites the
        # ctx annotation to ``fastmcp.Context`` for FastMCP introspection.
        return _ctx_annotation_passthrough(fn, ctx_param_name)

    @functools.wraps(fn)
    async def _wrapped(**kwargs: Any) -> Any:
        # ctx is supplied by FastMCP — keep it out of dispatch's wire
        # kwargs so the pre_hook doesn't see it, and merge back before
        # invoking fn. The dispatch helper filters merged kwargs to fn's
        # declared params, so unrecognized keys are dropped anyway, but
        # explicitly partitioning avoids surprising the hook author.
        #
        # Post relax-ldd-ambient-requirement: tools without ctx in
        # signature have a synthesized ``_a2kit_ctx`` in the rewritten
        # wrapper signature (so FastMCP still injects). Pop it here so
        # the dispatch hook + tool body never see the framework-internal
        # name; the LDD wrapper (which runs inside `fn`'s wrapper chain)
        # already extracted it for ambient binding.
        ctx_value = kwargs.pop(ctx_param_name, None) if ctx_param_name else None
        kwargs.pop(SYNTHESIZED_CTX_PARAM_NAME, None)
        async with app._resolver.dispatch(fn, kwargs, pre_hook=hook) as merged:
            if ctx_param_name is not None and ctx_value is not None:
                merged[ctx_param_name] = ctx_value
            result = fn(**merged)
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
    _ensure_ctx_in_rewritten_signature(fn, new_params, ctx_param_name)
    _install_rewritten_signature(fn, _wrapped, new_params)
    return _wrapped


def _install_rewritten_signature(
    fn: Any,
    wrapped: Any,
    new_params: list[inspect.Parameter],
) -> None:
    """Set ``wrapped.__signature__`` and ``wrapped.__annotations__["return"]``
    to mirror ``fn``'s return type while exposing only ``new_params``
    on the wire side.

    Without this, tools with structured return types (``list[_Item]``,
    Pydantic models, etc.) lose their FastMCP output-schema after the
    rewrite. Decoration must not raise; failures degrade to leaving
    the return type unset and a one-shot WARN line.
    """
    ret_ann: Any = inspect.Signature.empty
    try:
        from typing import get_type_hints

        ret_ann = get_type_hints(fn).get("return", inspect.Signature.empty)
    except Exception as exc:  # noqa: BLE001 -- decoration must not raise; degrade observably
        name = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
        if name not in _WARN_ONCE:
            _WARN_ONCE.add(name)
            _log.warning("_wrap_with_dispatch_hook: failed to resolve return annotation for %s: %s", name, exc)

    # ``__signature__`` is the PEP 362 introspection target FastMCP
    # consults; setattr keeps the type checker happy without
    # suppression markers.
    setattr(  # noqa: B010
        wrapped,
        "__signature__",
        inspect.Signature(parameters=new_params, return_annotation=ret_ann),
    )
    # Rewrite ``__annotations__`` to match the rewritten signature.
    # functools.wraps copies the original ``fn.__annotations__`` which
    # may include an ``a2kit.ToolContext`` Protocol annotation — pydantic
    # cannot schema-generate Protocols. Sync ``__annotations__`` with the
    # rewritten params so any path that introspects via ``__annotations__``
    # (pydantic, get_type_hints) sees the same shape as ``__signature__``.
    new_annotations: dict[str, Any] = {}
    for param in new_params:
        if param.annotation is not inspect.Parameter.empty:
            new_annotations[param.name] = param.annotation
    if ret_ann is not inspect.Signature.empty:
        new_annotations["return"] = ret_ann
    wrapped.__annotations__ = new_annotations


#: Framework-reserved parameter name used when synthesizing a ctx
#: parameter into the rewritten MCP wrapper signature for tools whose
#: body does not declare ``ctx``. The single-underscore prefix is the
#: standard "private-ish" Python convention; the ``_a2kit_`` prefix is
#: reserved by the framework. Tool body authors never see this name —
#: the wrapper pops it from kwargs before invoking the body.
SYNTHESIZED_CTX_PARAM_NAME = "_a2kit_ctx"


def _ensure_ctx_in_rewritten_signature(
    fn: Any,
    new_params: list[inspect.Parameter],
    ctx_param_name: str | None,
) -> None:
    """Append a ``ctx`` Parameter to ``new_params`` so FastMCP
    introspects it and binds the live ``Context`` at call time.

    Two cases per relax-ldd-ambient-requirement:

    1. **Tool declared ctx** (``ctx_param_name`` is set): re-append the
       tool's original ``Parameter`` (preserves the consumer's chosen
       name + annotation). The wrapper later passes ctx through to the
       tool body kwargs.
    2. **Tool did NOT declare ctx**: synthesize a Parameter named
       ``_a2kit_ctx`` annotated ``fastmcp.Context`` (the resolved class,
       not a string). FastMCP injects ctx based on the type annotation
       regardless of name. The wrapper extracts via the synthesized
       name into ambient state, then pops it before invoking the body
       (the tool's original signature has no such param).

    The result is a framework-level invariant: every dispatched tool's
    rewritten signature includes a ctx Parameter, so ambient ctx is
    always non-None inside any framework dispatch.

    Raises :class:`A2KitContextBindingBroken` if the post-append
    invariant is broken (defensive guard against future wrapper-chain
    changes).
    """
    from a2kit.exceptions import A2KitContextBindingBroken

    if ctx_param_name:
        if ctx_param_name not in {p.name for p in new_params}:
            import fastmcp

            orig_ctx_param = inspect.signature(fn).parameters[ctx_param_name]
            # The rewritten signature feeds FastMCP/pydantic schema generation.
            # ``a2kit.ToolContext`` is a Protocol that pydantic cannot
            # schema-generate; substitute ``fastmcp.Context`` (the concrete
            # class FastMCP injects under the MCP transport) in the wrapper
            # signature. Tool body still receives the live ctx and its own
            # annotation is unchanged.
            new_params.append(
                orig_ctx_param.replace(
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=fastmcp.Context,
                )
            )
        if ctx_param_name not in {p.name for p in new_params}:
            raise A2KitContextBindingBroken(
                fn_name=getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>")),
                ctx_param_name=ctx_param_name,
            )
        return

    # Tool did not declare ctx: synthesize one so FastMCP injects ctx
    # for ambient state binding. The body never sees this kwarg — the
    # wrapper pops it before calling fn.
    if SYNTHESIZED_CTX_PARAM_NAME in {p.name for p in new_params}:
        return  # consumer collision? defensive — should never happen given _a2kit_ prefix
    import fastmcp

    new_params.append(
        inspect.Parameter(
            name=SYNTHESIZED_CTX_PARAM_NAME,
            kind=inspect.Parameter.KEYWORD_ONLY,
            annotation=fastmcp.Context,
        )
    )


def _has_injectables(fn: Any, container: Any) -> bool:
    if container is None:
        return False
    from a2kit.signature import wire_input_params

    base, _ = wire_input_params(fn, container=None)
    wire, wire_scopes = wire_input_params(fn, container=container)
    return len(wire) < len(base) or bool(wire_scopes)


def _router_for_tool(app: Any, fn: Any) -> Any | None:
    for r in app.routers():
        for tool_fn in r.bound_tools():
            if tool_fn is fn or getattr(tool_fn, "__func__", None) is getattr(fn, "__func__", None):
                return r
    return None


def _build_fastmcp_lifespan(app: Any, user_lifespan: Any | None) -> Any:
    """Build a FastMCP-shaped ``lifespan(server)`` adapter for the App.

    Sets ``server._a2kit_app = app`` as a back-reference for middleware
    and enters ``async with app:`` so singletons enter eagerly and
    routers are positioned to enter lazily on first dispatch. When a
    FastMCP-shaped ``user_lifespan(server)`` is provided, it nests
    inside the App lifecycle.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(server: Any) -> Any:
        server._a2kit_app = app
        async with app:
            if user_lifespan is None:
                yield None
            else:
                async with user_lifespan(server) as user_state:
                    yield user_state

    return _lifespan


def build_mcp_server(app: Any, **fastmcp_kwargs: Any) -> FastMCP:
    """Build a FastMCP server from an ``a2kit.App``.

    All ``fastmcp_kwargs`` flow straight to ``FastMCP.__init__`` — auth,
    providers, transforms, lifespan, tasks, sampling_handler, etc. a2kit owns
    no auth abstraction; FastMCP plugins work directly.

    The App's composed lifespan (its ``lifespan=`` callable plus every
    ``Router.lifespan``) is wrapped in a FastMCP-shaped adapter that
    sets ``server._a2kit_app = app`` as a back-reference and enters the
    a2kit lifespan + any caller-supplied FastMCP ``lifespan=`` in nested
    ``async with`` order: a2kit-enter → user-lifespan enter → user body
    → user-lifespan exit → a2kit-exit. The adapter is always installed
    (even when neither side contributes) so the back-reference is
    available unconditionally.
    """
    user_lifespan = fastmcp_kwargs.get("lifespan")
    fastmcp_kwargs["lifespan"] = _build_fastmcp_lifespan(app, user_lifespan)
    # `App(debug=True)` adds a `traceback` field to the wire-error envelope's
    # JSON payload. The envelope itself (see `_wrap_with_error_envelope`)
    # is installed unconditionally and owns the wire bytes via
    # `raise ToolError(json.dumps(...))`, bypassing FastMCP's
    # `mask_error_details` semantics entirely.
    app_debug = bool(getattr(app, "debug", False))
    if "mask_error_details" not in fastmcp_kwargs:
        fastmcp_kwargs["mask_error_details"] = not app_debug
    server = FastMCP(name=app.name, **fastmcp_kwargs)

    reports_enabled = app.ldd_reports
    events_enabled = app.ldd_events
    app_sinks: tuple[Any, ...] = app.ldd.sinks

    container = app.container()
    dispatch_hook = app.dispatch_hook()

    from a2kit._verb_validators import _BUILTIN_RESERVED_TOOL_NAMES, _RESERVED_TOOL_NAME_PREFIX

    for desc in app.tools():
        fn = desc.fn
        meta = get_meta(fn)
        if meta is None:
            continue

        # `"hidden"` and `"cli"` are CLI-only tiers; only `"all"` registers
        # on programmatic surfaces (MCP / future REST / future GraphQL).
        visibility = meta.extras.visibility or "all"
        if visibility != "all":
            continue

        router = _router_for_tool(app, fn)
        # Timeout wraps innermost (closest to fn) so DI cost and LDD
        # scope setup don't count against the budget. Cancel scope
        # lives inside the LDD scope and inside dispatch-hook DI.
        inner = fn
        if meta.extras.timeout_seconds is not None:
            inner = _wrap_with_timeout(inner, seconds=meta.extras.timeout_seconds)
        wrapped = _wrap_with_router_enrichers(inner, router)
        wrapped = _wrap_with_router_lazy_enter(wrapped, app, router)
        if container is not None and dispatch_hook is not None:
            wrapped = _wrap_with_dispatch_hook(
                wrapped,
                dispatch_hook,
                app,
                ctx_param_name=meta.context_param_name,
            )
        # Always enter the LDD scope. Post relax-ldd-ambient-requirement,
        # the dispatch-hook wrapper synthesizes ctx into the rewritten
        # signature for tools whose body doesn't declare ``ctx``; the
        # ldd_state wrapper extracts it from the synthesized name so
        # ambient ``ctx`` is always non-None inside any dispatch.
        # Cross-transport parity with the CLI runtime (cli/runtime.py).
        wrapped = _wrap_with_ldd_state(
            wrapped,
            ctx_param_name=meta.context_param_name,
            report_type=meta.extras.report_type,
            tool_name=meta.tool_name,
            reports_enabled=reports_enabled,
            events_enabled=events_enabled,
            sinks=app_sinks,
        )
        # Outermost: a2kit-owned wire-error envelope. Installed
        # unconditionally so the {class, message} contract holds in
        # production (debug=False) too; debug=True adds the traceback
        # field to the JSON payload.
        wrapped = _wrap_with_error_envelope(wrapped, debug=app_debug)

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
