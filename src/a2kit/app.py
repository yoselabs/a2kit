from __future__ import annotations

import inspect
import logging
from contextlib import nullcontext
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


_LIFECYCLE_LOG = logging.getLogger("a2kit.lifecycle")


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

    Lifecycle:

    Pass a ``lifespan`` callable to ``__init__``. It MUST be defined
    with ``async def`` and SHOULD be decorated with
    ``@contextlib.asynccontextmanager``. The signature is fixed at
    exactly one positional parameter, the :class:`App` instance.
    Startup work goes before ``yield``; shutdown work goes after
    ``yield`` (typically in a ``finally`` block). Resolve startup
    dependencies inside the body via
    ``await app.container().aresolve(T)``.

    Multiple lifespans (e.g. App + per-Router contributions) compose
    via :func:`a2kit.lifespan.compose`. Routers contribute via
    ``Router.lifespan``; ``App.add_router`` composes them into the
    final lifespan returned by :meth:`lifespan_cm`.
    """

    def __init__(
        self,
        name: str,
        *,
        health_tool: bool = False,
        debug: bool = False,
        lifespan: Callable[[Any], Any] | None = None,
    ) -> None:
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
        # Lifespan plumbing. Reject sync ``def`` at construction.
        if lifespan is not None and not _is_async_callable(lifespan):
            msg = (
                f"App({name!r}, lifespan=...): lifespan callable "
                f"{lifespan!r} MUST be defined with 'async def' (and "
                "decorated with @contextlib.asynccontextmanager). Sync "
                "'def' lifespans are not supported; move sync setup work "
                "inside the async body as plain statements."
            )
            raise TypeError(msg)
        self._lifespan: Callable[[Any], Any] | None = lifespan
        self._lifecycle_started: bool = False
        # Router-declared lifespan context managers, composed into the
        # final lifespan returned by ``lifespan_cm`` via
        # ``a2kit.lifespan.compose``. Order matches ``add_router`` calls.
        self._router_lifespans: list[Router] = []
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
        # Router-declared lifespan composes into the App's final
        # ``lifespan_cm`` via ``a2kit.lifespan.compose``. Stored in
        # ``add_router`` order; reverse-unwound on shutdown.
        cls = type(router)
        if "lifespan" in cls.__dict__:
            self._router_lifespans.append(router)
        return self

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
        singleton raises a clear error; warm-up via
        :meth:`warm_async_singletons` called from the App's lifespan
        body (or any first call from inside the event loop) primes the
        cache.

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

    async def warm_async_singletons(self) -> None:
        """Resolve every registered async-factory singleton through the container.

        Iterates the App's singleton registry, awaits each entry whose
        factory is async (sync entries are left alone), and populates the
        container cache. Idempotent: subsequent calls observe cached
        instances and do not re-await the factory. Concurrent callers
        coalesce on the per-type lock already provided by the container,
        so the factory runs at most once across the App.

        The canonical call site is the App's lifespan body before
        ``yield``::

            @asynccontextmanager
            async def lifespan(app):
                await app.warm_async_singletons()
                yield
        """
        container = self._container
        # Snapshot keys so concurrent registration does not perturb the
        # iteration; the container's per-type lock handles the rest.
        for type_ in list(container.singletons()):
            if container.has_async_singleton(type_):
                await container.aresolve(type_)

    def lifespan_cm(self) -> Any:
        """Return the App's composed lifespan as an async context manager.

        Composes (in order) the user-supplied ``lifespan=`` callable
        followed by every Router's ``lifespan`` method via
        :func:`a2kit.lifespan.compose`. If the App has no user lifespan
        and no Router contributes one, returns a
        :class:`contextlib.nullcontext` (no-op enter, no-op exit). The
        callable returned is already bound to ``self``; enter via
        ``async with app.lifespan_cm():``.

        Used by the CLI runner, the test client, and the FastMCP
        adapter to obtain a single async-with for the whole App
        lifecycle.
        """
        from a2kit.lifespan import compose as _compose

        legs: list[Callable[[Any], Any]] = []
        if self._lifespan is not None:
            legs.append(self._lifespan)
        legs.extend(_router_lifespan_factory(r) for r in self._router_lifespans)
        if not legs:
            return nullcontext()
        composed = _compose(*legs)
        return composed(self)

    def has_lifespan(self) -> bool:
        """True iff this App contributes startup or shutdown work.

        Used by the CLI runner and FastMCP adapter to decide whether to
        wire a lifespan context manager at all.
        """
        return self._lifespan is not None or bool(self._router_lifespans)

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


def _is_async_callable(fn: Any) -> bool:
    """True iff ``fn`` is an async-def callable or ``@asynccontextmanager``-wrapped.

    ``@asynccontextmanager`` wraps an async generator; the resulting
    callable has ``__wrapped__`` pointing at the original async
    generator function, which :func:`inspect.iscoroutinefunction` and
    :func:`inspect.isasyncgenfunction` detect via the wrapper's own
    ``_recreate_cm``-style shape. We accept any of:

    - ``inspect.iscoroutinefunction(fn)`` — bare ``async def``
    - ``inspect.isasyncgenfunction(fn)`` — bare ``async def`` generator
    - ``inspect.iscoroutinefunction(fn.__wrapped__)`` or
      ``inspect.isasyncgenfunction(fn.__wrapped__)`` —
      ``@asynccontextmanager``-decorated, ``@functools.wraps``-preserving
    """
    if inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn):
        return True
    wrapped = getattr(fn, "__wrapped__", None)
    return wrapped is not None and (
        inspect.iscoroutinefunction(wrapped) or inspect.isasyncgenfunction(wrapped)
    )


def _router_lifespan_factory(router: Router) -> Callable[[Any], Any]:
    """Wrap a Router's ``lifespan`` method as a ``lifespan(app)`` callable.

    The Router-side surface is ``async def lifespan(self):`` (no ``app``
    parameter — Routers already hold their dependencies). The composed
    lifespan callable shape is ``async def lifespan(app):``; this
    adapter discards the ``app`` argument and calls ``router.lifespan()``.
    """

    def _adapter(_app: Any) -> Any:
        return router.lifespan()  # type: ignore[attr-defined]

    _adapter.__qualname__ = (
        f"{type(router).__name__}.lifespan"  # for log labels
    )
    _adapter.__name__ = f"{type(router).__name__}.lifespan"
    return _adapter
