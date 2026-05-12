from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any

from a2kit.packages.di.container import (
    _UNRESOLVED,
    Container,
    container_dispatch,
    container_dispatch_async,
)
from a2kit.routers import Router, RouterRegistry
from a2kit.tool import ToolDescriptor

if TYPE_CHECKING:
    from collections.abc import Callable

    import click


#: Public singleton-not-yet-resolved sentinel exported as ``a2kit.UNRESOLVED``.
UNRESOLVED: Any = _UNRESOLVED


class App:
    """Composition root.

    Three named verbs: :meth:`add_router`, :meth:`add_cli`,
    :meth:`add_mcp_middleware`. No polymorphic dispatch, no plugin
    registry, no class-keyed DI in core. Routers are constructed with
    their dependencies via plain Python ``__init__`` and registered
    explicitly.

    Request-scoped DI is provided by a :class:`a2kit.packages.di.Container`
    eagerly initialized on every App. Providers and singletons register
    sync factories; async resource initialization happens in resource
    classes (lazy-init pattern), not in DI factories. Wire-input
    transformation (e.g. ``connection: str`` → typed config) happens at
    the dispatch-hook seam in the consumer package (e.g. connections),
    not inside the container.
    """

    def __init__(self, name: str, *, health_tool: bool = False, debug: bool = False) -> None:
        self.name = name
        self.debug = debug
        self._routers = RouterRegistry()
        self._descriptors: list[ToolDescriptor] = []
        self._cli_extras: list[click.Command] = []
        self._mcp_middlewares: list[Any] = []
        # Eager container init — sync, ~80 LOC, always available.
        self._container: Container = Container()
        # Default dispatch hook is sync container_dispatch. Consumer packages
        # (e.g. connections) can replace it with an async wrap that does wire
        # preprocessing before delegating to container.apply_kwargs.
        self._dispatch_hook: Callable[..., Any] = self._default_dispatch_hook
        # LDD kill-switch — env A2KIT_LDD=off disables both channels at
        # startup; ``set_ldd(...)`` and CLI flags override per-invocation.
        import os

        env_off = os.environ.get("A2KIT_LDD", "").lower() == "off"
        self._ldd_reports = not env_off
        self._ldd_events = not env_off
        # Lifecycle handlers (DI-aware).
        self._startup_handlers: list[Callable[..., Any]] = []
        self._shutdown_handlers: list[Callable[..., Any]] = []
        self._lifecycle_started: bool = False
        # Router-declared lifespan context managers, composed in
        # registration order at startup and unwound LIFO at shutdown.
        # Replaced by ``a2kit.lifespan.compose`` after the sibling
        # ``lifespan-over-lifecycle-hooks`` proposal lands.
        self._router_lifespans: list[Router] = []
        self._router_lifespan_stack: Any = None
        # Typed event registry. Lazy import keeps the cold-start path off
        # `a2kit.packages.ldd` for apps that never touch typed events.
        from a2kit.packages.ldd import _AppLdd

        self.ldd = _AppLdd()

        # Health probe (round-2). Disabled by default — opt in via constructor.
        from a2kit.packages.health import HealthRegistry

        self._health: HealthRegistry = HealthRegistry(enabled=health_tool)
        # Test-seam: TestClient sessions claim this slot via __aenter__ so
        # overlapping sessions on the same App fail loud. Production code
        # never touches this attribute.
        self._test_override_owner: Any = None
        if health_tool:
            self._install_health_tool()

    def _default_dispatch_hook(
        self,
        fn: Callable[..., Any],
        wire_kwargs: dict[str, Any],
    ) -> Any:
        """Default dispatch hook backed by the container.

        Switches to the async resolution path if any singleton has an
        async factory, so async-factory singletons are awaited on first
        resolution. Otherwise stays synchronous (existing hot path,
        identical behaviour for apps that never touch async factories).
        """
        if self._container.has_any_async_singletons():
            return container_dispatch_async(fn, wire_kwargs, self._container)
        return container_dispatch(fn, wire_kwargs, self._container)

    def _install_health_tool(self) -> None:
        """Synthesize a built-in router carrying ``_meta.health``."""
        from a2kit.packages.health import HEALTH_TOOL_NAME, run_checks
        from a2kit.routers import Router as _Router
        from a2kit.tool import read as _read

        app_ref = self

        class _MetaRouter(_Router):
            slug = "_meta"

            @_read(name=HEALTH_TOOL_NAME, title="Health probe")
            async def aggregated_health(self) -> dict[str, Any]:
                """Aggregated health status. Hidden from agent-facing list_tools."""
                return await run_checks(app_ref)

            tools = (aggregated_health,)

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
            msg = (
                f"router slug {slug!r} already registered by "
                f"{type(existing).__name__!r}; rename the subclass or change "
                "its `slug` class attribute"
            )
            raise ValueError(msg)
        self._routers.add(router)
        self._descriptors.extend(_build_descriptors(router))
        # Install Router-declared providers.
        for entry in getattr(router, "providers", ()):
            if isinstance(entry, tuple):
                ptype, pfactory = entry
                self.provide(ptype, pfactory)
            else:
                self.provide(entry)
        # Router-declared lifespan composes into App lifecycle. The Router
        # exposes a single ``@asynccontextmanager async def lifespan(self):``
        # method (or omits the attribute). When present, register it as a
        # combined startup/shutdown pair so existing dispatch_startup/_shutdown
        # plumbing carries the work; the sibling ``lifespan-over-lifecycle-hooks``
        # proposal will replace this bridge with ``a2kit.lifespan.compose``.
        cls = type(router)
        if "lifespan" in cls.__dict__:
            self._register_router_lifespan(router)
        return self

    def _register_router_lifespan(self, router: Router) -> None:
        """Bridge a Router's ``lifespan`` context manager into App lifecycle.

        Minimal bridge until the sibling ``lifespan-over-lifecycle-hooks``
        proposal lands ``a2kit.lifespan.compose``. Stores the lifespan method
        on the App so dispatch_startup/dispatch_shutdown enter/exit it in
        registration order.
        """
        self._router_lifespans.append(router)

    def add_cli(self, command: click.Command) -> App:
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
        Factories MUST be synchronous.
        """
        self._container.register(type_, factory)
        return self

    def has_provider(self, type_: type) -> bool:
        return self._container.has(type_)

    def container(self) -> Container:
        """Return the App's container. Never None (eager-init)."""
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

        The factory MAY be sync (``def``) or async (``async def``). An
        async factory is awaited on first resolution; subsequent resolves
        return the cached instance. Concurrent first-resolution calls
        coalesce on a per-type ``asyncio.Lock`` — the factory runs at
        most once. Sync ``container.resolve(T)`` on an unresolved async
        singleton raises a clear error; warm-up via ``@on_startup`` (or
        any first call from inside the event loop) primes the cache.

        This is the primary path for async-opened resources (DB pools,
        HTTP clients, browser handles). Hand-rolled lazy-init resource
        classes are no longer necessary for the common case.
        """
        if factory is None:

            def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                self.singleton(type_, fn)
                return fn

            return _decorator

        self._container.register_singleton(type_, factory)
        return self

    def has_singleton(self, type_: type) -> bool:
        return self._container.has_singleton(type_)

    def singletons(self) -> dict[type, Any]:
        """Snapshot of registered singletons; unresolved entries carry :data:`UNRESOLVED`."""
        return self._container.singletons()

    # --- Lifecycle handlers (DI-aware) ---------------------------------- #

    def on_startup(
        self,
        handler: Callable[..., Any] | None = None,
    ) -> Any:
        """Register a startup handler invoked once before the first tool dispatch.

        Handlers may take arbitrary DI-resolvable kwargs (e.g. ``state: AppState``)
        which are resolved through ``container.apply_kwargs`` at dispatch time.
        Sync and async handlers both supported.
        """
        if handler is None:

            def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                self._startup_handlers.append(fn)
                return fn

            return _decorator
        self._startup_handlers.append(handler)
        return handler

    def on_shutdown(
        self,
        handler: Callable[..., Any] | None = None,
    ) -> Any:
        """Register a shutdown handler invoked once after the last tool dispatch.

        Handlers are DI-aware (same model as ``on_startup``). Shutdown handlers
        run in reverse registration order. A raised exception is logged but
        does not abort sibling handlers.
        """
        if handler is None:

            def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                self._shutdown_handlers.append(fn)
                return fn

            return _decorator
        self._shutdown_handlers.append(handler)
        return handler

    def has_lifecycle_handlers(self) -> bool:
        return (
            bool(self._startup_handlers)
            or bool(self._shutdown_handlers)
            or bool(self._router_lifespans)
        )

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
        return self._routers.bound_tools()

    def tool_descriptors(self) -> list[ToolDescriptor]:
        """Typed descriptors materialized at ``add_router`` time. One per tool."""
        return list(self._descriptors)


def _build_descriptors(router: Router) -> list[ToolDescriptor]:
    """Materialize one ``ToolDescriptor`` per tool on ``router``."""
    from a2kit.metadata import get_meta
    from a2kit.packages.formatter.inference import infer_format_hint
    from a2kit.signature import resolve_hints

    out: list[ToolDescriptor] = []
    for fn in router.bound_tools():
        hints = resolve_hints(fn)
        return_type = hints.get("return")
        format_hint = infer_format_hint(return_type)
        meta = get_meta(fn)
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


def _call_lifecycle_handler(app: App, handler: Callable[..., Any]) -> Any:
    """Resolve handler kwargs via DI, then invoke. Awaitable if handler is async."""
    kwargs = app._container.apply_kwargs(handler, {})
    return handler(**kwargs)


async def dispatch_startup(app: App) -> None:
    """Invoke registered startup handlers in registration order (DI-resolved).

    A handler that raises aborts the sequence; remaining startup handlers do
    NOT run, and shutdown handlers MUST NOT run (the caller enforces this by
    catching here and skipping shutdown). The first raised exception
    propagates unchanged.

    After explicit startup handlers, Router-declared ``lifespan`` context
    managers are entered in ``add_router`` registration order on a shared
    ``AsyncExitStack`` stored on the App. The stack is unwound LIFO from
    :func:`dispatch_shutdown`.
    """
    for handler in app._startup_handlers:
        result = _call_lifecycle_handler(app, handler)
        if inspect.isawaitable(result):
            await result
    if app._router_lifespans:
        from contextlib import AsyncExitStack

        stack = AsyncExitStack()
        try:
            for router in app._router_lifespans:
                cm = _resolve_router_lifespan_cm(app, router)
                await stack.enter_async_context(cm)
        except BaseException:
            await stack.aclose()
            raise
        app._router_lifespan_stack = stack


async def dispatch_shutdown(app: App) -> None:
    """Invoke registered shutdown handlers in reverse registration order (DI-resolved).

    A handler that raises is logged via ``a2kit.lifecycle`` and swallowed; the
    remaining handlers continue to run.

    Router-declared ``lifespan`` context managers are unwound LIFO before the
    explicit shutdown handlers run.
    """
    stack = app._router_lifespan_stack
    if stack is not None:
        app._router_lifespan_stack = None
        try:
            await stack.aclose()
        except Exception:  # noqa: BLE001
            _LIFECYCLE_LOG.exception(
                "Router lifespan stack raised on shutdown; continuing"
            )
    for handler in reversed(app._shutdown_handlers):
        try:
            result = _call_lifecycle_handler(app, handler)
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001
            _LIFECYCLE_LOG.exception(
                "shutdown handler %r raised; continuing",
                getattr(handler, "__name__", repr(handler)),
            )


def _resolve_router_lifespan_cm(app: App, router: Router) -> Any:
    """Call a Router's ``lifespan`` method with DI-resolved kwargs.

    Returns the async context manager the method produced. Typed kwargs
    (e.g. ``store: TrackerStore``) flow through ``container.apply_kwargs``
    so the lifespan body sees fully-resolved dependencies, matching the
    DI behaviour the previous ``on_startup`` / ``on_shutdown`` decorators
    provided.
    """
    method = router.lifespan  # type: ignore[attr-defined]
    kwargs = app._container.apply_kwargs(method, {})
    return method(**kwargs)
