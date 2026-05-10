from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING, Any

from a2kit.routers import Router, RouterRegistry
from a2kit.tool import ToolDescriptor, identity_dispatch_hook

if TYPE_CHECKING:
    from collections.abc import Callable

    import click


class _Unresolved:
    """Sentinel for ``App.singletons()`` entries that have been registered but not yet built."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<UNRESOLVED>"


#: Public singleton-not-yet-resolved sentinel exported as ``a2kit.UNRESOLVED``.
UNRESOLVED: Any = _Unresolved()


class _SingletonWrapper:
    """Provider wrapper that caches the user factory's first result on the App.

    The container introspects ``__signature__`` to see the underlying user
    factory's parameters (so chain resolution still works). On first call,
    invokes the user factory; on subsequent calls returns the cached value.
    Async user factories are coalesced under an :class:`asyncio.Lock` lazily
    created on first concurrent first-resolve.
    """

    _is_a2kit_singleton = True

    def __init__(self, type_: type, user_factory: Callable[..., Any], app: App) -> None:
        self.type_ = type_
        self.user_factory = user_factory
        self.app = app
        self.is_async = inspect.iscoroutinefunction(user_factory)
        self._lock: asyncio.Lock | None = None

    @property
    def __signature__(self) -> inspect.Signature:  # type: ignore[override]
        target: Any = self.user_factory
        if inspect.isclass(target):
            target = target.__init__
        return inspect.signature(target)

    def is_resolved(self) -> bool:
        return self.app._singletons.get(self.type_, UNRESOLVED) is not UNRESOLVED

    def get_cached(self) -> Any:
        return self.app._singletons[self.type_]

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        cached = self.app._singletons.get(self.type_, UNRESOLVED)
        if cached is not UNRESOLVED:
            return cached
        if self.is_async:
            return self._resolve_async(*args, **kwargs)
        result = self.user_factory(*args, **kwargs)
        self.app._singletons[self.type_] = result
        return result

    async def _resolve_async(self, *args: Any, **kwargs: Any) -> Any:
        cached = self.app._singletons.get(self.type_, UNRESOLVED)
        if cached is not UNRESOLVED:
            return cached
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            cached = self.app._singletons.get(self.type_, UNRESOLVED)
            if cached is not UNRESOLVED:
                return cached
            result = await self.user_factory(*args, **kwargs)
            self.app._singletons[self.type_] = result
            return result


class App:
    """Composition root.

    Three named verbs: :meth:`add_router`, :meth:`add_cli`,
    :meth:`add_mcp_middleware`. No polymorphic dispatch, no plugin
    registry, no class-keyed DI in core. Routers are constructed with
    their dependencies via plain Python ``__init__`` and registered
    explicitly.

    Request-scoped DI is layered via :meth:`provide` — calling it once
    installs a non-identity dispatch hook from
    ``a2kit.packages.connections.container``. Apps that never call
    ``provide`` keep the identity hook and pay zero overhead.
    """

    def __init__(self, name: str, *, health_tool: bool = False, debug: bool = False) -> None:
        self.name = name
        self.debug = debug
        self._routers = RouterRegistry()
        self._descriptors: list[ToolDescriptor] = []
        self._cli_extras: list[click.Command] = []
        self._mcp_middlewares: list[Any] = []
        # Lazy: created on first .provide() call.
        self._container: Any | None = None
        self._dispatch_hook: Callable[..., Any] = identity_dispatch_hook
        # LDD kill-switch — env A2KIT_LDD=off disables both channels at
        # startup; ``set_ldd(...)`` and CLI flags override per-invocation.
        import os

        env_off = os.environ.get("A2KIT_LDD", "").lower() == "off"
        self._ldd_reports = not env_off
        self._ldd_events = not env_off
        # App-scoped singletons (Section 2 of app-lifecycle-and-di-ergonomics).
        self._singletons: dict[type, Any] = {}
        # Lifecycle handlers (Section 3).
        self._startup_handlers: list[Callable[[App], Any]] = []
        self._shutdown_handlers: list[Callable[[App], Any]] = []
        self._lifecycle_started: bool = False
        # Typed event registry (Section 9b of fastmcp-context-passthrough).
        # Lazy import keeps the cold-start path off `a2kit.packages.ldd` for
        # apps that never touch typed events.
        from a2kit.packages.ldd import _AppLdd

        self.ldd = _AppLdd()

        # Health probe (round-2). Disabled by default — opt in via constructor.
        from a2kit.packages.health import HealthRegistry

        self._health: HealthRegistry = HealthRegistry(enabled=health_tool)
        if health_tool:
            self._install_health_tool()

    def _install_health_tool(self) -> None:
        """Synthesize a built-in router carrying ``_meta.health``.

        The tool name embeds the reserved ``_meta.`` prefix so it doesn't
        collide with user tools. It reads ``app._health`` via closure to
        aggregate registered checks at invocation time.
        """
        from a2kit.packages.health import HEALTH_TOOL_NAME, run_checks
        from a2kit.routers import Router as _Router
        from a2kit.tool import read as _read

        app_ref = self

        class _MetaRouter(_Router):
            name = "_meta"

            @_read(name=HEALTH_TOOL_NAME, title="Health probe")
            async def aggregated_health(self) -> dict[str, Any]:
                """Aggregated health status. Hidden from agent-facing list_tools."""
                return await run_checks(app_ref)

        self.add_router(_MetaRouter())

    def health_check(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register ``fn`` as a readiness probe for ``_meta.health``.

        ``fn`` may be sync or async, take any DI-resolvable kwargs (e.g.
        ``state: AppState``), and SHOULD return a :class:`HealthResult`.
        Returns the function unchanged for ``@app.health_check`` use.
        """
        return self._health.register(fn)

    # --- Composition verbs ---------------------------------------------- #

    def add_router(self, router: Router) -> App:
        slug = router.slug
        existing = next((r for r in self._routers.all() if r.slug == slug), None)
        if existing is not None and existing is not router:
            msg = f"router slug {slug!r} already registered by {type(existing).__name__!r}; declare an explicit name= or rename the class"
            raise ValueError(msg)
        self._routers.add(router)
        self._descriptors.extend(_build_descriptors(router))
        return self

    def add_cli(self, command: click.Command) -> App:
        # Detect connections-cli markers and auto-register typed providers.
        types_marker = getattr(command, "_a2kit_connections_types", None)
        if types_marker:
            self._auto_register_connections(tuple(types_marker))
        self._cli_extras.append(command)
        return self

    def add_mcp_middleware(self, middleware: Any) -> App:
        self._mcp_middlewares.append(middleware)
        return self

    def cli_extras(self) -> list[click.Command]:
        return list(self._cli_extras)

    def mcp_middlewares(self) -> list[Any]:
        return list(self._mcp_middlewares)

    # --- DI: typed providers ------------------------------------------- #

    def provide(
        self,
        type_: type,
        factory: Callable[..., Any] | None = None,
    ) -> App:
        """Register a typed provider for ``type_``.

        When ``factory`` is omitted, the class itself is the factory and
        the container introspects ``type_.__init__`` at resolve time.
        """
        self._ensure_container()
        container: Any = self._container
        container.register(type_, factory)
        return self

    def has_provider(self, type_: type) -> bool:
        if self._container is None:
            return False
        return self._container.has(type_)

    def container(self) -> Any | None:
        return self._container

    # --- DI: App-scoped singletons -------------------------------------- #

    def singleton(
        self,
        type_: type,
        factory: Callable[..., Any] | None = None,
    ) -> Any:
        """Register a factory whose result is cached for the lifetime of this App.

        Two forms:

        - Method: ``app.singleton(T, factory)`` returns ``self`` for chaining.
        - Decorator: ``@app.singleton(T)`` decorates the factory and returns it
          unchanged after registering.

        The factory MUST NOT depend on ``connection`` (directly or transitively).
        Connection-bound state belongs in :meth:`provide`, which constructs
        fresh per dispatch.
        """
        if factory is None:

            def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                self.singleton(type_, fn)
                return fn

            return _decorator

        self._ensure_container()
        container: Any = self._container
        self._reject_singleton_connection_dep(type_, factory, container)
        wrapper = _SingletonWrapper(type_, factory, self)
        # Register the not-yet-resolved sentinel so introspection sees it.
        if type_ not in self._singletons:
            self._singletons[type_] = UNRESOLVED
        container.register(type_, wrapper)
        return self

    def has_singleton(self, type_: type) -> bool:
        return type_ in self._singletons

    def singletons(self) -> dict[type, Any]:
        """Snapshot of registered singletons; unresolved entries carry :data:`UNRESOLVED`."""
        return dict(self._singletons)

    @staticmethod
    def _reject_singleton_connection_dep(
        type_: type,
        factory: Callable[..., Any],
        container: Any,
    ) -> None:
        from a2kit.signature import resolve_hints

        target: Any = factory
        if inspect.isclass(target):
            target = target.__init__
        hints = resolve_hints(target)
        try:
            sig = inspect.signature(target)
        except (TypeError, ValueError):
            return
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            ann = hints.get(pname, param.annotation)
            if pname == "connection" and (ann is str or ann is inspect.Parameter.empty):
                msg = (
                    f"singleton factory for {type_!r} cannot depend on `connection`; "
                    "use App.provide(...) instead — connection-bound state must be "
                    "constructed per dispatch."
                )
                raise ValueError(msg)
            if container.has(ann) and container._chain_reaches_connection(ann):
                msg = f"singleton factory for {type_!r} transitively depends on `connection` via {ann!r}; use App.provide(...) instead."
                raise ValueError(msg)

    # --- Lifecycle handlers --------------------------------------------- #

    def on_startup(
        self,
        handler: Callable[[App], Any] | None = None,
    ) -> Any:
        """Register an async or sync handler invoked once before the first tool dispatch.

        Usable as a method (``app.on_startup(fn)`` returns ``self``) or as a
        decorator (``@app.on_startup`` returns the original function).
        """
        if handler is None:

            def _decorator(fn: Callable[[App], Any]) -> Callable[[App], Any]:
                self._startup_handlers.append(fn)
                return fn

            return _decorator
        self._startup_handlers.append(handler)
        return handler

    def on_shutdown(
        self,
        handler: Callable[[App], Any] | None = None,
    ) -> Any:
        """Register an async or sync handler invoked once after the last tool dispatch.

        Shutdown handlers run in reverse registration order. A raised exception
        is logged via ``a2kit.lifecycle`` but does not abort sibling handlers.
        """
        if handler is None:

            def _decorator(fn: Callable[[App], Any]) -> Callable[[App], Any]:
                self._shutdown_handlers.append(fn)
                return fn

            return _decorator
        self._shutdown_handlers.append(handler)
        return handler

    def has_lifecycle_handlers(self) -> bool:
        return bool(self._startup_handlers) or bool(self._shutdown_handlers)

    def dispatch_hook(self) -> Callable[..., Any]:
        return self._dispatch_hook

    # --- LDD kill-switch ------------------------------------------------ #

    def set_ldd(self, *, reports: bool | None = None, events: bool | None = None) -> App:
        if reports is not None:
            self._ldd_reports = reports
        if events is not None:
            self._ldd_events = events
        return self

    @property
    def ldd_reports(self) -> bool:
        return self._ldd_reports

    @property
    def ldd_events(self) -> bool:
        return self._ldd_events

    # --- Router / tool aggregation -------------------------------------- #

    def routers(self) -> list[Router]:
        return self._routers.all()

    def tools(self) -> list[Callable[..., Any]]:
        return self._routers.tools()

    def tool_descriptors(self) -> list[ToolDescriptor]:
        """Typed descriptors materialized at ``add_router`` time. One per tool.

        Each descriptor carries the resolved return type and the pre-computed
        ``format_hint`` so the CLI runtime can dispatch encoders without
        re-running type inference per call.
        """
        return list(self._descriptors)

    # --- internals ----------------------------------------------------- #

    def _ensure_container(self) -> None:
        if self._container is not None:
            return
        from a2kit.packages.connections.container import Container, container_dispatch

        self._container = Container()
        container = self._container

        async def _hook(fn: Callable[..., Any], wire_kwargs: dict[str, Any]) -> dict[str, Any]:
            return await container_dispatch(fn, wire_kwargs, container)

        self._dispatch_hook = _hook

    def _auto_register_connections(self, conn_types: tuple[type, ...]) -> None:
        """Delegate to the connections package's typed-provider installer."""
        from a2kit.packages.connections.container import install_connection_providers

        self._ensure_container()
        container: Any = self._container
        install_connection_providers(container, conn_types)


def _build_descriptors(router: Router) -> list[ToolDescriptor]:
    """Materialize one ``ToolDescriptor`` per tool on ``router``.

    Resolves return-type annotations (handling ``from __future__ import
    annotations`` and string-quoted forward refs) and computes each tool's
    ``format_hint`` via ``infer_format_hint``. On any resolution failure, the
    descriptor falls back to ``return_type=None`` and ``format_hint="json"``
    and a warning is logged once per tool.
    """
    from a2kit.metadata import get_meta
    from a2kit.packages.formatter.inference import infer_format_hint
    from a2kit.signature import resolve_hints

    out: list[ToolDescriptor] = []
    for fn in router.tools():
        hints = resolve_hints(fn)
        return_type = hints.get("return")
        format_hint = infer_format_hint(return_type)
        meta = get_meta(fn)
        # Prefer meta.tool_name (honors decorator `name=` override) over the
        # raw function name. Falls back to the function name when meta is
        # missing (shouldn't happen for tools but defensive).
        name = meta.tool_name if meta is not None else getattr(fn, "__name__", "<callable>")
        out.append(
            ToolDescriptor(
                name=name,
                router=router,
                fn=fn,
                return_type=return_type,
                format_hint=format_hint,
            )
        )
    return out


_LIFECYCLE_LOG = logging.getLogger("a2kit.lifecycle")


async def dispatch_startup(app: App) -> None:
    """Invoke registered startup handlers in registration order.

    A handler that raises aborts the sequence; remaining startup handlers do
    NOT run, and shutdown handlers MUST NOT run (the caller enforces this by
    catching here and skipping shutdown). The first raised exception
    propagates unchanged.
    """
    for handler in app._startup_handlers:
        result = handler(app)
        if inspect.isawaitable(result):
            await result


async def dispatch_shutdown(app: App) -> None:
    """Invoke registered shutdown handlers in reverse registration order.

    A handler that raises is logged via ``a2kit.lifecycle`` and swallowed; the
    remaining handlers continue to run. The original exit reason of the
    surrounding scope (if any) MUST NOT be masked by shutdown failures.
    """
    for handler in reversed(app._shutdown_handlers):
        try:
            result = handler(app)
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001
            _LIFECYCLE_LOG.exception(
                "shutdown handler %r raised; continuing",
                getattr(handler, "__name__", repr(handler)),
            )
