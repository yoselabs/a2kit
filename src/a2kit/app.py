from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from a2kit._lifecycle_helpers import (
    resolve_singleton_args,
)
from a2kit.packages.di import Container, Scope
from a2kit.routers import Router, RouterRegistry, _collect_marked_tool_names
from a2kit.tool import ToolDescriptor, _build_descriptors

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import click

    from a2kit.packages.di import Resolver


def _default_dispatch_hook(
    fn: Callable[..., Any],
    wire_kwargs: dict[str, Any],
    seed: Callable[[type, Any], None],
) -> Any:
    """Default dispatch hook — identity over ``wire_kwargs``.

    Module-level (not a bound method) so its object identity is stable:
    :meth:`AppRuntime.has_default_dispatch_hook` is an ``is`` check
    against this single object. A bound method would not compare equal
    across copies.

    Contract: hooks are wire-side resolution only. The default hook does
    nothing — wire kwargs pass through unchanged, no DI seeding. DI
    resolution (provider chain, ``Lazy[T]``, per-call scope) runs inside
    ``Container.call_scope`` AFTER the hook, on the hook's output.
    The ``seed`` callable lets hooks publish typed instances on the
    per-call DI child; the identity hook ignores it.
    """
    return wire_kwargs


class App:
    """The a2kit application — the compose-phase composition root.

    ``App`` is authored by **subclassing** (ADR 0028 Wave 2): a subclass
    sets ``name`` / ``routers`` / ``providers`` / ``config`` class attrs
    and declares app-level verbs + enrichers as methods. The remaining
    composition verbs (:meth:`add_cli`, :meth:`add_mcp_middleware`,
    :meth:`provide`, :meth:`auth`, :meth:`health_check`) are called on the
    instance, then it is handed to a *finisher* — :func:`a2kit.run` (or
    ``Kay().serve()``), :func:`a2kit.packages.mcp.build_mcp_server`, or
    :func:`a2kit.testing.client`. Tests use
    :func:`a2kit.testing.app_of`. ``App`` is abstract: it is authored by
    subclassing and composes routers via the ``routers`` ClassVar.

    ``App`` is a pure, reusable builder. It carries no sealed mode and no
    lifecycle: a finisher's internal ``build(app)`` step (see
    :mod:`a2kit.runtime`) snapshots the App's composition into an
    ``AppRuntime`` — the sealed runtime that owns the DI container and
    the async-CM lifecycle. Composition verbs stay callable at any time;
    a verb called after a finisher has built a runtime affects only
    subsequent builds and never mutates an already-running ``AppRuntime``.

    The compose container accumulates ``provide`` registrations and stays
    mutable for the App's whole lifetime — it is never sealed. Each
    ``build()`` snapshots it into a fresh runtime container, so one App
    may be handed to more than one finisher. See ADR 0019 (supersedes
    ADR 0017).

    Construction is pure: instantiating the subclass plus ``provide`` calls
    trigger no async work — useful for unit tests that introspect wiring
    without entering a runtime.

    Authored as a class (ADR 0028 Wave 2, app-as-peer-root): a subclass
    sets ``name`` / ``providers`` / ``routers`` (a tuple of Router
    *classes*) / ``config`` as class attributes, declares app-level verbs
    as ``@a2kit.read``/``.write``/``.list_`` methods (auto-collected, bare
    top-level names — no slug), and class-body ``@a2kit.enricher`` methods.
    Run by instantiating at the entry point: ``Kay().serve()``.
    """

    #: Authoring class attributes (subclass form). ``routers`` names Router
    #: *classes* (reference-composition); ``providers`` mirrors
    #: ``Router.providers``. ``name`` is a plain
    #: subclass attribute (``name = "kay"``) read in ``__init__`` — not a
    #: ClassVar, so the per-instance ``self.name`` assignment is clean.
    routers: ClassVar[tuple[type[Router], ...]] = ()
    providers: ClassVar[tuple[Any, ...]] = ()

    #: On-serve background services (ADR 0030). Each is a coroutine
    #: function ``async def (ctx: a2kit.ServeContext) -> None`` that
    #: ``serve`` runs as a concurrent task inside its one
    #: ``async with runtime:`` — never on a CLI verb. Typed structurally
    #: (``ctx`` is ``a2kit.ServeContext``) to avoid an upward import of the
    #: L5 ``serve`` unit from this L3 module.
    serve_services: ClassVar[tuple[Callable[[Any], Awaitable[None]], ...]] = ()

    #: Auto-collected app-level verb-method names (bare, no slug),
    #: populated by ``__init_subclass__`` via the ``_a2kit`` marker.
    _a2kit_app_tool_names: ClassVar[tuple[str, ...]] = ()
    #: Auto-collected class-body ``@a2kit.enricher`` method names.
    _a2kit_app_enricher_names: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        from a2kit._verbs import ENRICHER_MARKER

        cls._a2kit_app_tool_names = _collect_marked_tool_names(cls)
        cls._a2kit_app_enricher_names = tuple(name for name in vars(cls) if getattr(getattr(cls, name, None), ENRICHER_MARKER, False))

    def __init__(
        self,
        name: str | None = None,
        *,
        config: Any = None,
        user_config: Any = None,
        **_kw: Any,
    ) -> None:
        # ``App`` is abstract: it is authored by subclassing, never built
        # directly. (Without this guard a bare ``App(...)`` would compose a
        # routerless app and silently do nothing — §1 silent-misbehavior
        # carve-out.)
        if type(self) is App:
            msg = (
                "a2kit.App is abstract — author by subclassing "
                "(`class Kay(a2kit.App): name = 'kay'; routers = (Entity, ...)` "
                "then `Kay()`), or use `a2kit.testing.app_of(name, *routers)` in tests."
            )
            raise TypeError(msg)
        if name is None:
            name = getattr(type(self), "name", None)
        if _kw:
            self._raise_unexpected_kwargs(name or type(self).__name__, _kw)
        if name is None:
            msg = f"{type(self).__name__}() has no name: set a `name` class attribute on the App subclass."
            raise TypeError(msg)
        if config is None:
            # Per-surface config via a `config = A2kitConfig(...)` class attr
            # on the subclass (design resolution: the names mcp/api/cli stay
            # the live form-(b) accessors, so config rides the existing slot).
            config = getattr(type(self), "config", None)
        self.name = name
        # ADR 0022: a2kit-owned config. Lazy-construct A2kitConfig() so the
        # env / .env / defaults are picked up at App() time. Inverted source
        # order means env beats the kwarg (consumer beats code).
        from a2kit.config import A2kitConfig

        self.config: A2kitConfig = config if config is not None else A2kitConfig()
        # ADR 0022: developer-owned config slot. Opaque pass-through.
        # a2kit does not introspect, validate, or merge.
        self.user_config: Any = user_config
        self._routers = RouterRegistry()
        self._descriptors: list[ToolDescriptor] = []
        self._cli_extras: list[click.Command] = []
        self._mcp_middlewares: list[Any] = []
        # Eager container init — sync, ~80 LOC, always available. Stays
        # mutable for the App's whole lifetime; ``build()`` snapshots it.
        self._container: Container = Container()
        # `Principal` is a framework-owned type that the substrate adapter
        # seeds per call (SCOPED). Pre-register a placeholder provider so
        # `split_signature` classifies `principal: Principal` into the
        # container bucket (resolved by a2kit DI, hidden from the wire surface).
        # The placeholder raises if reached — the per-call seed must be in place.
        from a2kit.packages.context import Principal as _Principal
        from a2kit.packages.di import Scope as _Scope

        def _principal_placeholder() -> _Principal:
            msg = "Principal not seeded for this call (no substrate produced an identity)"
            raise RuntimeError(msg)

        self._container.provide(_Principal, _principal_placeholder, scope=_Scope.SCOPED)
        # ADR 0022 worked example: subsystems consume sub-configs by type
        # through DI (last-write-wins for test overrides, ADR 0006).
        from a2kit.config import A2kitConfig as _A2kitConfig
        from a2kit.config import CliConfig as _CliConfig
        from a2kit.config import HttpConfig as _HttpConfig
        from a2kit.config import LogConfig as _LogConfig
        from a2kit.config import McpConfig as _McpConfig

        self._container.provide(_A2kitConfig, lambda: self.config)
        self._container.provide(_LogConfig, lambda: self.config.log)
        self._container.provide(_McpConfig, lambda: self.config.mcp)
        self._container.provide(_HttpConfig, lambda: self.config.http)
        self._container.provide(_CliConfig, lambda: self.config.cli)
        # Default dispatch hook is identity over wire kwargs. Consumer
        # packages (e.g. connections) install a hook that performs
        # wire-side conversion only; DI runs after the hook inside
        # ``Container.dispatch`` on the hook's output.
        self._dispatch_hook: Callable[..., Any] = _default_dispatch_hook
        # Wire the `a2kit` + `a2kit.calls` loggers from config (handlers,
        # the call-scope filter, the opt-in call-log). Kill-switch lives in
        # `LogConfig.enabled` (env A2KIT_LOG__ENABLED=false).
        from a2kit._log_bootstrap import configure_logging
        from a2kit.packages.log.app_log import _AppLog  # noqa: AK205 -- private app namespace

        configure_logging(self.config.log)
        self.log = _AppLog()

        # Health probe — auto-installed on the first ``health_check`` call.
        from a2kit.packages.health import HealthRegistry

        self._health: HealthRegistry = HealthRegistry(enabled=False)

        # Lazy substrate decorator accumulators. ``App.api`` and
        # ``App.mcp`` properties construct them on first touch — `import
        # a2kit` and `<app> --help` paths never reach them, so neither
        # ``fastapi`` nor ``fastmcp`` is loaded by attribute access alone.
        self._api: Any = None
        self._mcp: Any = None
        self._cli: Any = None
        # Auth registry — populated by `App.auth(spec)` calls. Stays
        # ``None`` (no allocation, no `packages.auth` import) until an
        # author registers an auth spec; cold-start preserved for apps
        # that don't configure auth.
        self._auth_registry: Any = None
        # Typed-error enricher chain — populated via @app.enricher. Each
        # entry is (filter_type, fn) where filter_type is the first-param
        # annotation (wide = BaseException; narrow = specific type). Read
        # by EnricherStage after router-level enrichers.
        self._enrichers: list[tuple[type[BaseException], Callable[..., Any]]] = []

        # --- subclass authoring (ADR 0028 Wave 2, app-as-peer-root) ------- #
        # Apply class-attr composition: install `providers`, compose the
        # `routers` ClassVar (Router classes → instances), and collect
        # app-level verbs + enrichers declared as methods on the subclass.
        self._apply_class_authoring()

    def _apply_class_authoring(self) -> None:
        """Install the subclass's class-attr authoring (no-op for base ``App``).

        ``providers`` ClassVar installs the same way Router providers do;
        ``routers`` names Router *classes* (reference-composition);
        app-level ``@a2kit`` verbs register on a synthetic
        slug-less root router so their canonical names stay bare, and
        class-body ``@a2kit.enricher`` methods join the app enricher chain.
        """
        cls = type(self)
        for entry in cls.providers:
            if isinstance(entry, tuple):
                ptype, pfactory = entry
                self.provide(ptype, pfactory)
            else:
                self.provide(entry)
        for router_cls in cls.routers:
            self._register_router(router_cls() if isinstance(router_cls, type) else router_cls)
        if cls._a2kit_app_tool_names:
            self._register_router(_AppRootRouter(self))
        for name in cls._a2kit_app_enricher_names:
            self.enricher(getattr(self, name))

    def __getattr__(self, name: str) -> Any:
        msg = f"'App' object has no attribute {name!r}"
        raise AttributeError(msg)

    @staticmethod
    def _raise_unexpected_kwargs(name: str, kw: dict[str, Any]) -> None:
        """Raise the standard unexpected-kwargs ``TypeError``.

        Core hygiene (`AGENTS.md` §3): any kwarg outside the declared set
        is rejected loud, naming the offending keys + the CHANGELOG. Removed
        kwargs (e.g. ``lifespan`` / ``debug`` / ``health_tool``) fall through
        to this generic path — no per-kwarg hint, the CHANGELOG is the recipe.
        """
        msg = f"App({name!r}) received unexpected keyword arguments: {sorted(kw)}. See CHANGELOG.md for removals across versions."
        raise TypeError(msg)

    def _install_health_tool(self) -> None:
        """Synthesize a built-in router carrying ``_meta.health``.

        Idempotent — if the ``_meta`` router is already installed, this is
        a no-op. The compose-phase ``_meta`` router's tool body closes
        over this App. A finisher's ``build()`` step re-binds the ``_meta``
        router to the resulting ``AppRuntime`` so the health probe
        resolves checks through the runtime's container.
        """
        if any(r.slug == "_meta" for r in self._routers.all()):
            return
        self._register_router(_make_meta_router(self))

    def health_check(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register ``fn`` as a readiness probe for ``_meta.health``.

        ``fn`` may be sync or async, take any DI-resolvable kwargs (e.g.
        ``state: AppState``), and SHOULD return a :class:`HealthResult`.
        Returns the function unchanged for ``@app.health_check`` use.

        The first ``health_check`` call auto-installs the ``_meta.health``
        synthetic router.
        """
        if not self._health.enabled:
            self._health.enabled = True
        self._install_health_tool()
        return self._health.register(fn)

    # --- Composition verbs ---------------------------------------------- #

    def enricher(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register an app-level exception → AppError|None translator.

        Same shape as ``Router.enricher`` — first-param annotation chooses
        wide (Exception/BaseException) vs narrow (specific type) dispatch.
        App-level enrichers run AFTER router-level enrichers in the chain.
        """
        from a2kit.routers import _resolve_enricher_filter

        filter_type = _resolve_enricher_filter(fn)
        self._enrichers.append((filter_type, fn))
        return fn

    def _register_router(self, router: Router) -> None:
        """Register one Router instance: dup-slug guard, descriptors, providers.

        The single registration seam — used by the ``routers`` ClassVar
        composition, the synthetic ``_AppRootRouter`` for app-level verbs,
        and the internal ``_meta`` health router.
        """
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

    def serve(self, argv: list[str] | None = None) -> Any:
        """Entry-point finisher: build this App's runtime and run its CLI.

        ``Kay().serve()`` is the authored run path (ADR 0028 Wave 2). Thin
        delegate to :func:`a2kit.run` so the instantiate-then-run shape is a
        one-liner at ``main()``.
        """
        from a2kit import run  # noqa: AK202 -- serve() is the deliberate App→facade finisher delegate

        return run(self, argv)

    def add_cli(self, command: click.Command) -> App:
        self._cli_extras.append(command)
        return self

    def add_mcp_middleware(self, middleware: Any) -> App:
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
    ) -> App:
        """Register a typed provider — the unified DI registration API.

        Three call shapes:

        - ``app.provide(SomeClass)`` — the class itself is the factory;
          registered under the class.
        - ``app.provide(factory)`` — type inferred from the factory's
          return-type annotation. Sync ``def``, ``async def``, and
          annotated lambdas accepted.
        - ``app.provide(BaseClass, factory)`` — explicit base-type
          override when the factory returns a subtype.

        ``per_call=True`` opts a registration into the per-call scope:
        a fresh instance is built per dispatch, cached within that one
        call only, and cleaned up at call exit. Default ``per_call=False``
        is app-scope (one instance per runtime, lazily entered on first
        use, cleaned up on runtime exit).

        Last-write-wins: a second ``provide`` for the same type silently
        replaces the prior factory. This is the test-override mechanism —
        construct a fresh ``App``, provide the fake last (see ADR 0006,
        ADR 0019).

        Cleanup auto-detection: only ``__aenter__``/``__aexit__`` is
        honored. ``aclose`` / ``close`` are NOT auto-detected — wrap them
        in a class with ``__aenter__``/``__aexit__`` or use
        ``@asynccontextmanager``.
        """
        if _kw:
            msg = f"App.provide() received unexpected keyword arguments: {sorted(_kw)}. Supported kwargs are `per_call`."
            raise TypeError(msg)
        type_, factory = resolve_singleton_args(arg1, arg2)
        scope = Scope.SCOPED if per_call else Scope.SINGLETON
        self._container.provide(type_, factory, scope=scope)
        return self

    def has_provider(self, type_: type) -> bool:
        return self._container.has_provider(type_)

    def provider_map(self) -> dict[type, Any]:
        """Snapshot of registered providers (parent-chain-aware).

        Renamed from ``providers()`` since ``providers`` is now the authoring
        ClassVar (a tuple of provider entries, ADR 0028 Wave 2).
        """
        return self._container.providers_view()

    # --- DI: read-only queries ------------------------------------------ #

    def container(self) -> Container:
        """Return the App's compose-phase container. Never None (eager-init).

        This container stays mutable for the App's lifetime. A finisher's
        ``build()`` step snapshots it into a separate runtime container;
        it never seals or mutates this one.
        """
        return self._container

    @property
    def _resolver(self) -> Resolver:
        """The App's compose-phase container, typed as :class:`Resolver`.

        Compose-phase introspection only. Per-dispatch resolution runs on
        the ``AppRuntime``'s container, not this one.
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
        """True when no consumer package installed a custom dispatch hook."""
        return self._dispatch_hook is _default_dispatch_hook

    # --- substrate-native decorator surfaces ---------------------------- #

    @property
    def api(self) -> Any:
        """The ``@app.api.<method>(...)`` decorator family (FastAPI-only).

        Lazy: first touch loads the FastAPI-side ``ApiSurface`` class
        via ``importlib`` (the ``A2K-LAYER`` rule forbids ``runtime``
        from a static ``from a2kit.packages.http ...`` import; the
        dynamic load keeps the constructor a plain-dataclass call that
        does NOT pull ``fastapi``). Subsequent accesses are idempotent.
        """
        if self._api is None:
            import importlib

            ApiSurface = importlib.import_module("a2kit.packages.http.api").ApiSurface  # noqa: N806
            self._api = ApiSurface()
        return self._api

    @property
    def mcp(self) -> Any:
        """The ``@app.mcp.tool/.prompt/.resource(...)`` decorator family.

        Lazy: same shape as :meth:`api`. Loads ``McpSurface`` via
        ``importlib`` to stay within the L3 → L5 layer discipline; the
        dataclass constructor does NOT pull ``fastmcp``.
        """
        if self._mcp is None:
            import importlib

            McpSurface = importlib.import_module("a2kit.packages.mcp.surface").McpSurface  # noqa: N806
            self._mcp = McpSurface()
        return self._mcp

    @property
    def cli(self) -> Any:
        """The CLI surface, peer of :meth:`api` / :meth:`mcp`.

        Lazy: same shape as :meth:`api`. Loads ``CliSurface`` via
        ``importlib`` so reaching this property is the only path that can
        pull ``typer`` (the constructor itself does NOT — ``typer`` loads
        only when ``app.cli.bind(...)`` runs). Idempotent thereafter.
        """
        if self._cli is None:
            import importlib

            CliSurface = importlib.import_module("a2kit.packages.cli.surface").CliSurface  # noqa: N806
            self._cli = CliSurface()
        return self._cli

    def auth(self, spec: Any) -> App:
        """Register an :class:`AuthSpec` for this App.

        Multiple calls accumulate in registration order. Order matters
        on HTTP (multiple auth middlewares run in registration order;
        first to authenticate wins); on MCP only the first OAuth-
        targeting spec is honoured (FastMCP takes a single ``auth=``).

        Lazy: the first call constructs the :class:`AppAuthRegistry`
        on demand so apps that never configure auth never load
        ``a2kit.packages.auth``.
        """
        if self._auth_registry is None:
            import importlib

            AppAuthRegistry = importlib.import_module("a2kit.packages.auth.registry").AppAuthRegistry  # noqa: N806
            self._auth_registry = AppAuthRegistry()
        self._auth_registry.add(spec)
        return self

    @property
    def auth_registry(self) -> Any:
        """The :class:`AppAuthRegistry` for this App, or ``None`` if no auth was registered.

        Substrate builders (``build_http_app`` / ``build_mcp_server``)
        consult this through ``AppRuntime.auth_registry``; the ``None``
        case preserves the no-auth cold-start path.
        """
        return self._auth_registry

    # --- Router / tool aggregation -------------------------------------- #

    def router_instances(self) -> list[Router]:
        """The registered Router instances (renamed from ``routers()``).

        The ``routers`` name is now the authoring ClassVar (a tuple of
        Router *classes*); this accessor returns the composed instances.
        """
        return self._routers.all()

    def tools(self) -> list[ToolDescriptor]:
        """Typed descriptors materialized at router-registration time. One per tool."""
        return list(self._descriptors)


class _AppRootRouter(Router):
    """Synthetic slug-less root router carrying app-level verbs.

    App-level verbs render BARE (no slug prefix): the app name is identity,
    not a prefix (ADR 0028 Wave 2). This holds the App subclass's ``@a2kit``
    verb methods bound to the app instance and deliberately does NOT stamp
    ``router_slug`` — so ``resolve_canonical_name`` yields the bare leaf.
    ``slug = None`` keeps it out of slug-grouped rendering (CLI panels) and
    the dotted ``_qualified`` form. ``Router.__init__`` (which requires a
    str slug and stamps ``router_slug``) is intentionally bypassed.
    """

    slug = None  # app root is slug-less → bare canonical names

    def __init__(self, app: App) -> None:
        from a2kit.metadata import _get_meta

        bound: list[Callable[..., Any]] = []
        for name in type(app)._a2kit_app_tool_names:
            method = getattr(app, name)
            meta = _get_meta(method)
            if meta is None:  # pragma: no cover -- collection keeps only marked methods
                continue
            # Do NOT stamp router_slug → bare canonical name. Surface
            # placement is per-verb ``surfaces=`` (default LISTED everywhere).
            bound.append(method)
        self._tools = bound
        self._enrichers = []


def _make_meta_router(owner: Any) -> Router:
    """Build the synthetic ``_meta`` router carrying ``_meta.health``.

    The tool body closes over ``owner`` — an :class:`App` at compose
    time, an ``AppRuntime`` at finisher-build time — and reads
    ``owner._health`` / ``owner._resolver`` live, so the probe observes
    the right registry and DI container for whichever phase installed it.
    """
    from a2kit._verbs import _read_internal
    from a2kit.packages.health import HEALTH_TOOL_NAME, app_version, run_checks
    from a2kit.routers import Router as _Router

    class _MetaRouter(_Router):
        slug = "_meta"

        @_read_internal(HEALTH_TOOL_NAME, title="Health probe")
        async def aggregated_health(self) -> dict[str, Any]:
            """Aggregated health status. Hidden from agent-facing list_tools."""
            return await run_checks(owner._health, owner._resolver, version=app_version(owner))

    return _MetaRouter()
