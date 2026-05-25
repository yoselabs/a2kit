"""``build_mcp_server(app, **fastmcp_kwargs) -> FastMCP``.

Forwards ``**fastmcp_kwargs`` to ``FastMCP.__init__`` so users can plug in
auth providers, lifespans, transforms, etc., without a2kit owning an
abstraction. Walks ``app.tools()`` and registers each as a ``FunctionTool``;
``A2KitMeta`` round-trips into ``tool.meta["a2kit"]`` for middleware to read.

Request-scoped DI: when ``app`` has registered providers (via
``app.provide(T, factory)``), the dispatch hook resolves typed kwargs
(``store: TrackerStore`` etc.) before the tool body runs.

The per-tool dispatch-wrapper chain lives in
:mod:`a2kit.packages.mcp._wrappers`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool

from a2kit.packages.dispatch import ToolBuildSpec, fold_pipeline

if TYPE_CHECKING:
    from a2kit.metadata import A2KitMeta
from a2kit.packages.mcp._wrappers import McpErrorRenderStage, TypedErrorEnvelopeMiddleware, install_mcp_signature
from a2kit.packages.mcp.format_routing import FormatRoutingMiddleware
from a2kit.packages.mcp.guards import GuardsMiddleware
from a2kit.packages.mcp.listview import ListViewMiddleware
from a2kit.packages.mcp.principal_middleware import PrincipalMiddleware


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


def _router_for_tool(app: Any, fn: Any) -> Any | None:
    for r in app.routers():
        for tool_fn in r.bound_tools():
            if tool_fn is fn or getattr(tool_fn, "__func__", None) is getattr(fn, "__func__", None):
                return r
    return None


def _build_one_tool(
    app: Any,
    desc: Any,
    *,
    reports_enabled: bool,
    events_enabled: bool,
    sinks: tuple[Any, ...],
) -> FunctionTool | None:
    """Build the FastMCP tool for one descriptor.

    Folds the transport-neutral ``DISPATCH_PIPELINE`` shared with the CLI
    adapter, appends the MCP-only error-render stage, then installs the
    FastMCP signature on the outermost callable. Returns ``None`` for a
    tool whose visibility is not ``"all"`` (CLI-only tiers do not reach
    the MCP surface).
    """
    from a2kit._verb_validators import _BUILTIN_RESERVED_TOOL_NAMES, _RESERVED_TOOL_NAME_PREFIX

    fn = desc.fn
    meta = desc._meta
    if meta is None:
        return None
    # `"hidden"` and `"cli"` are CLI-only tiers; only `"all"` registers
    # on programmatic surfaces (MCP / future REST / future GraphQL).
    if (meta.extras.visibility or "all") != "all":
        return None

    router = _router_for_tool(app, fn)
    spec = ToolBuildSpec(
        app=app,
        router=router,
        meta=meta,
        reports_enabled=reports_enabled,
        events_enabled=events_enabled,
        sinks=sinks,
    )
    # Fold the shared pipeline (timeout -> enrichers -> router-lazy-enter
    # -> dispatch-hook+DI -> ldd-state -> error-capture), then append the
    # MCP error-render stage. install_mcp_signature rewrites the
    # outermost callable's signature for FastMCP schema generation.
    wrapped = fold_pipeline(fn, spec)
    wrapped = McpErrorRenderStage().wrap(wrapped, spec)
    install_mcp_signature(fn, wrapped, app, meta)

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
    extra_kwargs: dict[str, Any] = {}
    union_schema = _maybe_build_union_output_schema(desc, wrapped)
    if union_schema is not None:
        extra_kwargs["output_schema"] = union_schema
    return FunctionTool.from_function(
        wrapped,
        name=meta.tool_name,
        tags=tool_tags,
        annotations=meta.annotations,
        meta={"a2kit": _meta_to_dict(meta)},
        **extra_kwargs,
    )


def _maybe_build_union_output_schema(desc: Any, wrapped: Any) -> dict[str, Any] | None:
    """When `desc.raises` is non-empty, return the oneOf union outputSchema.

    Branches: the bare ReturnT schema (computed via pydantic TypeAdapter) +
    the ErrorEnvelope schema. Returns None for tools without declared
    raises so FastMCP keeps its auto-generated bare schema.
    """
    if not desc.raises:
        return None
    from a2effect import ErrorEnvelope
    from pydantic import TypeAdapter

    return_type = desc.return_type
    try:
        bare_schema = TypeAdapter(return_type).json_schema()
    except Exception:  # noqa: BLE001 — schema generation must not break tool registration
        return None
    # MCP spec constraint: outputSchema MUST be type=object. Both union
    # branches are object schemas already; we add `type: object` at the
    # root so FastMCP's _is_object_schema check passes.
    return {
        "type": "object",
        "oneOf": [bare_schema, ErrorEnvelope.model_json_schema()],
    }


def _register_mcp_surface(server: FastMCP, runtime: Any) -> None:
    """Install ``@app.mcp.tool/.prompt/.resource`` registrations on ``server``.

    Each registration's ``fn`` is wrapped by
    ``install_substrate_signature(fn, "fastmcp", container)`` so a2kit
    DI is resolved per call from inside the wrapper. The wrapper's
    ``__signature__`` exposes only wire + ``Context``; FastMCP's
    schema introspection sees a clean surface with no DI types.

    Stamps ``runtime.mcp_surface.fastmcp_server = server`` so authors
    who need the underlying FastMCP instance (escape hatch:
    ``add_transform`` / ``add_middleware``) can reach it after build.
    """
    from a2kit.packages.dispatch import SURFACE_REGISTRY, install_substrate_signature

    surface = runtime.mcp_surface
    container = runtime.container()
    mcp_surface_obj = SURFACE_REGISTRY.get("mcp")
    for reg in surface.registrations:
        wrapped = install_substrate_signature(reg.fn, mcp_surface_obj, container)
        if reg.kind == "tool":
            server.tool(**reg.fastmcp_kwargs)(wrapped)
        elif reg.kind == "prompt":
            server.prompt(**reg.fastmcp_kwargs)(wrapped)
        elif reg.kind == "resource":
            # ``resource(uri, ...)`` — uri is positional.
            kwargs = dict(reg.fastmcp_kwargs)
            uri = kwargs.pop("uri")
            server.resource(uri, **kwargs)(wrapped)
    surface.fastmcp_server = server


def _build_mcp_mount_lifespan(app: Any, user_lifespan: Any | None) -> Any:
    """Build the MCP-mount ``lifespan(server)`` — transport-scoped only.

    Sets ``server._a2kit_app = app`` as a back-reference for middleware
    and nests any FastMCP-shaped ``user_lifespan(server)``. It does NOT
    enter ``async with app:``: the App lifecycle is owned by whoever
    mounts this server — the multiplex parent app
    (:mod:`a2kit.packages.serve`), or :func:`_build_standalone_lifespan`
    for the non-multiplexed (stdio) path. Entering the App per-mount
    would couple shutdowns — the first surface to exit would drain the
    shared DI container out from under the others.
    """

    @asynccontextmanager
    async def _lifespan(server: Any) -> Any:
        server._a2kit_app = app
        if user_lifespan is None:
            yield None
        else:
            async with user_lifespan(server) as user_state:
                yield user_state

    return _lifespan


def _build_standalone_lifespan(app: Any, user_lifespan: Any | None) -> Any:
    """Build the lifespan for a non-multiplexed MCP server that owns the App.

    Wraps :func:`_build_mcp_mount_lifespan` in a single ``async with
    app:``. Used for the stdio ``serve`` path, where there is no parent
    application to own the App lifecycle.
    """
    mount_lifespan = _build_mcp_mount_lifespan(app, user_lifespan)

    @asynccontextmanager
    async def _lifespan(server: Any) -> Any:
        async with app, mount_lifespan(server) as state:
            yield state

    return _lifespan


def build_mcp_server(
    app: Any,
    *,
    code_mode: bool = True,
    code_mode_allow_destructive: bool = False,
    compact: bool = False,
    own_app_lifecycle: bool = True,
    **fastmcp_kwargs: Any,
) -> FastMCP:
    """Build a FastMCP server from an ``a2kit.App``.

    All ``fastmcp_kwargs`` flow straight to ``FastMCP.__init__`` — auth,
    providers, transforms, lifespan, tasks, sampling_handler, etc. a2kit owns
    no auth abstraction; FastMCP plugins work directly.

    ``code_mode`` (default ``True``) installs the bundled code-execution
    surface: an ``A2kitCodeMode`` transform that collapses ``list_tools``
    into ``search`` / ``get_schema`` / ``execute`` meta-tools. Real tools
    stay callable by name. ``code_mode=False`` leaves the full catalog
    listed and no ``execute`` tool present. ``code_mode_allow_destructive``
    is the operator-side grant that lets the sandbox reach ``destructive``
    tools; it is off by default. See ``docs/VISION.md`` and
    ``a2kit.packages.codemode``.

    ``compact`` (default ``False``) is the operator escape hatch for
    non-conformant MCP clients: when set, the format-routing middleware
    drops the ``structuredContent`` channel entirely, leaving only the
    token-efficient ``content`` payload. Conformant clients leave it off —
    emitting both channels is spec-aligned (MCP SEP-1624).

    ``own_app_lifecycle`` (default ``True``) controls who enters the App
    lifecycle. When ``True`` the installed lifespan enters ``async with
    app:`` itself — the non-multiplexed (stdio) ``serve`` path, where no
    parent application exists. When ``False`` the lifespan carries only
    the ``server._a2kit_app`` back-reference and any caller-supplied
    FastMCP ``lifespan=``; the multiplex parent app
    (:mod:`a2kit.packages.serve`) then owns the single ``async with app:``
    for the whole process. The back-reference is installed in both modes.
    """
    # Finisher build: snapshot the App into a sealed runtime — validates
    # the DI provider graph and freezes a fresh container — before any
    # server bytes are built. Idempotent on an AppRuntime, so the
    # multiplex parent may build once and hand the runtime here. See ADR 0019.
    from a2kit.runtime import build

    runtime = build(app)
    user_lifespan = fastmcp_kwargs.get("lifespan")
    # `own_app_lifecycle` (default True) installs the standalone lifespan
    # that enters `async with runtime:` itself — the stdio `serve` path. The
    # multiplex parent passes `own_app_lifecycle=False` and owns the one
    # `async with runtime:` for the whole process; the mount lifespan then
    # carries only transport-scoped setup. See ADR multiplex-serve-topology.
    if own_app_lifecycle:
        fastmcp_kwargs["lifespan"] = _build_standalone_lifespan(runtime, user_lifespan)
    else:
        fastmcp_kwargs["lifespan"] = _build_mcp_mount_lifespan(runtime, user_lifespan)
    # `app.config.debug` (env `A2KIT_DEBUG=true`) adds a `traceback` field to
    # the wire-error envelope's JSON payload. The envelope itself (see
    # `_wrap_with_error_envelope`) is installed unconditionally and owns the
    # wire bytes via `raise ToolError(json.dumps(...))`, bypassing FastMCP's
    # `mask_error_details` semantics entirely.
    app_debug = bool(getattr(runtime, "debug", False))
    if "mask_error_details" not in fastmcp_kwargs:
        fastmcp_kwargs["mask_error_details"] = not app_debug
    server = FastMCP(name=runtime.name, **fastmcp_kwargs)

    reports_enabled = runtime.ldd_reports
    events_enabled = runtime.ldd_events
    app_sinks: tuple[Any, ...] = runtime.ldd.sinks

    # Per-tool encoding plans for the format-routing middleware and return
    # types for code-mode stub generation / dataclass marshalling, keyed by
    # the registered tool name. Only tools that actually reach the MCP
    # surface (visibility == "all") are collected.
    encoding_plans: dict[str, Any] = {}
    return_types: dict[str, Any] = {}

    for desc in runtime.tools():
        # Honour per-tool expose: a projection tool registered as
        # `@a2kit.read(expose=("api",))` does NOT appear on the FastMCP
        # surface. The pre-extension `_meta.*` health router uses
        # `_read_internal` which stamps default `expose=("mcp","api")`,
        # so it continues to land here.
        if "mcp" not in desc.expose:
            continue
        tool = _build_one_tool(
            runtime,
            desc,
            reports_enabled=reports_enabled,
            events_enabled=events_enabled,
            sinks=app_sinks,
        )
        if tool is None:
            continue
        server.add_tool(tool)
        encoding_plans[tool.name] = desc.encoding_plan
        return_types[tool.name] = desc.return_type

    # Register @app.mcp.tool / .prompt / .resource entries from the App's
    # mcp_surface. Each fn is wrapped via install_substrate_signature so
    # FastMCP's introspector sees only wire + reserved params and a2kit
    # DI is resolved per call from Container.call_scope inside the
    # wrapper body. These bypass the dispatch pipeline — they are
    # substrate-native (no LDD ambient, no projection format routing),
    # which is the whole point of the FastMCP-only family.
    if runtime.mcp_surface is not None:
        _register_mcp_surface(server, runtime)

    # Hide `_meta.*` tools from default `list_tools` output via FastMCP 3's
    # visibility-transform API. Selector is the `"_meta"` tag stamped above,
    # so future `_meta.*` additions inherit the rule.
    server.disable(tags={"_meta"})

    # Built-in middleware first; user-attached middlewares (via add_mcp_middleware) after.
    # Format routing is outermost so its post-call content re-derivation runs
    # AFTER ListViewMiddleware has rewritten ``structured_content`` — the two
    # channels stay equivalent. The consumer regime is fixed by ``code_mode``:
    # code mode renders real tools for the sandbox (``code``, uncompressed);
    # otherwise real tools face the LLM (``llm``, compressed).
    # Typed-error envelope middleware runs outermost on the error path:
    # paired with `McpErrorRenderStage`, it patches `structured_content =
    # {"error": <envelope>}` onto the CallToolResult that FastMCP built
    # from the prose-shaped `ToolError`. See `error-envelope-rendering`.
    server.add_middleware(TypedErrorEnvelopeMiddleware())
    # ADR 0022: structured_output is a consumer-owned concern — read from
    # `app.config.mcp.structured_output` (env: A2KIT_MCP__STRUCTURED_OUTPUT).
    # When True, success-path content[] gets a short marker; structured stays
    # canonical. Default (False) keeps spec-prescribed dual-emit. Mutually
    # exclusive with `compact`: if both are requested, structured_output wins
    # (modern wire shape over legacy-client escape hatch).
    _structured_output = bool(getattr(getattr(app, "config", None), "mcp", None) and app.config.mcp.structured_output)
    server.add_middleware(
        FormatRoutingMiddleware(
            plans=encoding_plans,
            consumer="code" if code_mode else "llm",
            compact=compact and not _structured_output,
            structured_output=_structured_output,
        )
    )
    server.add_middleware(ListViewMiddleware())
    server.add_middleware(GuardsMiddleware())
    # Publish Principal on `_a2kit_request_principal` so DispatchHookStage and
    # AuthorizeGateStage seed it as SCOPED in the per-call DI scope.
    server.add_middleware(PrincipalMiddleware())
    for mw in runtime.mcp_middlewares():
        server.add_middleware(mw)

    # Code-execution surface. Installed last so the transform sees the
    # final tool catalog. Imported here (not at module scope) so
    # `import a2kit.packages.mcp` does not pull FastMCP's `experimental`
    # namespace until a server actually opts into code mode.
    if code_mode:
        from a2kit.packages.codemode import build_code_mode_transform

        server.add_transform(
            build_code_mode_transform(
                allow_destructive=code_mode_allow_destructive,
                return_types=return_types,
            )
        )
    return server


__all__ = ["build_mcp_server"]
