"""Typed DI container — feature-agnostic, sync + async resolution paths.

Resolution surface (post-v0.37 dispatch-lifecycle-wiring):

- ``Container.dispatch(fn, wire_kwargs, *, pre_hook=None)`` — async-CM
  for per-call dispatch (opens a child, runs the optional pre_hook,
  runs ``resolve_params`` for DI, yields merged kwargs, unwinds
  per-call cleanup on exit).
- ``Container.resolve_params(fn)`` — resolves a function's parameters
  through DI, ``Lazy[T]``-aware.
- ``Container.get(t)`` — async lifecycle-aware resolve honoring scope,
  ``__aenter__``, cleanup recording.
- ``Container.provide(t, factory, *, scope)`` / ``has_provider`` /
  ``providers_view`` — v0.36 registration surface.

Legacy surface (still in place for TestClient seam + sync test paths):
``register`` / ``register_singleton`` / ``resolve`` / ``aresolve`` /
``has`` / ``has_async_singleton``. Scheduled for separate retirement.

Wire-input transformation (e.g. ``connection: str`` → typed config)
lives in the consumer's dispatch hook (``pre_hook`` arg), wire-side only
— DI runs after, on the hook's output.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import weakref
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

from a2kit.packages.di._cleanup_stack import CleanupStack
from a2kit.packages.di._introspection import (
    Factory,
    UnresolvableType,
    _factory_params,
    _ParamSpec,
)
from a2kit.packages.di.scope import Scope

if TYPE_CHECKING:
    from collections.abc import Callable

_log = logging.getLogger(__name__)

T = TypeVar("T")


class Container:
    """Synchronous typed DI container.

    Construct one per :class:`a2kit.App`. The container holds the App's
    singletons (cached values shared across dispatches) and per-call
    providers (fresh instances per dispatch).

    Resolution is per-call: pass a fresh cache dict to :meth:`resolve` each
    time so two kwargs of the same type share one instance within a call
    but never across calls.
    """

    def __init__(self) -> None:
        self._providers: dict[type, Factory] = {}
        # Singleton cache: type → cached instance.
        self._singletons: dict[type, Any] = {}
        # Types whose singleton factory is async. First aresolve awaits;
        # sync resolve raises a precise error while the cache is unresolved.
        self._async_factories: set[type] = set()
        # Per-type asyncio.Lock for concurrent first-resolution coalescing.
        # Created lazily on first aresolve to avoid touching the running
        # loop at registration time.
        self._async_singleton_locks: dict[type, asyncio.Lock] = {}
        # Cached parameter introspection per factory, keyed on the live factory
        # object via a ``WeakKeyDictionary``. The id(factory)-keyed cache that
        # preceded this would hit stale entries when CPython recycled function
        # ids across nested test scopes — the same hazard documented for the
        # tool-signature cache in ``a2kit/signature.py``'s design note.
        # ``WeakKeyDictionary`` keys on the object identity and auto-vacates
        # on GC, eliminating both the aliasing and the memory-growth modes.
        self._param_cache: weakref.WeakKeyDictionary[Factory, list[_ParamSpec]] = weakref.WeakKeyDictionary()
        # Generic "wire-scoped string" registry. Consumer packages register
        # a scope name (e.g. ``"connection"``) and the types whose values
        # are populated from that wire string. The container holds the
        # mapping but knows nothing about specific scope semantics — those
        # live in the consumer's dispatch hook. Schema generation consults
        # this to synthesize the wire-side string param.
        self._wire_scopes: dict[str, set[type]] = {}

        # --- new di-scoped-lifecycle state --------------------------------
        # Registered scope per type. Defaults to SINGLETON for ``provide`` /
        # ``register_singleton``; SCOPED entries are child-container-scoped.
        self._scope_metadata: dict[type, Scope] = {}
        # Per-container cleanup stack. Root container holds app-scope
        # cleanups; child containers hold per-call cleanups.
        self._cleanup_stack: CleanupStack = CleanupStack()
        # Set once :meth:`__aenter__` has been called on this container —
        # blocks further ``provide`` registrations.
        self._sealed: bool = False
        # Parent (root) container for child containers. ``None`` for the
        # root. Children share the parent's providers + scope_metadata +
        # app-scope cache but maintain their own scoped cache + cleanup.
        self._parent: Container | None = None
        # Per-call (SCOPED) cache. Empty on root; populated on children.
        self._scoped_cache: dict[type, Any] = {}
        # Per-type async locks for lifecycle-aware ``get(T)`` so concurrent
        # first-touches coalesce. Separate from the older
        # ``_async_singleton_locks`` used by the legacy ``aresolve`` path.
        self._get_locks: dict[type, asyncio.Lock] = {}

    # -- registration --------------------------------------------------- #

    def register(self, type_: type, factory: Factory | None = None) -> None:
        """Register ``factory`` (or ``type_`` itself) as the provider for ``type_``.

        When ``factory`` is None, the class itself becomes the factory and
        the container will introspect ``type_.__init__`` at resolve time.
        Factories MUST be synchronous (``def``, not ``async def``); async
        factories raise ``ValueError`` at registration.
        """
        if factory is None:
            factory = type_
        if inspect.iscoroutinefunction(factory):
            msg = (
                f"provider for {type_!r}: factory is `async def`, but container "
                "factories must be synchronous. Async resource initialization belongs "
                "in resource classes (lazy-init pattern) or at the composition root "
                "(see README 'Resource pattern' appendix)."
            )
            raise ValueError(msg)
        if inspect.isclass(factory):
            for spec in _factory_params(factory):
                if not spec.has_default and spec.annotation is inspect.Parameter.empty:
                    msg = f"provider for {type_!r}: parameter {spec.name!r} lacks an annotation"
                    raise ValueError(msg)
        self._providers[type_] = factory

    def register_singleton(self, type_: type, factory: Factory) -> None:
        """Register a factory whose result is cached on this Container.

        The factory may be sync (``def``) or async (``async def``). First
        resolution of an async-factory singleton runs inside an event
        loop via :meth:`aresolve` (or any code path the framework
        dispatches inside one — e.g. App ``__aenter__`` eagerly resolves
        every registered singleton). Subsequent resolves return the
        cached value. Sync :meth:`resolve` on an unresolved async
        singleton raises a precise error.
        """
        is_async = inspect.iscoroutinefunction(factory)
        if is_async:
            self._async_factories.add(type_)
        # Sentinel: registered but not yet resolved.
        if type_ not in self._singletons:
            self._singletons[type_] = _UNRESOLVED
        self._providers[type_] = factory

    def has(self, type_: Any) -> bool:
        return type_ in self._providers

    def has_singleton(self, type_: Any) -> bool:
        return type_ in self._singletons

    def providers(self) -> dict[type, Factory]:
        return dict(self._providers)

    def register_wire_scope(self, scope_name: str, *types: type) -> None:
        """Track ``types`` as populated by a wire-side string named ``scope_name``.

        The container holds the mapping but does no resolution work for it.
        The consumer's dispatch hook is responsible for converting the wire
        string into typed instances and substituting them into kwargs before
        the container's ``apply_kwargs`` runs.
        """
        self._wire_scopes.setdefault(scope_name, set()).update(types)

    def wire_scopes(self) -> dict[str, set[type]]:
        """Snapshot of registered wire scopes (read-only view, deep-copied)."""
        return {name: set(ts) for name, ts in self._wire_scopes.items()}

    def wire_scopes_used_by(self, fn: Callable[..., Any]) -> set[str]:
        """Return scope names whose registered types are reachable from fn's params.

        Walks the dependency chain: a tool taking ``store: Store`` where ``Store``
        depends on ``cfg: Cfg`` and ``Cfg`` is in the ``connection`` wire scope
        still needs ``connection`` in the wire schema.
        """
        reachable: set[Any] = set()
        for spec in _params_for_method(fn):
            self._collect_reachable(spec.annotation, reachable)
        return {name for name, ts in self._wire_scopes.items() if ts & reachable}

    def _collect_reachable(self, type_: Any, seen: set[Any]) -> None:
        """Walk the provider chain from ``type_`` and accumulate all annotations."""
        if type_ in seen:
            return
        seen.add(type_)
        factory = self._providers.get(type_)
        if factory is None:
            return
        for spec in self._params_for(factory):
            self._collect_reachable(spec.annotation, seen)

    def singletons(self) -> dict[type, Any]:
        """Snapshot of registered singletons; unresolved entries carry the sentinel."""
        return dict(self._singletons)

    # -- resolution ----------------------------------------------------- #

    def resolve(
        self,
        type_: type,
        *,
        cache: dict[type, Any] | None = None,
        chain: list[type] | None = None,
    ) -> Any:
        """Resolve ``type_`` synchronously.

        Per-call cache prevents the same factory from running twice within
        one resolution. Singleton-registered types short-circuit to their
        cached value after first resolve.
        """
        if cache is None:
            cache = {}
        if chain is None:
            chain = []
        # Singleton fast-path.
        if type_ in self._singletons:
            cached = self._singletons[type_]
            if cached is not _UNRESOLVED:
                return cached
            if type_ in self._async_factories:
                msg = (
                    f"singleton {type_!r} has an async factory and has not been "
                    "resolved yet. Use the async resolve path (the dispatcher "
                    "runs async, so depending on this type from a tool body is "
                    "fine), or warm it up by calling "
                    "`await app.warm_async_singletons()` from inside the "
                    "App's lifespan body so sync resolve sees a cached value."
                )
                raise ValueError(msg)
        if type_ in cache:
            return cache[type_]
        if type_ in chain:
            msg = f"provider cycle: {[*chain, type_]}"
            raise ValueError(msg)
        factory = self._providers.get(type_)
        if factory is None:
            raise UnresolvableType(type_, [*chain])

        new_chain = [*chain, type_]
        kwargs = self._resolve_factory_kwargs(factory, cache, new_chain)
        result = factory(**kwargs)
        if type_ in self._singletons:
            # Singleton: cache permanently.
            self._singletons[type_] = result
        cache[type_] = result
        return result

    async def aresolve(
        self,
        type_: type,
        *,
        cache: dict[type, Any] | None = None,
        chain: list[type] | None = None,
    ) -> Any:
        """Resolve ``type_`` from within an event loop.

        Hot path is identical to :meth:`resolve` (cached lookup). Cold path
        for async-factory singletons takes the per-type lock, double-checks
        the cache, awaits the factory, and caches the result. Two concurrent
        first-resolution calls for the same type coalesce on the lock; the
        factory runs at most once. Resolving sub-dependencies of an async
        factory uses this same path, so an async factory may depend on
        other async singletons.

        v0.36 bridge: when ``type_`` was registered via the new
        ``provide(...)`` API (has scope metadata), delegate to
        :meth:`get` so ``__aenter__`` / cleanup wire through the per-scope
        cleanup stack uniformly.
        """
        if cache is None:
            cache = {}
        if chain is None:
            chain = []
        # New-API bridge: any type registered via `provide()` carries scope
        # metadata; route through `get` so lifecycle is honored.
        if type_ in self._scope_metadata:
            return await self.get(type_)
        cached = self._cached_or_none(type_, cache)
        if cached is not _MISSING:
            return cached
        if type_ in chain:
            msg = f"provider cycle: {[*chain, type_]}"
            raise ValueError(msg)
        factory = self._providers.get(type_)
        if factory is None:
            raise UnresolvableType(type_, [*chain])

        new_chain = [*chain, type_]
        if type_ in self._singletons and type_ in self._async_factories:
            return await self._aresolve_async_singleton(type_, factory, cache, new_chain)
        kwargs = await self._aresolve_factory_kwargs(factory, cache, new_chain)
        result = factory(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        if type_ in self._singletons:
            self._singletons[type_] = result
        cache[type_] = result
        return result

    def _cached_or_none(self, type_: type, cache: dict[type, Any]) -> Any:
        """Return cached value (singleton or per-call) or ``_MISSING``."""
        if type_ in self._singletons:
            cached = self._singletons[type_]
            if cached is not _UNRESOLVED:
                return cached
        if type_ in cache:
            return cache[type_]
        return _MISSING

    async def _aresolve_async_singleton(
        self,
        type_: type,
        factory: Factory,
        cache: dict[type, Any],
        new_chain: list[type],
    ) -> Any:
        lock = self._async_singleton_locks.get(type_)
        if lock is None:
            lock = asyncio.Lock()
            self._async_singleton_locks[type_] = lock
        async with lock:
            cached = self._singletons.get(type_, _UNRESOLVED)
            if cached is not _UNRESOLVED:
                return cached
            kwargs = await self._aresolve_factory_kwargs(factory, cache, new_chain)
            result = factory(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            self._singletons[type_] = result
            cache[type_] = result
            return result

    async def _aresolve_factory_kwargs(
        self,
        factory: Factory,
        cache: dict[type, Any],
        new_chain: list[type],
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        for spec in self._params_for(factory):
            if self.has(spec.annotation):
                kwargs[spec.name] = await self.aresolve(
                    spec.annotation,
                    cache=cache,
                    chain=new_chain,
                )
                continue
            if spec.has_default:
                continue
            raise UnresolvableType(spec.annotation, new_chain)
        return kwargs

    def _resolve_factory_kwargs(
        self,
        factory: Factory,
        cache: dict[type, Any],
        new_chain: list[type],
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        for spec in self._params_for(factory):
            if self.has(spec.annotation):
                kwargs[spec.name] = self.resolve(
                    spec.annotation,
                    cache=cache,
                    chain=new_chain,
                )
                continue
            if spec.has_default:
                continue
            raise UnresolvableType(spec.annotation, new_chain)
        return kwargs

    def has_async_singleton(self, type_: type) -> bool:
        return type_ in self._async_factories

    def has_any_async_singletons(self) -> bool:
        return bool(self._async_factories)

    # -- test seam: snapshot/restore for TestClient.override -------------- #

    def _override(self, type_: type, instance: object) -> None:
        """Pin ``type_`` to ``instance`` across all resolution paths.

        Test-only seam owning the three-attribute mutation: install a
        constant factory in `_providers`, cache `instance` in
        `_singletons`, and clear any async-factory marker on `type_` so
        sync `resolve` no longer raises. Idempotent and feature-agnostic.
        """
        self._providers[type_] = lambda: instance
        self._singletons[type_] = instance
        self._async_factories.discard(type_)

    def _snapshot(self) -> _ContainerSnapshot:
        """Capture the registration + cache state for later restore.

        Test-only seam — `TestClient.override` uses this to roll back
        DI mutations at the end of a test session. Hot path resolution
        never consults a snapshot.
        """
        return _ContainerSnapshot(
            providers=dict(self._providers),
            singletons=dict(self._singletons),
            async_factories=set(self._async_factories),
        )

    def _restore(self, snapshot: _ContainerSnapshot) -> None:
        """Restore the registration + cache state from a prior snapshot."""
        self._providers = dict(snapshot.providers)
        self._singletons = dict(snapshot.singletons)
        self._async_factories = set(snapshot.async_factories)
        # Locks are rebuilt lazily; drop any held by overridden types.
        self._async_singleton_locks = {t: lock for t, lock in self._async_singleton_locks.items() if t in self._async_factories}

    # -- di-scoped-lifecycle public surface ----------------------------- #

    def provide(
        self,
        type_: type,
        factory: Factory | None = None,
        *,
        scope: Scope = Scope.SINGLETON,
    ) -> None:
        """Register ``factory`` (or ``type_`` itself) for ``type_`` at ``scope``.

        Last-write-wins: a second :meth:`provide` for the same type
        silently overrides the prior provider (composition-root override
        pattern; no special test-only API needed).

        Raises ``TypeError`` if called after :meth:`__aenter__` (the
        container is sealed against further registration).

        For ``Scope.SCOPED`` the factory may be sync or async; the
        per-call child container will await it during resolution.
        """
        if self._sealed:
            msg = (
                f"Container is sealed after __aenter__; cannot provide({type_!r}). "
                "Register all providers at composition time, before "
                "`async with app:` enters. To override a provider for a test, "
                "re-register it in the composition root before app entry."
            )
            raise TypeError(msg)

        if factory is None:
            factory = type_

        # Class-as-factory: validate annotations exist for required params.
        if inspect.isclass(factory):
            for spec in _factory_params(factory):
                if not spec.has_default and spec.annotation is inspect.Parameter.empty:
                    msg = (
                        f"provider for {type_!r}: parameter {spec.name!r} lacks an annotation"
                    )
                    raise ValueError(msg)

        is_async = inspect.iscoroutinefunction(factory)
        if scope is Scope.SINGLETON:
            if is_async:
                self._async_factories.add(type_)
            else:
                self._async_factories.discard(type_)
            if type_ not in self._singletons:
                self._singletons[type_] = _UNRESOLVED
            else:
                # Re-registration overrides any cached value too.
                self._singletons[type_] = _UNRESOLVED
        else:
            # SCOPED: don't pre-register in singletons cache; ensure no
            # stale singleton entry survives from a prior provide() call.
            self._singletons.pop(type_, None)
            self._async_factories.discard(type_)

        self._providers[type_] = factory
        self._scope_metadata[type_] = scope

    def has_provider(self, type_: Any) -> bool:
        """True when this container (or its parent) holds a provider for ``type_``."""
        if type_ in self._providers:
            return True
        if self._parent is not None:
            return self._parent.has_provider(type_)
        return False

    def providers_view(self) -> dict[type, Factory]:
        """Snapshot of (parent-chain-aware) provider map."""
        merged: dict[type, Factory] = {}
        if self._parent is not None:
            merged.update(self._parent.providers_view())
        merged.update(self._providers)
        return merged

    async def get(self, type_: type) -> Any:
        """Lifecycle-aware resolve honoring scope, ``__aenter__``, cleanup.

        Resolution order:

        1. SINGLETON cache hit on root → return cached value.
        2. SCOPED cache hit on this child → return cached value.
        3. Otherwise: take per-type lock, double-check cache, build the
           instance (chain-resolving constructor deps via :meth:`get`),
           enter ``__aenter__`` if present, record cleanup, cache.

        Auto-resolves ``pydantic_settings.BaseSettings`` subclasses via
        duck-typing if no explicit provider is registered.
        """
        # Check the calling container's scope metadata first — wire-seeded
        # SCOPED types live only on the child; the root would resolve them
        # as SINGLETON (the default) and miss them.
        scope = self._scope_of(type_)
        if scope is Scope.SINGLETON:
            cached = self._root()._singletons.get(type_, _UNRESOLVED)
            if cached is not _UNRESOLVED:
                return cached
            return await self._root()._build_singleton(type_)

        # SCOPED on this child (or transient — TRANSIENT not on App surface yet).
        if type_ in self._scoped_cache:
            return self._scoped_cache[type_]

        # SCOPED resolution happens on the child holding the per-call cache.
        return await self._build_scoped(type_)

    def child(self) -> Container:
        """Open a child container for a per-call (SCOPED) lifetime.

        Shares the parent's providers + scope metadata + app-scope cache.
        Holds its own scoped cache and cleanup stack. Re-entry of the
        parent's app-scope resources does NOT happen — they are resolved
        once and reused.
        """
        child = Container()
        child._parent = self._root()
        return child

    async def aclose(
        self,
        exc_type: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: object | None = None,
    ) -> None:
        """Unwind this container's cleanup stack in LIFO order."""
        await self._cleanup_stack.aclose(exc_type, exc, tb)

    @contextlib.asynccontextmanager
    async def dispatch(
        self,
        fn: Callable[..., Any],
        wire_kwargs: dict[str, Any] | None = None,
        *,
        pre_hook: Callable[..., Any] | None = None,
    ) -> Any:
        """Per-call dispatch helper for the framework.

        Opens a child resolver, optionally calls ``pre_hook`` for
        wire-side resolution (e.g. connection-string → typed config),
        resolves ``fn``'s injectable kwargs from the child container
        (including ``Lazy[T]`` closures), merges everything, yields
        the merged kwarg dict. On exit, unwinds the child's cleanup
        stack — per-call resources see the propagating exception via
        standard ``__aexit__`` semantics.

        ``pre_hook`` contract: wire-side conversion only. The hook
        receives ``(fn, dict(wire_kwargs))``, may be sync or async,
        and returns a ``dict[str, Any]`` of wire-side resolved kwargs
        (e.g. ``{"connection": <TrackerConn instance>}``). It MUST NOT
        call DI (``apply_kwargs``, ``get``) — DI is the framework's
        job, run after the hook on the hook's output.

        Example::

            async def my_hook(fn, kw):
                kw["connection"] = await store.load(kw["connection"])
                return kw

            async with app._resolver.dispatch(tool_fn, {"connection": "x"}, pre_hook=my_hook) as kw:
                result = await tool_fn(**kw)
        """
        wire: dict[str, Any] = dict(wire_kwargs) if wire_kwargs else {}
        async with self.child() as child:
            if pre_hook is not None:
                hook_result = pre_hook(fn, wire)
                if inspect.isawaitable(hook_result):
                    hook_result = await hook_result
                wire = dict(hook_result) if hook_result else {}
            # Seed the child with wire-resolved typed instances as
            # SCOPED providers so chain resolution from any factory
            # can find them. Walks ALL wire kwargs: each value's
            # concrete class becomes a type-keyed seed on the child.
            # Primitives (str/int/bool/etc.) seed too — harmless if
            # nothing chains through them, useful if a tool actually
            # takes the wire kwarg by type rather than by name.
            for _wire_val in wire.values():
                _t = type(_wire_val)
                child._providers[_t] = (lambda v=_wire_val: v)
                child._scope_metadata[_t] = Scope.SCOPED
                child._scoped_cache[_t] = _wire_val
            resolved = await child.resolve_params(fn)
            # Filter merged kwargs to fn's actual params so wire-side
            # inputs that the hook used (e.g. raw connection string) but
            # the tool doesn't declare are not passed through.
            fn_param_names = {spec.name for spec in _params_for_method(fn)}
            # Wire kwargs take precedence over resolved injectables when
            # both name the same param (wire-aware tools declare
            # connection-style params alongside injectables).
            merged: dict[str, Any] = {
                **{k: v for k, v in resolved.items() if k in fn_param_names},
                **{k: v for k, v in wire.items() if k in fn_param_names},
            }
            yield merged

    async def resolve_params(self, fn: Callable[..., Any]) -> dict[str, Any]:
        """Resolve ``fn``'s parameter kwargs, honoring ``Lazy[T]`` annotations.

        For each parameter:

        - Annotation is ``Lazy[T]`` (``Callable[[], Awaitable[T]]``):
          inject a zero-arg async closure that resolves ``T`` via
          :meth:`get` when first awaited. Never invoked = ``T`` never
          built.
        - Annotation is a registered (or auto-resolvable) type ``T``:
          eagerly call ``await self.get(T)`` and inject the instance.
        - Otherwise: omit — caller treats as wire kwarg.
        """
        out: dict[str, Any] = {}
        for spec in _params_for_method(fn):
            ann = spec.annotation
            lazy_inner = _lazy_inner_type(ann)
            if lazy_inner is not None:
                out[spec.name] = self._make_lazy_closure(lazy_inner)
                continue
            if self.has_provider(ann) or _looks_like_basesettings(ann):
                out[spec.name] = await self.get(ann)
        return out

    def _make_lazy_closure(self, type_: type) -> Callable[[], Any]:
        async def _lazy() -> Any:
            return await self.get(type_)

        return _lazy

    async def __aenter__(self) -> Container:
        """Enter the container's lifecycle scope.

        Root container: seals registration, validates the provider graph
        (rejects app-scope factories depending on scoped types).

        Child container: no-op; child enters its scope on construction.
        """
        if self._parent is None:
            self._validate_scope_graph()
            self._sealed = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: object | None = None,
    ) -> None:
        """Exit the container's lifecycle scope, unwinding cleanups."""
        await self.aclose(exc_type, exc, tb)

    # -- internal helpers for the new surface --------------------------- #

    def _root(self) -> Container:
        return self if self._parent is None else self._parent

    def _scope_of(self, type_: type) -> Scope:
        scope = self._scope_metadata.get(type_)
        if scope is not None:
            return scope
        if self._parent is not None:
            return self._parent._scope_of(type_)
        # Unregistered types default to SINGLETON resolution semantics
        # (BaseSettings auto-resolve falls under this).
        return Scope.SINGLETON

    def _provider_for(self, type_: type) -> Factory | None:
        f = self._providers.get(type_)
        if f is not None:
            return f
        if self._parent is not None:
            return self._parent._provider_for(type_)
        return None

    async def _build_singleton(self, type_: type) -> Any:
        root = self._root()
        lock = root._get_locks.setdefault(type_, asyncio.Lock())
        async with lock:
            cached = root._singletons.get(type_, _UNRESOLVED)
            if cached is not _UNRESOLVED:
                return cached
            instance = await self._construct(type_, scope=Scope.SINGLETON)
            root._singletons[type_] = instance
            return instance

    async def _build_scoped(self, type_: type) -> Any:
        instance = await self._construct(type_, scope=Scope.SCOPED)
        self._scoped_cache[type_] = instance
        return instance

    async def _construct(self, type_: type, *, scope: Scope) -> Any:
        """Build an instance via the registered (or auto-resolved) factory.

        Chain-resolves constructor parameters via :meth:`get` on the
        appropriate container. Enters ``__aenter__`` if the instance is
        a context manager, then records cleanup on the right scope's stack.
        """
        factory = self._provider_for(type_)
        if factory is None:
            # BaseSettings auto-resolve (duck-typed; no pydantic import).
            if _looks_like_basesettings(type_):
                # pydantic-settings reads env at zero-arg construction; skip
                # parameter introspection of its `__init__(__pydantic_self__, **data)`.
                result: Any = type_()
            else:
                raise UnresolvableType(type_, [])
        else:
            kwargs = await self._construct_kwargs(factory)
            result = factory(**kwargs)
        if inspect.isawaitable(result):
            result = await result

        # Enter __aenter__ / generator-yield (single-protocol convention).
        instance, aexit = await _enter_lifecycle(result)

        # Record cleanup on the appropriate stack.
        target = self._root() if scope is Scope.SINGLETON else self
        if aexit is not None:
            target._cleanup_stack.record(type_, aexit)

        return instance

    async def _construct_kwargs(self, factory: Factory) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        for spec in self._params_for(factory):
            ann = spec.annotation
            if ann is inspect.Parameter.empty:
                if spec.has_default:
                    continue
                msg = f"factory {factory!r}: parameter {spec.name!r} lacks an annotation"
                raise ValueError(msg)
            if self.has_provider(ann) or _looks_like_basesettings(ann):
                kwargs[spec.name] = await self.get(ann)
                continue
            if spec.has_default:
                continue
            raise UnresolvableType(ann, [])
        return kwargs

    def _validate_scope_graph(self) -> None:
        """Reject app-scope factories that depend on per-call types."""
        for type_, scope in self._scope_metadata.items():
            if scope is not Scope.SINGLETON:
                continue
            factory = self._providers.get(type_)
            if factory is None:
                continue
            for spec in self._params_for(factory):
                dep = spec.annotation
                dep_scope = self._scope_metadata.get(dep)
                if dep_scope is Scope.SCOPED:
                    msg = (
                        f"scope violation: app-scope depends on per-call. "
                        f"App-scope provider for {type_!r} declares parameter "
                        f"{spec.name!r} of per-call type {dep!r}. "
                        "Per-call types live for one dispatch; an app-scope "
                        "instance would cache a stale per-call value. "
                        "Either move the dependent to per-call too, or use "
                        "`Lazy[" + getattr(dep, "__name__", repr(dep)) + "]` "
                        "to defer resolution into the call scope."
                    )
                    raise TypeError(msg)

    # -- internal ------------------------------------------------------- #

    def _params_for(self, factory: Factory) -> list[_ParamSpec]:
        cached = self._param_cache.get(factory)
        if cached is not None:
            return cached
        params = _factory_params(factory)
        self._param_cache[factory] = params
        return params


class _Unresolved:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<UNRESOLVED>"


_UNRESOLVED: Any = _Unresolved()


@dataclass(frozen=True, slots=True)
class _ContainerSnapshot:
    """Opaque snapshot of container state for the test-override seam."""

    providers: dict[type, Factory] = field(default_factory=dict)
    singletons: dict[type, Any] = field(default_factory=dict)
    async_factories: set[type] = field(default_factory=set)


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<MISSING>"


_MISSING: Any = _Missing()


def _lazy_inner_type(ann: Any) -> type | None:  # noqa: PLR0911
    """If ``ann`` is ``Lazy[T]`` / ``Callable[[], Awaitable[T]]``, return ``T``.

    Recognizes the user-facing ``a2kit.Lazy`` alias plus the equivalent
    raw ``Callable[[], Awaitable[T]]`` shape. Returns ``None`` for any
    other annotation.
    """
    import typing as _typing
    from collections.abc import Awaitable as _Awaitable
    from collections.abc import Callable as _Callable

    origin = _typing.get_origin(ann)
    if origin is None:
        return None
    if origin not in (_Callable, _typing.Callable):  # type: ignore[attr-defined]
        return None
    args = _typing.get_args(ann)
    if len(args) != 2:
        return None
    # Callable[[arg_types...], ret_type]
    callable_args, ret = args
    if callable_args != []:
        return None
    ret_origin = _typing.get_origin(ret)
    if ret_origin not in (_Awaitable, _typing.Awaitable):  # type: ignore[attr-defined]
        return None
    inner = _typing.get_args(ret)
    if len(inner) != 1:
        return None
    t = inner[0]
    if isinstance(t, type):
        return t
    return None


def _looks_like_basesettings(type_: Any) -> bool:
    """Duck-typed detection of ``pydantic_settings.BaseSettings`` subclasses.

    Walks ``type_.__mro__`` looking for a class whose ``__module__`` starts
    with ``pydantic_settings`` and whose ``__name__`` is ``BaseSettings``.
    Duck-typed on purpose: the container stays usable without the optional
    settings dependency installed.
    """
    if not inspect.isclass(type_):
        return False
    for base in type_.__mro__:
        mod = getattr(base, "__module__", "") or ""
        name = getattr(base, "__name__", "")
        if name == "BaseSettings" and mod.startswith("pydantic_settings"):
            return True
    return False


async def _enter_lifecycle(result: Any) -> tuple[Any, Callable[..., Any] | None]:
    """Single-protocol entry: only ``__aenter__``/``__aexit__`` is honored.

    Returns ``(instance, aexit_callable_or_None)``. The ``aexit`` callable
    forwards ``(exc_type, exc, tb)`` to the resource's ``__aexit__`` so
    per-call resources see the propagating body exception (matching the
    Python ``async with`` protocol).

    ``aclose`` / ``close`` are NOT auto-detected — wrap such resources in
    a class with ``__aenter__``/``__aexit__`` or use ``@asynccontextmanager``.

    Partial-entry safety: nothing is returned to the caller until
    ``__aenter__`` succeeded.
    """
    if hasattr(result, "__aenter__") and hasattr(result, "__aexit__"):
        instance = await result.__aenter__()

        async def _aexit(exc_type: Any = None, exc: Any = None, tb: Any = None) -> None:
            await result.__aexit__(exc_type, exc, tb)

        return instance, _aexit
    return result, None


def _params_for_method(fn: Callable[..., Any]) -> list[_ParamSpec]:
    """Method-aware variant of :func:`_factory_params` (skips ``self``)."""
    from a2kit.packages.di._hints import resolve_hints

    hints = resolve_hints(fn)
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return []
    out: list[_ParamSpec] = []
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        ann = hints.get(pname, param.annotation)
        has_default = param.default is not inspect.Parameter.empty
        out.append(_ParamSpec(pname, ann, has_default))
    return out


__all__ = [
    "Container",
    "Factory",
    "UnresolvableType",
]
