"""`a2kit.App` — composition class that absorbs the FastMCP + store + registry +
runner wiring. Author writes:

    app = a2kit.App("my-mcp")
    todos = app.connect(TodoConn)
    app.use(TodoRouter)
    app.use(MyPlugin())
    app.run()

instead of constructing FastMCP, ConnectionStore, RouterRegistry, and MCPRunner
by hand and threading them through a `build_app()` helper.

Storage-agnostic: App itself doesn't touch the filesystem. The FS-backed
`ConnectionStore` (used by the built-in connection plugin) handles its own
directory creation lazily on first save. Users wanting a custom path pass
`app.connect(T, config_dir=Path("/custom"))`. Users wanting a non-FS backend
in v0.13+ will pass a custom Provider directly to App.

Escape hatches kept:
    app.server   — the underlying FastMCP instance
    app.runner   — the MCPRunner driving argv/transport/select
    app.cli      — a `click.Group` aggregating connection-management +
                   plugin-contributed commands.

Drop down to `app.server.tool()(fn)` or `app.runner.run(argv=...)` whenever
the convention doesn't fit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from a2kit.connections import ConnectionInfo, ConnectionStore, default_config_dir
from a2kit.scaffold import MCPRunner, Router, RouterRegistry, build_cli

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import click

    from a2kit.di import Plugin, Provider

C = TypeVar("C", bound=ConnectionInfo)


class App:
    """High-level composition. Wraps FastMCP + ConnectionStore(s) + RouterRegistry
    + MCPRunner. Author surface = `connect()` / `use()` / `run()`.

    Storage-agnostic: App does not create any filesystem directories itself.
    """

    def __init__(self, name: str) -> None:
        # Lazy import — keeps a2kit importable when FastMCP isn't installed.
        from mcp.server.fastmcp import FastMCP  # noqa: PLC0415

        self.name = name
        self.server: Any = FastMCP(name)

        self._stores: list[ConnectionStore[Any]] = []
        self._routers: list[Router] = []
        self._plugins: list[Plugin] = []
        self._providers: list[Any] = []
        self._runner: MCPRunner | None = None

        # v0.13: FastAPI-idiom test override map for `Annotated[T, Depends(factory)]`.
        # Key = the original factory callable referenced in `Depends(...)`.
        # Value = replacement callable (sync or async) returning the same type.
        # Mutate freely from tests: `app.dependency_overrides[get_conn] = fake_get_conn`.
        self.dependency_overrides: dict[Callable[..., Any], Callable[..., Any]] = {}

    def connect(self, conn_type: type[C], *, config_dir: Path | None = None) -> ConnectionStore[C]:
        """Register a `ConnectionStore[T]` for `conn_type`. Returns the store.

        `config_dir` defaults to `default_config_dir()` (which honors
        `A2KIT_CONFIG_HOME`, else `~/.config/a2kit/connections/`). The store
        creates the directory lazily on first save — App itself never touches
        the filesystem.

        Raises `ValueError` if the same `conn_type` is registered twice —
        in v0.12 each connection type maps to exactly one store. Need parallel
        stores? Subclass the type (`class StagingTodoConn(TodoConn): ...`).
        """
        for existing in self._stores:
            if existing.connection_class is conn_type:
                msg = (
                    f"App already has a ConnectionStore for {conn_type.__name__}. "
                    "v0.12: one type → one store. Subclass the type for parallel instances."
                )
                raise ValueError(msg)
        cd = config_dir if config_dir is not None else default_config_dir()
        store: ConnectionStore[C] = ConnectionStore(cd, conn_type)
        self._stores.append(store)
        return store

    def use(self, item: type[Router] | Router | Provider | Plugin) -> None:
        """Register a Router (instance or class), a Provider, or a Plugin.

        - A Router (or Router subclass) joins the RouterRegistry.
        - A Provider (anything with `provides: type` + async `get`) is added
          to the runner's chained-DI index and made available for tool
          auto-injection (`*, store: TrackerStore`).
        - Anything else is treated as a Plugin (legacy v0.12 shape — gets
          deleted in v0.13 per the Composition Root pivot).
        """
        from typing import cast as _cast  # noqa: PLC0415

        if isinstance(item, type) and issubclass(item, Router):
            instance = item()
            self._attach_overrides(instance)
            self._routers.append(instance)
        elif isinstance(item, Router):
            self._attach_overrides(item)
            self._routers.append(item)
        elif hasattr(item, "provides") and isinstance(item.provides, type):
            self._providers.append(_cast("Provider", item))
        else:
            # Anything else — assume Plugin.
            self._plugins.append(_cast("Plugin", item))

    def _attach_overrides(self, router: Router) -> None:
        """Pin the App's `dependency_overrides` dict onto the router so its
        `_apply_bindings` can forward it to each `@a2kit.tool(...)` call.
        Stored as a private attribute (set via object.__setattr__ to bypass
        Pydantic's `extra='forbid'`)."""
        object.__setattr__(router, "_a2kit_dependency_overrides", self.dependency_overrides)

    def _build_runner(self) -> MCPRunner:
        """Construct the underlying MCPRunner. Idempotent — caches on first call."""
        if self._runner is not None:
            return self._runner
        registry = RouterRegistry()
        for r in self._routers:
            # If the Router doesn't have an explicit store and we have exactly
            # one registered, wire it. If multiple — leave to the user (Router
            # construction site can pass `store=app.connect(...)`).
            if r.store is None and len(self._stores) == 1:
                r.store = self._stores[0]
            registry.add(r)
        # v0.12: stores stay in `store=` / Router.store. The `provides=` kwarg
        # is for explicit Provider instances (step 6+ work). Until ConnectionStore
        # itself satisfies the Provider Protocol, App keeps them separate.
        self._runner = MCPRunner(
            self.server,
            store=self._stores[0] if self._stores else None,
            router_registry=registry,
            plugins=self._plugins,
            provides=self._providers or None,
        )
        return self._runner

    @property
    def runner(self) -> MCPRunner:
        """Return (and lazily build) the underlying MCPRunner."""
        return self._build_runner()

    @property
    def cli(self) -> click.Group:
        """Return the unified Click group: `serve` + connection commands +
        `tools list/call` + plugin commands.

        v0.12: this is what `app.run()` invokes. Authors who want to embed
        the kit's CLI into their own bigger Click app can also access this
        property and add it as a subgroup.
        """
        return self._build_cli()

    # Built-in subcommand names — tool names colliding with these are rejected
    # at CLI build time (lint A2K-future will flag preventatively).
    _RESERVED_SUBCOMMANDS = frozenset({"serve", "login", "logout", "connections"})

    def _build_cli(self) -> click.Group:
        """Build the unified Click group. See `App.cli` for usage."""
        import click as _click  # noqa: PLC0415

        # Start from the connection-management group when we have a store —
        # gives us `login`, `logout`, `connections list/show/delete` for free.
        if self._stores:
            group = build_cli(self._stores[0], name=self.name)
        else:
            group = _click.Group(name=self.name)

        # `serve` — start the MCP server. Argv flags (`--http`, `--select`,
        # `--register`) live on this subcommand so they don't pollute the
        # parent group's namespace.
        @group.command("serve", help="Start the MCP server.")
        @_click.option("--http", default=None, help="HTTP transport [host[:port]]; omit for stdio.")
        @_click.option("--select", "select_expr", default=None, help="Router/tool select expression.")
        @_click.option("--scope", default=None, help="Scope filter for connections.")
        @_click.option(
            "--register",
            "registers",
            multiple=True,
            help='Register an ephemeral connection. Form: "router:key field=val ...".',
        )
        def serve(http: str | None, select_expr: str | None, scope: str | None, registers: tuple[str, ...]) -> None:
            runner_argv: list[str] = []
            if select_expr is not None:
                runner_argv += ["--select", select_expr]
            if scope is not None:
                runner_argv += ["--scope", scope]
            if http is not None:
                runner_argv += ["--http", http] if http else ["--http"]
            for reg in registers:
                runner_argv += ["--register", reg]
            self.run_server(argv=runner_argv)

        # Each registered tool becomes a top-level subcommand: `app <tool-name>`.
        # `--help` lists them alongside built-ins; no `tools list/call` ceremony.
        for tool_name in sorted(self._enumerate_tool_names()):
            if tool_name in self._RESERVED_SUBCOMMANDS:
                msg = (
                    f"Tool name {tool_name!r} collides with a built-in subcommand. "
                    f"Reserved: {sorted(self._RESERVED_SUBCOMMANDS)}. Rename via "
                    "`tool_name=` on the verb decorator."
                )
                raise ValueError(msg)
            self._add_tool_subcommand(group, tool_name)

        # Plugin-contributed commands.
        for cmd in self.runner.cli_commands:
            group.add_command(cmd)

        return group

    def _add_tool_subcommand(self, group: Any, tool_name: str) -> None:
        """Wire a tool as a top-level Click subcommand.

        UX: `app <tool-name> key=value [key=value ...]`. Lazy: routers are
        only applied when the subcommand is actually invoked, so building
        the CLI doesn't pre-register tools with FastMCP.
        """
        import click as _click  # noqa: PLC0415

        # Pull the docstring once for `--help` text.
        binding = self._find_binding_for_tool(tool_name)
        help_text = ""
        if binding is not None and binding.fn.__doc__:
            help_text = binding.fn.__doc__.splitlines()[0].strip()

        @group.command(tool_name, help=help_text or f"Invoke the {tool_name} tool.")
        @_click.argument("kwargs", nargs=-1)
        def _cmd(kwargs: tuple[str, ...], _name: str = tool_name) -> None:
            parsed: dict[str, Any] = {}
            for raw in kwargs:
                if "=" not in raw:
                    raise _click.BadParameter(f"expected key=value, got {raw!r}")
                k, v = raw.split("=", 1)
                parsed[k] = v
            self._invoke_tool(_name, parsed)

    def _enumerate_tool_names(self) -> list[str]:
        """Walk all registered routers' bindings; return tool names.

        Pre-decoration enumeration — does not apply routers (so it doesn't
        register tools with FastMCP). Used at CLI build time to know which
        subcommands to add.
        """
        names: list[str] = []
        for router in self._routers:
            for binding in router._tools:
                tool_name = binding.decorator_kwargs.get("tool_name") or binding.fn.__name__
                names.append(tool_name)
        return names

    def _find_binding_for_tool(self, tool_name: str) -> Any:
        """Find the `_ToolBinding` matching `tool_name` across all routers.

        Callers always pass names enumerated from `_enumerate_tool_names`, so
        the not-found path is unreachable in practice — we still return None
        defensively. Single comprehension keeps the branch graph trivial.
        """
        candidates = [
            (binding.decorator_kwargs.get("tool_name") or binding.fn.__name__, binding)
            for router in self._routers
            for binding in router._tools
        ]
        return next((b for n, b in candidates if n == tool_name), None)

    def _ensure_routers_applied(self) -> None:
        """Apply router registrations to the FastMCP server (idempotent)."""
        runner = self._build_runner()
        runner._prepare(argv=[], transport="stdio")

    def _invoke_tool(self, tool_name: str, kwargs: dict[str, Any]) -> None:
        """Look up the tool wrapper and invoke it with `kwargs`. Prints result."""
        import asyncio  # noqa: PLC0415
        import inspect  # noqa: PLC0415
        import json  # noqa: PLC0415

        import click as _click  # noqa: PLC0415

        # Apply routers so the tool wrapper exists on the server's tool manager.
        self._ensure_routers_applied()
        try:
            tools = self.server._tool_manager.list_tools()
        except AttributeError:  # pragma: no cover — defensive
            tools = []

        target = next((t for t in tools if t.name == tool_name), None)
        if target is None:
            available = ", ".join(t.name for t in tools)
            raise _click.ClickException(f"unknown tool {tool_name!r}. Available: {available}")

        fn = target.fn
        if inspect.iscoroutinefunction(fn):
            result = asyncio.run(fn(**kwargs))
        else:
            result = fn(**kwargs)

        # Best-effort serialisation: Pydantic models, dataclasses, plain dicts.
        try:
            if hasattr(result, "model_dump"):
                _click.echo(json.dumps(result.model_dump(), indent=2, default=str))
            elif isinstance(result, list) and result and hasattr(result[0], "model_dump"):
                _click.echo(json.dumps([r.model_dump() for r in result], indent=2, default=str))
            else:
                _click.echo(json.dumps(result, indent=2, default=str))
        except (TypeError, ValueError):
            _click.echo(repr(result))

    def run_server(self, argv: list[str] | None = None, *, transport: str | None = None) -> dict[str, Any]:
        """Start the MCP server directly. Equivalent to `app run serve --...`
        but bypasses Click — useful when embedding the kit in a host program
        that already owns the CLI.
        """
        return self._build_runner().run(argv=argv, transport=transport)

    def run(self, argv: list[str] | None = None) -> Any:
        """Build the CLI group and dispatch. Author entry point.

        With no args → prints help. With `serve` subcommand → runs the MCP
        server. Other subcommands → connection management, `tools list/call`,
        plugin commands.
        """
        return self.cli.main(args=argv, standalone_mode=False)

    async def run_async(self, argv: list[str] | None = None, *, transport: str | None = None) -> dict[str, Any]:
        """Async-mode equivalent of `run_server` — for embedding the MCP
        inside a host event loop. Awaits FastMCP's `server.run_async(...)`.
        """
        return await self._build_runner().run_async(argv=argv, transport=transport)


__all__ = ["App"]
