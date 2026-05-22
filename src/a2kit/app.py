from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from a2kit._lifecycle_helpers import (
    resolve_singleton_args,
)
from a2kit.packages.di import Container, Scope
from a2kit.routers import Router, RouterRegistry
from a2kit.tool import ToolDescriptor

if TYPE_CHECKING:
    from collections.abc import Callable

    import click

    from a2kit.packages.di import Resolver


_LIFECYCLE_LOG = logging.getLogger("a2kit.lifecycle")


def _default_dispatch_hook(
    fn: Callable[..., Any],
    wire_kwargs: dict[str, Any],
) -> Any:
    """Default dispatch hook — identity over ``wire_kwargs``.

    Module-level (not a bound method) so its object identity is stable
    across the :class:`AppBuilder` / :class:`App` split:
    :meth:`App.has_default_dispatch_hook` is an ``is`` check against this
    single object. A bound method would compare unequal once copied from
    builder to App.

    v0.36+ contract: hooks are wire-side resolution only. The default
    hook does nothing — wire kwargs pass through unchanged. DI resolution
    (provider chain, ``Lazy[T]``, per-call scope) runs inside
    ``Container.dispatch`` AFTER the hook, on the hook's output.
    """
    return wire_kwargs


class AppBuilder:
    """Mutable composition root. Terminal method: :meth:`build`.

    ``AppBuilder`` is the *write* phase of an a2kit application. It
    carries the composition verbs — :meth:`add_router`, :meth:`add_cli`,
    :meth:`add_mcp_middleware`, :meth:`provide`, :meth:`health_check` —
    and nothing else. Each verb returns the builder for chaining.

    :meth:`build` is the seal point: it constructs the sealed
    :class:`App`, validates the DI provider graph, and locks the builder.
    A builder produces exactly one ``App``; call it again and it raises.

    The builder / runtime split makes the two-phase lifecycle a fact in
    the type system — the sealed ``App`` has no ``provide`` to call after
    entry, so "is this still mutable?" is answered by the type, not by a
    runtime raise. See ADR 0016.

    Construction is pure: ``AppBuilder(...)`` plus ``add_router`` /
    ``provide`` calls trigger no async work — useful for unit tests that
    introspect wiring without entering the App.
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
        # Eager container init — sync, ~80 LOC, always available. Mutable
        # until ``build()`` seals it.
        self._container: Container = Container()
        # Default dispatch hook is identity over wire kwargs. Consumer
        # packages (e.g. connections) install a hook on the builder that
        # performs wire-side conversion only; DI runs after the hook
        # inside ``Container.dispatch`` on the hook's output.
        self._dispatch_hook: Callable[..., Any] = _default_dispatch_hook
        # LDD kill-switch — env A2KIT_LDD=off disables both channels at
        # startup; the built App's ``set_ldd(...)`` and CLI flags override
        # per-invocation.
        import os

        env_off = os.environ.get("A2KIT_LDD", "").lower() == "off"
        self._ldd_reports = not env_off
        self._ldd_events = not env_off
        # Typed event registry. Lazy import keeps the cold-start path off
        # `a2kit.packages.ldd` for apps that never touch typed events.
        from a2kit.packages.ldd import _AppLdd

        self.ldd = _AppLdd()

        # Health probe — auto-installed on the first ``health_check`` call.
        from a2kit.packages.health import HealthRegistry

        self._health: HealthRegistry = HealthRegistry(enabled=False)
        # Flipped by ``build()``. A spent builder rejects further verbs.
        self._built: bool = False

    @staticmethod
    def _raise_unexpected_kwargs(name: str, kw: dict[str, Any]) -> None:
        """Raise ``TypeError`` for any kwarg removed in v0.35.

        Each known-removed kwarg gets a migration-hint message. Other
        unknown kwargs raise the standard "unexpected kwargs" shape.
        """
        if "lifespan" in kw:
            msg = (
                f"AppBuilder({name!r}, lifespan=...) was removed in v0.35. "
                "Express imperative bookends as a marker singleton "
                "(``class _Warmup: __aenter__/__aexit__``; "
                "``builder.provide(_Warmup)``) or move the work into "
                "``main()`` before ``async with app:``. See CHANGELOG."
            )
            raise TypeError(msg)
        if "health_tool" in kw:
            msg = (
                f"AppBuilder({name!r}, health_tool=...) was removed in v0.35. "
                "Register a probe with builder.health_check to "
                "auto-install the _meta.health tool, or omit the flag "
                "entirely if you don't need health checks."
            )
            raise TypeError(msg)
        msg = f"AppBuilder({name!r}) received unexpected keyword arguments: {sorted(kw)}. See CHANGELOG.md for v0.35 removals."
        raise TypeError(msg)

    def _ensure_unbuilt(self) -> None:
        """Reject composition verbs after :meth:`build` has been called.

        A builder produces one App. After ``build()`` the underlying
        container is sealed and the routers/descriptors are owned by the
        runtime ``App`` — further mutation would silently change a
        already-built App. Construct a fresh ``AppBuilder`` instead.
        """
        if self._built:
            msg = (
                "AppBuilder is spent — build() was already called. A builder "
                "produces exactly one App. Construct a new a2kit.AppBuilder "
                "to compose another."
            )
            raise TypeError(msg)

    def _install_health_tool(self) -> None:
        """Synthesize a built-in router carrying ``_meta.health``.

        Idempotent — if the ``_meta`` router is already installed, this is
        a no-op. The synthetic router's tool body closes over this
        builder; the builder's ``_health`` registry and ``_container``
        are handed by reference to the built :class:`App`, so the closure
        reads live runtime state after ``build()``.
        """
        if any(r.slug == "_meta" for r in self._routers.all()):
            return
        from a2kit._verbs import _read_internal
        from a2kit.packages.health import HEALTH_TOOL_NAME, app_version, run_checks
        from a2kit.routers import Router as _Router

        builder_ref = self

        class _MetaRouter(_Router):
            slug = "_meta"

            @_read_internal(HEALTH_TOOL_NAME, title="Health probe")
            async def aggregated_health(self) -> dict[str, Any]:
                """Aggregated health status. Hidden from agent-facing list_tools."""
                registry = builder_ref._health
                resolver = builder_ref._container
                return await run_checks(registry, resolver, version=app_version(builder_ref))

            tools = (aggregated_health,)

        self.add_router(_MetaRouter())

    def health_check(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register ``fn`` as a readiness probe for ``_meta.health``.

        ``fn`` may be sync or async, take any DI-resolvable kwargs (e.g.
        ``state: AppState``), and SHOULD return a :class:`HealthResult`.
        Returns the function unchanged for ``@builder.health_check`` use.

        The first ``health_check`` call auto-installs the ``_meta.health``
        synthetic router; ``build()`` carries it into the runtime App.
        """
        self._ensure_unbuilt()
        if not self._health.enabled:
            self._health.enabled = True
        self._install_health_tool()
        return self._health.register(fn)

    # --- Composition verbs ---------------------------------------------- #

    def add_router(self, router: Router) -> AppBuilder:
        self._ensure_unbuilt()
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

    def add_cli(self, command: click.Command) -> AppBuilder:
        self._ensure_unbuilt()
        self._cli_extras.append(command)
        return self

    def add_mcp_middleware(self, middleware: Any) -> AppBuilder:
        self._ensure_unbuilt()
        self._mcp_middlewares.append(middleware)
        return self

    # --- DI: typed providers ------------------------------------------- #

    def provide(
        self,
        arg1: Any,
        arg2: Any = None,
        *,
        per_call: bool = False,
        **_kw: Any,
    ) -> AppBuilder:
        """Register a typed provider — the unified DI registration API.

        Three call shapes:

        - ``builder.provide(SomeClass)`` — the class itself is the
          factory; registered under the class.
        - ``builder.provide(factory)`` — type inferred from the factory's
          return-type annotation. Sync ``def``, ``async def``, and
          annotated lambdas accepted.
        - ``builder.provide(BaseClass, factory)`` — explicit base-type
          override when the factory returns a subtype.

        ``per_call=True`` opts a registration into the per-call scope:
        a fresh instance is built per dispatch, cached within that one
        call only, and cleaned up at call exit. Default ``per_call=False``
        is app-scope (one instance per App, lazily entered on first use,
        cleaned up on app exit).

        Last-write-wins: a second ``provide`` for the same type silently
        replaces the prior factory. This is the test-override mechanism —
        provide the fake last, then ``build()`` (see ADR 0006, ADR 0016).

        Cleanup auto-detection: only ``__aenter__``/``__aexit__`` is
        honored. ``aclose`` / ``close`` are NOT auto-detected — wrap them
        in a class with ``__aenter__``/``__aexit__`` or use
        ``@asynccontextmanager``.
        """
        self._ensure_unbuilt()
        if "teardown" in _kw:
            msg = (
                "builder.provide(..., teardown=...) was removed in v0.36. Move "
                "cleanup onto the resource itself via __aexit__ — the framework "
                "auto-detects __aenter__/__aexit__ and unwinds via the per-scope "
                "cleanup stack."
            )
            raise TypeError(msg)
        if _kw:
            msg = f"AppBuilder.provide() received unexpected keyword arguments: {sorted(_kw)}. Supported kwargs are `per_call`."
            raise TypeError(msg)
        type_, factory = resolve_singleton_args(arg1, arg2)
        scope = Scope.SCOPED if per_call else Scope.SINGLETON
        self._container.provide(type_, factory, scope=scope)
        return self

    def has_provider(self, type_: type) -> bool:
        return self._container.has_provider(type_)

    def providers(self) -> dict[type, Any]:
        """Snapshot of registered providers (parent-chain-aware)."""
        return self._container.providers_view()

    # --- terminal: seal into a runtime App ------------------------------ #

    def build(self) -> App:
        """Seal the composition and return the runtime :class:`App`.

        Constructs the immutable ``App`` over this builder's state,
        validates the DI provider graph (rejecting app-scope factories
        that depend on per-call types), and seals the container against
        further ``provide()``. The builder is spent afterwards.

        The ``_meta.health`` router, if any ``health_check`` was
        registered, was already installed on the first registration and
        is carried into the App by this call.
        """
        self._ensure_unbuilt()
        app = App._build_from(self)
        # Validate the provider graph and lock the container. After this
        # the builder cannot mutate the App it produced.
        self._container.seal()
        self._built = True
        return app


class App:
    """Sealed runtime — the mutation-free product of :meth:`AppBuilder.build`.

    ``App`` is the *run* phase of an a2kit application. It exposes only
    the runtime surface: :meth:`tools`, :meth:`routers`,
    :meth:`container`, the async-context-manager lifecycle, and the LDD
    kill-switch. It carries no composition verb — composition happened on
    the :class:`AppBuilder` before ``build()``.

    Construction is private. ``a2kit.App(...)`` raises ``TypeError``;
    compose with ``a2kit.AppBuilder(name)...build()`` instead. Calling a
    composition verb (``add_router``, ``provide``, ...) on a built App
    raises with the same migration hint. See ADR 0016.

    Lifecycle:

    ``App`` is its own async context manager. ``async with app:`` seals
    and validates the container, then enters lazily: app-scope resources
    enter on first ``Container.get(T)`` (first dispatch that needs them);
    routers carrying ``__aenter__`` enter on first dispatch of any of
    their tools and unwind on App exit in LIFO order.
    """

    #: Verbs that moved off the runtime App onto :class:`AppBuilder`.
    #: :meth:`__getattr__` intercepts these to raise a migration hint
    #: rather than a bare ``AttributeError``.
    _COMPOSITION_VERBS: frozenset[str] = frozenset(
        {
            "add_router",
            "add_cli",
            "add_mcp_middleware",
            "provide",
            "health_check",
            "singleton",
            "has_singleton",
        }
    )

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        msg = (
            "a2kit.App(...) cannot be constructed directly since v0.40. "
            "Compose with a2kit.AppBuilder(name), call the composition verbs "
            "(add_router / provide / ...), then `app = builder.build()`. "
            "See CHANGELOG: split-app-builder-runtime."
        )
        raise TypeError(msg)

    @classmethod
    def _build_from(cls, builder: AppBuilder) -> App:
        """Construct the sealed App over ``builder``'s state.

        The only real constructor — bypasses ``__init__`` (which always
        raises) via ``object.__new__``. Routers, descriptors, container,
        and the LDD registry are taken by reference: the builder and the
        App share them, which is how the ``_meta.health`` closure (bound
        to the builder) reads live runtime state.
        """
        self = object.__new__(cls)
        self.name = builder.name
        self.debug = builder.debug
        self._routers = builder._routers
        self._descriptors = builder._descriptors
        self._cli_extras = builder._cli_extras
        self._mcp_middlewares = builder._mcp_middlewares
        self._container = builder._container
        self._dispatch_hook = builder._dispatch_hook
        self._health = builder._health
        self.ldd = builder.ldd
        self._ldd_reports = builder._ldd_reports
        self._ldd_events = builder._ldd_events
        # Routers that successfully entered via ``__aenter__`` during this
        # App's lifecycle. LIFO unwound on App ``__aexit__``.
        self._entered_routers: dict[str, Router] = {}
        # Per-router asyncio.Lock for first-touch coalescing.
        self._router_locks: dict[str, Any] = {}
        return self

    def __getattr__(self, name: str) -> Any:
        """Intercept composition verbs with a migration hint.

        ``__getattr__`` fires only on a failed normal lookup, so a real
        runtime method never reaches here. A composition verb is not
        defined on ``App`` at all — accessing one lands here and raises
        a pointed ``TypeError``; anything else raises ``AttributeError``
        so ``getattr(app, x, default)`` and ``hasattr`` behave normally.
        """
        if name in App._COMPOSITION_VERBS:
            msg = (
                f"App.{name}(...) is a composition verb — it moved off the "
                f"sealed runtime App onto a2kit.AppBuilder in v0.40. Compose "
                f"before sealing: `builder = a2kit.AppBuilder(name); "
                f"builder.{name}(...); app = builder.build()`."
            )
            raise TypeError(msg)
        raise AttributeError(f"'App' object has no attribute {name!r}")

    # --- DI: read-only queries ------------------------------------------ #

    def has_provider(self, type_: type) -> bool:
        return self._container.has_provider(type_)

    def providers(self) -> dict[type, Any]:
        """Snapshot of registered providers (parent-chain-aware)."""
        return self._container.providers_view()

    def container(self) -> Container:
        """Return the App's container. Never None (eager-init)."""
        return self._container

    @property
    def _resolver(self) -> Resolver:
        """The App's resolver, typed as the :class:`Resolver` protocol.

        Framework / test code uses this to open child resolvers per
        dispatch via ``app._resolver.child()``. Production tool code
        receives resolved dependencies via parameter annotations; it
        SHOULD NOT call ``_resolver.get`` directly — that's a service
        locator antipattern.

        Typed as ``Resolver`` (not ``Container``) so consumer code is
        decoupled from the concrete implementation — only ``get``,
        ``provide``, ``child``, ``aclose`` are stable surface.
        """
        return self._container

    # --- transport extras ---------------------------------------------- #

    def cli_extras(self) -> list[click.Command]:
        return list(self._cli_extras)

    def mcp_middlewares(self) -> list[Any]:
        return list(self._mcp_middlewares)

    # --- dispatch hook -------------------------------------------------- #

    def dispatch_hook(self) -> Callable[..., Any]:
        return self._dispatch_hook

    def has_default_dispatch_hook(self) -> bool:
        """True when no consumer package installed a custom dispatch hook.

        Identity check against the module-level :func:`_default_dispatch_hook`.
        The dispatch pipeline's hook stage self-skips when this is true and
        the tool declares no injectables — opening a per-call child
        container would be pure overhead.
        """
        return self._dispatch_hook is _default_dispatch_hook

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
                await router.__aexit__(exc_type, exc, tb)  # type: ignore[attr-defined]
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

        Lazy first-use (v0.36 di-scoped-lifecycle):

        - The container is sealed (idempotent — ``build()`` already
          sealed it) and the provider graph is validated.
        - NO eager resource entry. App-scope resources enter on first
          ``Container.get(T)``, which means first dispatch that needs them.
        - Routers carrying ``__aenter__`` enter lazily on first dispatch
          of any of their tools.

        Exit order: routers unwind first (LIFO of enter order), then
        the container's cleanup stack unwinds (LIFO of resolution order).
        """
        await self._container.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool | None:
        try:
            await self._unwind_entered_routers(exc_type, exc, tb)
        finally:
            await self._container.__aexit__(exc_type, exc, tb)
        return None

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
        """Typed descriptors materialized at ``add_router`` time. One per tool."""
        return list(self._descriptors)

    def tool_descriptors(self) -> list[ToolDescriptor]:
        """Deprecated alias for :meth:`tools`. Removed in a future minor."""
        return list(self._descriptors)


def _validate_router_tools(router: Router) -> None:
    """Verify every ``@a2kit.*``-decorated method on the Router class
    is listed in its ``tools`` tuple.

    Fires at ``AppBuilder.add_router`` time per ``app-time-tools-tuple-validation``.
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
    from a2kit.packages.formatter import build_encoding_plan, infer_format_hint
    from a2kit.signature import resolve_hints

    out: list[ToolDescriptor] = []
    for fn in router.bound_tools():
        hints = resolve_hints(fn)
        return_type = hints.get("return")
        format_hint = infer_format_hint(return_type)
        encoding_plan = build_encoding_plan(return_type)
        meta = get_meta(fn)
        name = meta.tool_name if meta is not None else getattr(fn, "__name__", "<callable>")
        out.append(
            ToolDescriptor(
                name=name,
                router=router,
                fn=fn,
                return_type=return_type,
                format_hint=format_hint,
                encoding_plan=encoding_plan,
            )
        )
    return out
