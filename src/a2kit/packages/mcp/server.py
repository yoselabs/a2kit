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

from dataclasses import asdict
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool

from a2kit.metadata import A2KitMeta, get_meta
from a2kit.packages.dispatch import ToolBuildSpec, fold_pipeline
from a2kit.packages.mcp._wrappers import McpErrorRenderStage, install_mcp_signature
from a2kit.packages.mcp.format_routing import FormatRoutingMiddleware
from a2kit.packages.mcp.guards import GuardsMiddleware
from a2kit.packages.mcp.listview import ListViewMiddleware


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
    meta = get_meta(fn)
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
        descriptor=desc,
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
    return FunctionTool.from_function(
        wrapped,
        name=meta.tool_name,
        tags=tool_tags,
        annotations=meta.annotations,
        meta={"a2kit": _meta_to_dict(meta)},
    )


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


def build_mcp_server(
    app: Any,
    *,
    code_mode: bool = True,
    code_mode_allow_destructive: bool = False,
    compact: bool = False,
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

    # Per-tool encoding plans for the format-routing middleware and return
    # types for code-mode stub generation / dataclass marshalling, keyed by
    # the registered tool name. Only tools that actually reach the MCP
    # surface (visibility == "all") are collected.
    encoding_plans: dict[str, Any] = {}
    return_types: dict[str, Any] = {}

    for desc in app.tools():
        tool = _build_one_tool(
            app,
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
    server.add_middleware(
        FormatRoutingMiddleware(
            plans=encoding_plans,
            consumer="code" if code_mode else "llm",
            compact=compact,
        )
    )
    server.add_middleware(ListViewMiddleware())
    server.add_middleware(GuardsMiddleware())
    for mw in app.mcp_middlewares():
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
