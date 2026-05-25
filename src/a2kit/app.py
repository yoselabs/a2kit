from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

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


def _default_dispatch_hook(
    fn: Callable[..., Any],
    wire_kwargs: dict[str, Any],
) -> Any:
    """Default dispatch hook — identity over ``wire_kwargs``.

    Module-level (not a bound method) so its object identity is stable:
    :meth:`AppRuntime.has_default_dispatch_hook` is an ``is`` check
    against this single object. A bound method would not compare equal
    across copies.

    v0.36+ contract: hooks are wire-side resolution only. The default
    hook does nothing — wire kwargs pass through unchanged. DI resolution
    (provider chain, ``Lazy[T]``, per-call scope) runs inside
    ``Container.dispatch`` AFTER the hook, on the hook's output.
    """
    return wire_kwargs


class App:
    """The a2kit application — the compose-phase builder.

    ``App`` is constructed directly (``a2kit.App("svc")``), wired with the
    composition verbs — :meth:`add_router`, :meth:`add_cli`,
    :meth:`add_mcp_middleware`, :meth:`provide`, :meth:`health_check` —
    and handed to a *finisher*: :func:`a2kit.run`,
    :func:`a2kit.packages.mcp.build_mcp_server`, or
    :func:`a2kit.testing.client`. Each composition verb returns the App
    for chaining.

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

    Construction is pure: ``App(...)`` plus ``add_router`` / ``provide``
    calls trigger no async work — useful for unit tests that introspect
    wiring without entering a runtime.
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
        # Default dispatch hook is identity over wire kwargs. Consumer
        # packages (e.g. connections) install a hook that performs
        # wire-side conversion only; DI runs after the hook inside
        # ``Container.dispatch`` on the hook's output.
        self._dispatch_hook: Callable[..., Any] = _default_dispatch_hook
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

        # Health probe — auto-installed on the first ``health_check`` call.
        from a2kit.packages.health import HealthRegistry

        self._health: HealthRegistry = HealthRegistry(enabled=False)

        # Lazy substrate decorator accumulators. ``App.api`` and
        # ``App.mcp`` properties construct them on first touch — `import
        # a2kit` and `<app> --help` paths never reach them, so neither
        # ``fastapi`` nor ``fastmcp`` is loaded by attribute access alone.
        self._api: Any = None
        self._mcp: Any = None
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
                "``app.provide(_Warmup)``) or move the work into "
                "``main()`` before handing the App to a finisher. See CHANGELOG."
            )
            raise TypeError(msg)
        if "health_tool" in kw:
            msg = (
                f"App({name!r}, health_tool=...) was removed in v0.35. "
                "Register a probe with app.health_check to "
                "auto-install the _meta.health tool, or omit the flag "
                "entirely if you don't need health checks."
            )
            raise TypeError(msg)
        msg = f"App({name!r}) received unexpected keyword arguments: {sorted(kw)}. See CHANGELOG.md for v0.35 removals."
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
        self.add_router(_make_meta_router(self))

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
        if "teardown" in _kw:
            msg = (
                "app.provide(..., teardown=...) was removed in v0.36. Move "
                "cleanup onto the resource itself via __aexit__ — the framework "
                "auto-detects __aenter__/__aexit__ and unwinds via the per-scope "
                "cleanup stack."
            )
            raise TypeError(msg)
        if _kw:
            msg = f"App.provide() received unexpected keyword arguments: {sorted(_kw)}. Supported kwargs are `per_call`."
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

    # --- LDD kill-switch ------------------------------------------------ #

    def set_ldd(self, *, reports: bool | None = None, events: bool | None = None) -> App:
        if reports is not None:
            self._ldd_reports = reports
        if events is not None:
            self._ldd_events = events
        return self

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

        tools = (aggregated_health,)

    return _MetaRouter()


def _validate_router_tools(router: Router) -> None:
    """Verify every ``@a2kit.*``-decorated method on the Router class
    is listed in its ``tools`` tuple.

    Fires at ``App.add_router`` time per ``app-time-tools-tuple-validation``.
    Only inspects the Router class's own attributes (``cls.__dict__``) so
    inherited decorated methods from a base class are not surfaced as
    drift unless the subclass intends them to be registered.
    """
    from a2kit.exceptions import A2KitDecoratedMethodNotInTools
    from a2kit.metadata import _get_meta

    cls = type(router)
    tools_names = {getattr(fn, "__name__", None) for fn in (getattr(cls, "tools", ()) or ())}
    decorated_methods = {name for name, attr in cls.__dict__.items() if callable(attr) and _get_meta(attr) is not None}
    missing = sorted(decorated_methods - tools_names)
    if missing:
        raise A2KitDecoratedMethodNotInTools(cls.__name__, missing)


def _build_descriptors(router: Router, container: Container | None = None) -> list[ToolDescriptor]:
    """Materialize one ``ToolDescriptor`` per tool on ``router``.

    When ``container`` is supplied (typically at ``runtime.build`` time),
    populates ``wire_param_names`` and ``lazy_param_names``. Without a
    container (``add_router`` time), those sentinel fields stay ``None``
    and substrate adapters that need them MUST read via
    ``AppRuntime.descriptor_for(name)``.
    """
    from types import MappingProxyType

    from a2kit.metadata import _get_meta
    from a2kit.packages.di import lazy_inner_type
    from a2kit.packages.formatter import build_encoding_plan, infer_format_hint
    from a2kit.signature import resolve_hints, wire_input_params

    out: list[ToolDescriptor] = []
    for fn in router.bound_tools():
        hints = resolve_hints(fn)
        return_type = hints.get("return")
        format_hint = infer_format_hint(return_type)
        encoding_plan = build_encoding_plan(return_type)
        meta = _get_meta(fn)
        name = meta.tool_name if meta is not None else getattr(fn, "__name__", "<callable>")
        # Carry the multi-surface fields onto the descriptor so substrate
        # adapters and selectors can filter without re-reading A2KitMeta.
        # `verb` defaults to "read" — the safest default for unstamped
        # tools (e.g. the _meta.health helper that uses _read_internal).
        # A2KitMeta.verb is `Literal["read", "write", "list", "tool"]`;
        # ToolDescriptor.verb is narrowed to read/list/write because
        # `tool` is the @app.mcp.tool family that does NOT produce a
        # ToolDescriptor (mcp_surface holds them separately).
        meta_verb = meta.verb if meta is not None else "read"
        verb: Literal["read", "list", "write"] = meta_verb if meta_verb in ("read", "list", "write") else "read"  # type: ignore[assignment]
        expose: tuple[str, ...] = tuple(meta.extras.expose) if meta is not None else ("mcp", "api")
        authorize = meta.extras.authorize if meta is not None else None
        ctx_param_name = meta.context_param_name if meta is not None else None
        timeout = meta.extras.timeout_seconds if meta is not None else None
        annotations_view = MappingProxyType(dict(meta.annotations_as_dict())) if meta is not None else MappingProxyType({})
        if meta is not None:
            metadata_view = MappingProxyType(
                {
                    "verb": meta.verb,
                    "tags": frozenset(meta.tags),
                    "context_param_name": meta.context_param_name,
                    "tool_name": meta.tool_name,
                    "extras": MappingProxyType(meta.extras.model_dump()),
                }
            )
        else:
            metadata_view = MappingProxyType({})
        wire_param_names: frozenset[str] | None = None
        lazy_param_names: frozenset[str] | None = None
        if container is not None:
            wire_params, _scopes = wire_input_params(fn, container)
            wire_param_names = frozenset(wire_params.keys())
            lazy_param_names = frozenset(pname for pname, ann in hints.items() if pname != "return" and lazy_inner_type(ann) is not None)
        out.append(
            ToolDescriptor(
                name=name,
                router=router,
                fn=fn,
                return_type=return_type,
                format_hint=format_hint,
                encoding_plan=encoding_plan,
                verb=verb,
                expose=expose,
                authorize=authorize,
                ctx_param_name=ctx_param_name,
                timeout=timeout,
                annotations_view=annotations_view,
                metadata_view=metadata_view,
                wire_param_names=wire_param_names,
                lazy_param_names=lazy_param_names,
                _meta=meta,
            )
        )
    return out
