"""``AppRuntime`` — the internal sealed runtime, and ``build()`` — the finisher seam.

``a2kit.App`` is the compose-phase builder; this module holds its
run-phase counterpart. A finisher (``a2kit.run``, ``build_mcp_server``,
``a2kit.testing.client``) calls :func:`build` to snapshot an ``App`` into
an ``AppRuntime``: a fresh validated DI container plus the App's
composed surface, frozen at build time. ``AppRuntime`` is the async
context manager; it is internal and never crosses the consumer
boundary. See ADR 0019 (supersedes ADR 0017).

Layer: ``runtime`` core sub-unit. Imports ``a2kit.app`` (same sub-unit,
one-way — ``app`` never imports ``runtime``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from a2kit.app import App, _default_dispatch_hook, _make_meta_router
from a2kit.packages.health import HealthRegistry
from a2kit.tool import _build_descriptors

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.packages.di import Container, Resolver
    from a2kit.routers import Router
    from a2kit.tool import ToolDescriptor

_LIFECYCLE_LOG = logging.getLogger("a2kit.lifecycle")


class AppRuntime:
    """The sealed a2kit runtime — a finisher's snapshot of a composed ``App``.

    Produced only by :func:`build`. Holds a fresh validated DI container
    and the App's composed surface (routers, tool descriptors, CLI
    extras, MCP middleware, dispatch hook, log config, health registry),
    all frozen at build time. ``AppRuntime`` is the async context
    manager: ``async with runtime:`` enters the lifecycle; app-scope
    resources enter lazily on first ``Container.get(T)`` and unwind in
    LIFO order on exit.

    Internal: never exported on ``a2kit.*``; consumers reach it only
    through the finishers, which build and enter it for them.
    """

    def __init__(
        self,
        *,
        name: str,
        config: Any,
        routers: list[Router],
        descriptors: list[ToolDescriptor],
        cli_extras: list[Any],
        mcp_middlewares: list[Any],
        container: Container,
        dispatch_hook: Callable[..., Any],
        health: HealthRegistry,
        api_surface: Any = None,
        mcp_surface: Any = None,
        auth_registry: Any = None,
        surfaces: Any = None,
    ) -> None:
        self.name = name
        self.config = config
        self._routers = routers
        self._descriptors = descriptors
        self._cli_extras = cli_extras
        self._mcp_middlewares = mcp_middlewares
        self._container = container
        self._dispatch_hook = dispatch_hook
        self._health = health
        # Substrate-native decorator surfaces collected by the source
        # ``App``. ``None`` when the author never touched ``App.api`` /
        # ``App.mcp`` — no FastAPI / FastMCP-only registrations exist.
        self.api_surface = api_surface
        self.mcp_surface = mcp_surface
        # Auth registrations from ``App.auth(spec)`` calls. ``None`` when
        # the source App has no auth configured — substrate builders use
        # this as the "skip middleware mount" signal (cold-start path).
        self.auth_registry = auth_registry
        # Per-runtime surface registry composed from ``build(surfaces=...)``.
        # Substrate adapters read transport-specific surface metadata
        # (`runtime.surfaces.get("api")` / `.get("mcp")`) through this
        # attribute instead of the module-level proxy.
        self.surfaces = surfaces
        # Routers that entered via ``__aenter__`` during this runtime's
        # lifecycle. LIFO unwound on ``__aexit__``.
        self._entered_routers: dict[str, Router] = {}
        # Per-router asyncio.Lock for first-touch coalescing.
        self._router_locks: dict[str, asyncio.Lock] = {}
        # Name → descriptor lookup; built once from the list in init order.
        # Substrate adapters consume via descriptor_for / descriptors.
        self._descriptor_by_name: dict[str, ToolDescriptor] = {d.name: d for d in descriptors}

    # --- composed surface accessors ------------------------------------ #

    def routers(self) -> list[Router]:
        return list(self._routers)

    def tools(self) -> list[ToolDescriptor]:
        return list(self._descriptors)

    def descriptors(self) -> tuple[ToolDescriptor, ...]:
        """Canonical descriptor read surface for substrate adapters.

        Returns a frozen tuple in stable registration order. Container-dependent
        fields (``wire_param_names``, ``lazy_param_names``) are populated here
        because ``build()`` re-materialised against the sealed runtime container.
        """
        return tuple(self._descriptors)

    def descriptor_for(self, name: str) -> ToolDescriptor:
        """O(1) descriptor lookup by tool name. Raises ``KeyError`` on miss."""
        return self._descriptor_by_name[name]

    def cli_extras(self) -> list[Any]:
        return list(self._cli_extras)

    def mcp_middlewares(self) -> list[Any]:
        return list(self._mcp_middlewares)

    def container(self) -> Container:
        """The runtime's validated DI container."""
        return self._container

    @property
    def _resolver(self) -> Resolver:
        """The runtime's resolver, typed as the :class:`Resolver` protocol."""
        return self._container

    # --- dispatch hook ------------------------------------------------- #

    def dispatch_hook(self) -> Callable[..., Any]:
        return self._dispatch_hook

    def has_default_dispatch_hook(self) -> bool:
        """True when no consumer package installed a custom dispatch hook."""
        return self._dispatch_hook is _default_dispatch_hook

    # --- lazy router entry --------------------------------------------- #

    async def _ensure_router_entered(self, router: Router) -> None:
        """Enter ``router`` via ``__aenter__`` exactly once this lifecycle.

        Called from the per-transport dispatch wrappers before invoking
        the tool method. No-op for routers without ``__aenter__``.
        Concurrent first-touch coalesces on a per-router ``asyncio.Lock``.
        Failed ``__aenter__`` does NOT cache the router; the next
        dispatch retries.
        """
        if not hasattr(router, "__aenter__"):
            return
        slug = router.slug
        if slug in self._entered_routers:
            return
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
        """LIFO unwind of routers that entered via ``__aenter__``.

        Each ``__aexit__`` failure is logged at ERROR; unwinding
        continues so sibling routers still exit.
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

    # --- async context manager protocol -------------------------------- #

    async def __aenter__(self) -> AppRuntime:
        """Enter the runtime lifecycle.

        The container is already validated and sealed by :func:`build`.
        Entry performs NO eager resource entry: app-scope resources
        enter on first ``Container.get(T)`` (first dispatch that needs
        them); routers carrying ``__aenter__`` enter lazily on first
        dispatch of any of their tools.

        Exit order: routers unwind first (LIFO of enter order), then the
        container's cleanup stack unwinds (LIFO of resolution order).
        """
        await self._container.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            await self._unwind_entered_routers(exc_type, exc, tb)
        finally:
            await self._container.__aexit__(exc_type, exc, tb)


def build(
    app: App | AppRuntime,
    *,
    select: list[str] | None = None,
    surfaces: Any = None,
) -> AppRuntime:
    """Snapshot a compose-phase ``App`` into a sealed ``AppRuntime``.

    The finisher seam. Idempotent on an ``AppRuntime``: passing one back
    returns it unchanged — the multiplex-serve parent builds the runtime
    once and hands the same instance to ``build_mcp_server`` and the REST
    surface.

    For an ``App``:

    1. Snapshots the App's provider registrations, scope metadata, and
       wire scopes into a **fresh** ``Container`` (via
       ``Container.snapshot``). The App's own compose-phase container is
       left untouched, so the App stays a reusable builder.
    2. Seals the fresh container — graph validation runs here; an
       app-scope-depends-on-per-call violation raises ``TypeError``
       before any ``AppRuntime`` is produced.
    3. Carries the App's composed surface (routers, descriptors, CLI
       extras, MCP middleware, dispatch hook, log config) into the
       runtime. When the App registered a health probe, the synthetic
       ``_meta`` router is re-bound to the runtime so the health tool
       resolves checks through the runtime's container.
    """
    if isinstance(app, AppRuntime):
        return app

    # The per-runtime surface registry is the facade's
    # `compose_default_surfaces()` by default — composing once at build
    # time gives every reader (`runtime.surfaces`, `expose=` validation)
    # the same canonical registry. Callers that need a custom surface set
    # pass `surfaces=` explicitly. The facade lives in `a2kit/__init__.py`,
    # which is layer-exempt, so late-import keeps the L3 → L4/L5 edge
    # off the static graph.
    if surfaces is None:
        from a2kit import compose_default_surfaces  # noqa: A2K-PKG-INIT-IMPORT

        surface_registry: Any = compose_default_surfaces()
    else:
        surface_registry = surfaces

    runtime_container = app.container().snapshot()
    runtime_container.seal()

    # Compile selectors once, up-front — any parse error must surface
    # before any App work happens so the CLI exit-2 path is clean.
    compiled_selectors = _compile_selectors(select) if select else ()

    # Carry every non-synthetic router; the ``_meta`` health router is
    # re-bound to the runtime below so its tool body resolves through the
    # runtime container, not the App's compose-phase container.
    routers: list[Router] = [r for r in app.router_instances() if r.slug != "_meta"]
    # Re-materialise descriptors against the sealed runtime container so
    # `wire_param_names` / `lazy_param_names` are populated. Pre-build
    # `app.tools()` still works for introspection (sentinel `None`).
    descriptors: list[ToolDescriptor] = []
    for r in routers:
        descriptors.extend(_build_descriptors(r, container=runtime_container))
    descriptors = _apply_descriptor_selectors(descriptors, compiled_selectors)
    api_surface = _filter_api_surface(app._api, compiled_selectors)  # noqa: SLF001
    mcp_surface = _filter_mcp_surface(app._mcp, compiled_selectors)  # noqa: SLF001

    # Validate every captured `expose=` against the composed surface set.
    # Empty `expose=()` was rejected at decoration; here we catch the
    # unknown-name case that decoration deliberately skipped (per
    # `bootstrap-surfaces-explicit` — surface validation requires the
    # composed registry, not import-time accumulation). Skipped when no
    # registry is in scope (programmatic callers bypassing the facade).
    if surface_registry is not None:
        _validate_descriptor_expose(descriptors, surface_registry)

    # Layer-2 backstop: assert global canonical-name uniqueness over the
    # snapshotted descriptors before any AppRuntime is produced. Shares the
    # one resolver with the standalone `validate_composition`, so build() and
    # the validator fail identically (ADR 0028 decision 6, validate-composition).
    _assert_unique_canonical_names(descriptors)

    health = HealthRegistry(enabled=app._health.enabled, checks=list(app._health.checks))  # noqa: SLF001 -- finisher snapshot

    runtime = AppRuntime(
        name=app.name,
        config=app.config,
        routers=routers,
        descriptors=descriptors,
        cli_extras=app.cli_extras(),
        mcp_middlewares=app.mcp_middlewares(),
        container=runtime_container,
        dispatch_hook=app.dispatch_hook(),
        health=health,
        # Carry substrate decorator surfaces only if they were touched —
        # `app._api` / `app._mcp` stay None until the first attribute
        # access, preserving the cold-start invariant.
        # When a selector filtered them, `_filter_api_surface` / `_filter_mcp_surface`
        # returns a copy with the narrowed registrations.
        api_surface=api_surface,
        mcp_surface=mcp_surface,
        # Auth registry — ``None`` when the source App never called
        # ``App.auth(...)`` so substrate builders skip middleware mount
        # entirely (cold-start invariant: no auth imports for no-auth apps).
        auth_registry=app.auth_registry,
        surfaces=surface_registry,
    )

    # Re-bind the synthetic `_meta` health router to the runtime so its
    # tool body resolves checks through the runtime container. The meta
    # router closes over `runtime` (now constructed); appending to the
    # `routers` / `descriptors` lists mutates the very lists the runtime
    # holds, since `AppRuntime` stores them by reference.
    if any(r.slug == "_meta" for r in app.router_instances()):
        meta_router = _make_meta_router(runtime)
        routers.append(meta_router)
        meta_descs = _build_descriptors(meta_router, container=runtime_container)
        descriptors.extend(meta_descs)
        # The lookup dict was sized off the initial descriptors list; refresh
        # it so the post-init meta descriptors are reachable via descriptor_for.
        runtime._descriptor_by_name.update({d.name: d for d in meta_descs})  # noqa: SLF001

    # Re-apply this app's logging config as it goes live (CLI/MCP build). The
    # `a2kit` logger is process-global, so the app being run must win over any
    # other App constructed earlier in the same process (test isolation).
    from a2kit._log_bootstrap import configure_logging

    configure_logging(runtime.config.log)
    return runtime


def _compile_selectors(exprs: list[str]) -> tuple[Any, ...]:
    """Compile every ``--select`` expression once at build time.

    Errors surface here (before any App snapshot work), so the CLI's
    ``SelectorError`` -> exit-2 handler sees a clean failure path. The
    selector package is imported lazily so ``import a2kit`` does not
    load it for consumers that never call ``build(app, select=...)``.
    """
    from a2kit.packages.select import compile_selector

    return tuple(compile_selector(e) for e in exprs)


def _apply_descriptor_selectors(
    descriptors: list[ToolDescriptor],
    selectors: tuple[Any, ...],
) -> list[ToolDescriptor]:
    """Filter projection-tool descriptors by ANDed selectors.

    For ``surface=`` selectors, also narrows each descriptor's
    ``expose`` tuple to the include intersection; a descriptor whose
    ``expose`` becomes empty is dropped entirely (the tool would have
    nowhere to surface).
    """
    if not selectors:
        return descriptors
    from dataclasses import replace

    out: list[ToolDescriptor] = []
    for desc in descriptors:
        if not all(s.matches(desc) for s in selectors):
            continue
        # Narrow expose to the intersection across all surface=
        # selectors. Each surface selector already passed `.matches`,
        # so the intersection is non-empty.
        narrowed = desc.expose
        for s in selectors:
            if s.category != "surface":
                continue
            if s.include:
                narrowed = tuple(sub for sub in narrowed if sub in s.include)
            if s.exclude:
                narrowed = tuple(sub for sub in narrowed if sub not in s.exclude)
        if not narrowed:
            continue
        out.append(replace(desc, expose=narrowed) if narrowed != desc.expose else desc)
    return out


def _filter_api_surface(api: Any, selectors: tuple[Any, ...]) -> Any:
    """Drop the api_surface entirely if any ``surface=`` selector excludes ``api``.

    The ``ApiSurface``'s routes are FastAPI-only by construction —
    ``surface=mcp`` (i.e. include={'mcp'}) means /api should not mount,
    so the surface is replaced with ``None``. Equivalent for the
    explicit ``surface=!api`` form.
    """
    if api is None or not selectors:
        return api
    for s in selectors:
        if s.category != "surface":
            continue
        if s.include and "api" not in s.include:
            return None
        if "api" in s.exclude:
            return None
    return api


def _filter_mcp_surface(mcp: Any, selectors: tuple[Any, ...]) -> Any:
    """Same shape as :func:`_filter_api_surface` for the FastMCP surface."""
    if mcp is None or not selectors:
        return mcp
    for s in selectors:
        if s.category != "surface":
            continue
        if s.include and "mcp" not in s.include:
            return None
        if "mcp" in s.exclude:
            return None
    return mcp


def _validate_descriptor_expose(descriptors: list[ToolDescriptor], surface_registry: Any) -> None:
    """Validate every captured `expose=` against the composed surface set.

    Per `bootstrap-surfaces-explicit`: surface name validation moves from
    decoration time (where the registry may not yet be populated) to build
    time (where `surfaces=` has been composed). Empty `expose=()` was
    already rejected at decoration. The default `_DEFAULT_EXPOSE` sentinel
    is also skipped (it stamps the bundled names regardless).
    """
    allowed = frozenset(surface_registry.names())
    if not allowed:
        return  # No surfaces composed; nothing to validate against.
    bad_per_tool: list[tuple[str, list[str]]] = []
    for desc in descriptors:
        bad = [s for s in desc.expose if s not in allowed]
        if bad:
            bad_per_tool.append((desc.name, bad))
    if not bad_per_tool:
        return
    registered = tuple(sorted(allowed))
    lines = [f"  - {name}: unknown surface(s) {bad!r}" for name, bad in bad_per_tool]
    msg = (
        "runtime.build(): tool(s) declare expose= names not in the composed surface set.\n"
        + "\n".join(lines)
        + f"\nComposed surfaces: {registered!r}. "
        "Pass surfaces=(...) to runtime.build() to register additional surfaces."
    )
    raise TypeError(msg)


def _assert_unique_canonical_names(descriptors: list[ToolDescriptor]) -> None:
    """Assert global canonical-name uniqueness; fail loud on the offending pair.

    The canonical name (``desc.name``, produced by the one shared
    :func:`a2kit._surfaces.resolve_canonical_name`) is the single call-journal
    / audit key (ADR 0028 decision 6). Two verbs resolving to the same name
    make every name-keyed consumer ambiguous, so uniqueness is **global** —
    independent of which surface each verb appears on. On collision this raises
    naming the canonical name and BOTH offending verbs (slug-or-app + leaf
    each); it never silently picks a winner, renames, or defers to dispatch.

    Layer 2 of the two-layer model: the static dup-name lint rule (layer 1)
    consumes the same resolver, so the layers cannot disagree.
    """

    def _ident(desc: ToolDescriptor) -> str:
        slug = getattr(desc.router, "slug", None)
        leaf = getattr(desc.fn, "__name__", "<verb>")
        return f"{slug}.{leaf}" if slug else f"<app>.{leaf}"

    seen: dict[str, ToolDescriptor] = {}
    for desc in descriptors:
        canonical = desc.name
        prior = seen.get(canonical)
        if prior is not None:
            msg = (
                f"duplicate canonical name {canonical!r}: {_ident(prior)} and "
                f"{_ident(desc)} resolve to the same name — the global "
                "call-journal / audit key (ADR 0028 decision 6). Rename one "
                "verb or give it a distinct canonical_name_override=."
            )
            raise ValueError(msg)
        seen[canonical] = desc


def validate_composition(app: App | AppRuntime) -> None:
    """Validate a compose-phase ``App`` WITHOUT a full surface build.

    The standalone runtime backstop (ADR 0028 decision 6, layer 2). For every
    projection verb (app-level verbs + every router's verbs) it resolves the
    surfaces matrix and the canonical name via the shared
    :func:`a2kit._surfaces.resolve_canonical_name`, then asserts **global**
    canonical-name uniqueness, failing loud on the offending pair. It also runs
    the same unknown-surface check ``build()`` performs, now reachable offline.

    Crucially it does NOT seal the App's container, re-materialize descriptors,
    or construct any transport (FastAPI / FastMCP / Typer) — so a unit test MAY
    assert that an App composes cleanly without standing up a runtime. Returns
    ``None`` on success. ``build()`` invokes the same uniqueness backstop over
    its snapshotted descriptors, so the two entry points share one resolver and
    cannot drift.
    """
    descriptors: list[ToolDescriptor]
    if isinstance(app, AppRuntime):
        descriptors = list(app.descriptors())
    else:
        # Compose-phase descriptors: materialized at compose time, carrying the
        # canonical ``name`` from the shared resolver. Reading them touches no
        # container seal and builds no transport.
        descriptors = app.tools()

    from a2kit import compose_default_surfaces  # noqa: A2K-PKG-INIT-IMPORT

    surface_registry = compose_default_surfaces()
    if surface_registry is not None:
        _validate_descriptor_expose(descriptors, surface_registry)
    _assert_unique_canonical_names(descriptors)


__all__ = ["AppRuntime", "build", "validate_composition"]
