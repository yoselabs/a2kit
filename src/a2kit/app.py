from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from a2kit._lifecycle_helpers import (
    register_instance_cleanup,
    resolve_singleton_args,
)
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


#: Singleton-not-yet-resolved sentinel. Importable as ``from a2kit.app import UNRESOLVED``.
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

    ``a2kit.App`` is its own async context manager. ``async with app:``
    enters all registered singletons eagerly (in registration order,
    topological-DI ordering deferred), auto-detecting their cleanup
    protocol (``__aexit__`` / ``aclose`` / ``close``). Routers carrying
    ``__aenter__`` enter lazily on first dispatch of any of their tools
    and unwind on App exit in LIFO order.

    Construction is pure: ``a2kit.App(...)`` plus ``add_router`` /
    ``singleton`` / ``provide`` calls trigger no async work — useful
    for unit tests that introspect wiring without entering the App.
    """

    def __init__(
        self,
        name: str,
        *,
        debug: bool = False,
        **_kw: Any,
    ) -> None:
        if _kw:
            self._raise_unexpected_kwargs(name, _kw)
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
        # Typed event registry. Lazy import keeps the cold-start path off
        # `a2kit.packages.ldd` for apps that never touch typed events.
        from a2kit.packages.ldd import _AppLdd

        self.ldd = _AppLdd()

        # Health probe — auto-installed on the first ``@app.health_check``
        # call (v0.35: explicit constructor flag removed).
        from a2kit.packages.health import HealthRegistry

        self._health: HealthRegistry = HealthRegistry(enabled=False)
        # Test-seam: TestClient sessions claim this slot via __aenter__ so
        # overlapping sessions on the same App fail loud.
        self._test_override_owner: Any = None
        # Singleton AsyncExitStack owned by the App's lifecycle. Populated
        # in ``__aenter__``, unwound in ``__aexit__``.
        self._singleton_stack: Any = None
        # Routers that successfully entered via ``__aenter__`` during this
        # App's lifecycle. LIFO unwound on App ``__aexit__``.
        self._entered_routers: dict[str, Router] = {}
        # Per-router asyncio.Lock for first-touch coalescing.
        self._router_locks: dict[str, Any] = {}

    @staticmethod
    def _raise_unexpected_kwargs(name: str, kw: dict[str, Any]) -> None:
        """Raise ``TypeError`` for any kwarg removed in v0.35.

        Each known-removed kwarg gets a migration-hint message. Other
        unknown kwargs raise the standard "unexpected kwargs" shape.
        """
        if "lifespan" in kw:
            msg = (
                f"App({name!r}, lifespan=...) was removed in v0.35. "
                "Express imperative bookends as a marker singleton "
                "(``class _Warmup: __aenter__/__aexit__``; "
                "``app.singleton(_Warmup)``) or move the work into "
                "``main()`` before ``async with app:``. See CHANGELOG."
            )
            raise TypeError(msg)
        if "health_tool" in kw:
            msg = (
                f"App({name!r}, health_tool=...) was removed in v0.35. "
                "Register a probe with @app.health_check to "
                "auto-install the _meta.health tool, or omit the flag "
                "entirely if you don't need health checks."
            )
            raise TypeError(msg)
        msg = f"App({name!r}) received unexpected keyword arguments: {sorted(kw)}. See CHANGELOG.md for v0.35 removals."
        raise TypeError(msg)

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
        """Synthesize a built-in router carrying ``_meta.health``.

        Idempotent — if the ``_meta`` router is already installed, this is a
        no-op so ``App(health_tool=True)`` + ``@app.health_check`` does not
        double-install.
        """
        if any(r.slug == "_meta" for r in self._routers.all()):
            return
        from a2kit.packages.health import HEALTH_TOOL_NAME, run_checks
        from a2kit.routers import Router as _Router
        from a2kit.tool import _read_internal

        app_ref = self

        class _MetaRouter(_Router):
            slug = "_meta"

            @_read_internal(HEALTH_TOOL_NAME, title="Health probe")
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

        v0.33: the first ``@app.health_check`` call auto-installs the
        ``_meta.health`` synthetic router. ``App(health_tool=True)`` remains
        accepted (no-op when checks are also registered) for explicit-eager
        registration and apps that want the tool present with zero checks.
        """
        if not self._health.enabled:
            self._health.enabled = True
        self._install_health_tool()
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
        # ``Router.lifespan`` classmethod is removed in v0.35
        # (``consolidate-lifecycle-on-async-cm-protocol``). Subclasses
        # must implement ``__aenter__``/``__aexit__`` on the instance
        # instead. Raise loud with the migration hint per CLAUDE.md
        # "no backward compat shims".
        cls = type(router)
        if "lifespan" in cls.__dict__:
            msg = (
                f"Router subclass {cls.__name__!r}: `lifespan` classmethod "
                "was removed in v0.35. Implement `__aenter__` and "
                "`__aexit__` on the Router instance instead (the framework "
                "detects the async-CM protocol at add_router time)."
            )
            raise TypeError(msg)
        _validate_router_tools(router)
        self._routers.add(router)
        self._descriptors.extend(_build_descriptors(router))
        # Install Router-declared providers.
        for entry in getattr(router, "providers", ()):
            if isinstance(entry, tuple):
                ptype, pfactory = entry
                self.provide(ptype, pfactory)
            else:
                self.provide(entry)
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

    def singleton(self, arg1: Any, arg2: Any = None, **_kw: Any) -> App:
        """Register a factory whose result is cached for the lifetime of this App.

        Three call shapes:

        - ``app.singleton(SomeClass)`` — the class itself is the factory;
          the registered type is the class.
        - ``app.singleton(factory)`` — type is inferred from the
          factory's return-type annotation. Sync ``def``, ``async def``,
          and annotated lambdas are all accepted.
        - ``app.singleton(BaseClass, factory)`` — explicit base-type
          override for the case where the factory returns a subtype.

        Cleanup is auto-detected on the resolved instance during App
        ``__aenter__``: ``__aexit__`` (paired with ``__aenter__``),
        ``aclose``, ``close`` — first match wins. There is no
        ``teardown=`` kwarg; move cleanup onto the resource itself via
        the protocol. Async factories are awaited on first resolution.
        """
        if "teardown" in _kw:
            msg = (
                "app.singleton(..., teardown=...) was removed in v0.35. "
                "Move cleanup onto the resource itself via __aexit__, "
                "aclose, or close — the framework auto-detects it."
            )
            raise TypeError(msg)
        if _kw:
            msg = f"app.singleton() received unexpected keyword arguments: {sorted(_kw)}"
            raise TypeError(msg)
        type_, factory = resolve_singleton_args(arg1, arg2)
        self._container.register_singleton(type_, factory)
        return self

    def has_singleton(self, type_: type) -> bool:
        return self._container.has_singleton(type_)

    def singletons(self) -> dict[type, Any]:
        """Snapshot of registered singletons; unresolved entries carry :data:`UNRESOLVED`."""
        return self._container.singletons()

    # --- Lazy router entry (v0.35 consolidate-lifecycle) ----------------- #

    async def _ensure_router_entered(self, router: Router) -> None:
        """Enter ``router`` via ``__aenter__`` exactly once during this App's lifecycle.

        Called from the per-transport dispatch wrappers before invoking
        the tool method. No-op for routers without ``__aenter__``.
        Concurrent first-touch coalesces on a per-router
        ``asyncio.Lock``. Failed ``__aenter__`` does NOT cache the router
        in ``_entered_routers``; the next dispatch retries.
        """
        if not hasattr(router, "__aenter__"):
            return
        slug = router.slug
        if slug in self._entered_routers:
            return
        import asyncio

        lock = self._router_locks.get(slug)
        if lock is None:
            lock = asyncio.Lock()
            self._router_locks[slug] = lock
        async with lock:
            if slug in self._entered_routers:
                return
            await router.__aenter__()  # type: ignore[func-returns-value]  # ty: ignore[call-non-callable]
            self._entered_routers[slug] = router

    async def _unwind_entered_routers(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """LIFO unwind of routers that entered via ``__aenter__`` during the
        App's lifecycle. Each ``__aexit__`` failure is logged at ERROR;
        unwinding continues so sibling routers still exit.
        """
        for slug in reversed(list(self._entered_routers)):
            router = self._entered_routers[slug]
            try:
                await router.__aexit__(exc_type, exc, tb)  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
            except Exception as inner:  # noqa: BLE001 -- error-isolation per spec
                _LIFECYCLE_LOG.error(
                    "router teardown failed: slug=%s class=%s message=%s",
                    slug,
                    type(inner).__name__,
                    inner,
                )
                _LIFECYCLE_LOG.debug("router teardown traceback for %s", slug, exc_info=True)
        self._entered_routers.clear()
        self._router_locks.clear()

    # --- async context manager protocol (v0.35 consolidate-lifecycle) ----- #

    async def __aenter__(self) -> App:
        """Enter the App's lifecycle.

        Singletons enter eagerly in registration order. Each resolved
        instance is probed for cleanup protocol (``__aexit__``,
        ``aclose``, ``close`` — first match wins) and the corresponding
        cleanup is registered on an ``AsyncExitStack`` owned by the
        App. Routers enter lazily on first dispatch.

        Exit order: routers unwind first in LIFO of enter order,
        followed by the AsyncExitStack (LIFO of singleton registration).
        Topological DI-graph ordering for singletons is a deferred
        refinement; registration order is the contract today.
        """
        from contextlib import AsyncExitStack

        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            for type_ in list(self._container.singletons()):
                if self._container.has_async_singleton(type_):
                    instance = await self._container.aresolve(type_)
                else:
                    instance = self._container.resolve(type_)
                await register_instance_cleanup(stack, instance)
        except BaseException:
            await stack.__aexit__(None, None, None)
            raise
        self._singleton_stack = stack
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool | None:
        stack = self._singleton_stack
        self._singleton_stack = None
        try:
            await self._unwind_entered_routers(exc_type, exc, tb)
        finally:
            if stack is not None:
                await stack.__aexit__(exc_type, exc, tb)
        return None

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

    def tools(self) -> list[ToolDescriptor]:
        """Typed descriptors materialized at ``add_router`` time. One per tool.

        v0.33: collapsed surface — previously this returned bound callables
        and the descriptor list lived on ``tool_descriptors()``. Both now
        funnel through this single accessor, which returns ``ToolDescriptor``
        objects. Consumers that need raw callables compute
        ``[d.fn for d in app.tools()]``.
        """
        return list(self._descriptors)

    def tool_descriptors(self) -> list[ToolDescriptor]:
        """Deprecated alias for :meth:`tools`. Removed in a future minor.

        v0.33 keeps this as a one-line shim so internal call sites and
        downstream consumers have a quiet migration window. The README and
        public docs reference ``tools()`` exclusively.
        """
        return list(self._descriptors)


def _validate_router_tools(router: Router) -> None:
    """Verify every ``@a2kit.*``-decorated method on the Router class
    is listed in its ``tools`` tuple.

    Fires at ``App.add_router`` time per ``app-time-tools-tuple-validation``.
    Only inspects the Router class's own attributes (``cls.__dict__``) so
    inherited decorated methods from a base class are not surfaced as
    drift unless the subclass intends them to be registered.
    """
    from a2kit.exceptions import A2KitDecoratedMethodNotInTools
    from a2kit.metadata import get_meta

    cls = type(router)
    tools_names = {getattr(fn, "__name__", None) for fn in (getattr(cls, "tools", ()) or ())}
    decorated_methods = {name for name, attr in cls.__dict__.items() if callable(attr) and get_meta(attr) is not None}
    missing = sorted(decorated_methods - tools_names)
    if missing:
        raise A2KitDecoratedMethodNotInTools(cls.__name__, missing)


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
