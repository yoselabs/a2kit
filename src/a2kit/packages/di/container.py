"""Typed DI container — feature-agnostic, async lifecycle-aware resolution.

Public surface: ``provide`` / ``seed_scoped`` / ``has_provider`` /
``providers_view`` (registration); ``call_scope`` / ``resolve_params``
/ ``get`` / ``child`` (resolution); async lifecycle via ``__aenter__`` /
``__aexit__`` / ``aclose``.

Wire-input transformation (e.g. ``connection: str`` → typed config)
lives in the consumer's dispatch hook (``pre_hook`` arg). The hook may
publish typed instances on the per-call child via the ``seed`` callable
it receives.

Legacy methods (``register`` / ``register_singleton`` / ``resolve`` /
``aresolve`` / ``has`` / async-singleton helpers) raise ``TypeError``
with v0.38 migration hints. See CHANGELOG.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import weakref
from typing import TYPE_CHECKING, Any, NoReturn, TypeVar

from a2kit.packages.di._cleanup_stack import CleanupStack
from a2kit.packages.di._helpers import (
    enter_lifecycle as _enter_lifecycle,
)
from a2kit.packages.di._helpers import (
    lazy_inner_type as _lazy_inner_type,
)
from a2kit.packages.di._helpers import (
    looks_like_basesettings as _looks_like_basesettings,
)
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


_RETIRED_V038 = "v0.38 (see CHANGELOG retire-legacy-di-surface)"


def _retired(old: str, replacement: str) -> NoReturn:
    msg = f"Container.{old} was retired in {_RETIRED_V038}. Replacement: {replacement}."
    raise TypeError(msg)


class Container:
    """Typed async DI container with lifecycle-aware resolution.

    Construct one per :class:`a2kit.App`. The container holds the App's
    app-scope cache (instances shared across dispatches) and opens a
    per-call child via :meth:`child` / :meth:`dispatch` for SCOPED types.
    """

    def __init__(self) -> None:
        self._providers: dict[type, Factory] = {}
        # Canonical app-scope cache: type → built instance. Populated by
        # ``_build_singleton`` on first ``get(T)``. Absent keys mean "not
        # yet built" (lazy first-use, post-v0.36).
        self._singletons: dict[type, Any] = {}
        # Cached parameter introspection per factory, WeakKeyDictionary so
        # CPython id-recycling across test scopes doesn't surface stale entries
        # (same hazard as ``a2kit/signature.py``'s tool-signature cache).
        self._param_cache: weakref.WeakKeyDictionary[Factory, list[_ParamSpec]] = weakref.WeakKeyDictionary()
        # Wire-scope name → typed members. Consumer packages register a scope
        # name (e.g. ``"connection"``) and the types whose values are populated
        # from that wire string. Schema generation reads this to synthesize the
        # wire-side string param.
        self._wire_scopes: dict[str, set[type]] = {}

        # Registered scope per type. Defaults to SINGLETON for ``provide``;
        # SCOPED entries are child-container-scoped.
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
        # first-touches coalesce.
        self._get_locks: dict[type, asyncio.Lock] = {}

    # -- retired surface (loud-crash shims; see CHANGELOG) ---------------- #

    def register(self, type_: type, factory: Factory | None = None) -> NoReturn:  # noqa: ARG002
        _retired("register(T, factory)", "Container.provide(T, factory)")

    def register_singleton(self, type_: type, factory: Factory) -> NoReturn:  # noqa: ARG002
        _retired("register_singleton(T, factory)", "Container.provide(T, factory, scope=Scope.SINGLETON)")

    def resolve(self, type_: type, *, cache: Any = None, chain: Any = None) -> NoReturn:  # noqa: ARG002
        _retired("resolve(T)", "await Container.get(T)")

    async def aresolve(self, type_: type, *, cache: Any = None, chain: Any = None) -> NoReturn:  # noqa: ARG002
        _retired("aresolve(T)", "await Container.get(T)")

    def has(self, type_: Any) -> NoReturn:  # noqa: ARG002
        _retired("has(T)", "Container.has_provider(T)")

    def has_async_singleton(self, type_: type) -> NoReturn:  # noqa: ARG002
        _retired("has_async_singleton(T)", "no replacement — provide(scope=SINGLETON) takes sync or async factories")

    def has_any_async_singletons(self) -> NoReturn:
        _retired("has_any_async_singletons()", "no replacement — async/sync factories no longer distinguished")

    # -- registration --------------------------------------------------- #

    def register_wire_scope(self, scope_name: str, *types: type) -> None:
        """Track ``types`` as populated by a wire-side string named ``scope_name``.

        The container holds the mapping but does no resolution work for it.
        The consumer's dispatch hook is responsible for converting the wire
        string into typed instances and substituting them into kwargs before
        DI runs.
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

    # -- di-scoped-lifecycle public surface ----------------------------- #

    def seal(self) -> None:
        """Validate the provider graph and seal against further ``provide``.

        Idempotent. Finishers reach this via :meth:`App._seal`; the root
        container's :meth:`__aenter__` also calls it defensively. After
        ``seal``, :meth:`provide` raises.

        Validation rejects app-scope factories that depend on per-call
        types (directly or via ``Lazy[per-call-T]``).
        """
        if self._sealed:
            return
        self._validate_scope_graph()
        self._sealed = True

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
                f"Container is sealed; cannot provide({type_!r}). "
                "Register all providers on the App before handing it to a "
                "finisher (run / build_mcp_server / testing.client). "
                "To override a provider for a test, re-register it on a fresh "
                "a2kit.App (provide is last-write-wins)."
            )
            raise TypeError(msg)

        if factory is None:
            factory = type_

        # Class-as-factory: validate annotations exist for required params.
        if inspect.isclass(factory):
            for spec in _factory_params(factory):
                if not spec.has_default and spec.annotation is inspect.Parameter.empty:
                    msg = f"provider for {type_!r}: parameter {spec.name!r} lacks an annotation"
                    raise ValueError(msg)

        # Re-registration: drop any prior cached instance.
        self._singletons.pop(type_, None)
        self._providers[type_] = factory
        self._scope_metadata[type_] = scope

    def has_provider(self, type_: Any) -> bool:
        """True when this container (or its parent) holds a provider for ``type_``."""
        if type_ in self._providers:
            return True
        if self._parent is not None:
            return self._parent.has_provider(type_)
        return False

    def seed_scoped(self, type_: type, value: Any) -> None:
        """Register ``value`` as a SCOPED provider for ``type_`` on a child container.

        Explicit per-call publish — substrate adapters and pre_hooks call
        this to make a typed instance resolvable for the rest of the
        scope. Last-write-wins. Raises ``TypeError`` if called on a root
        container (SCOPED registrations there would leak across calls).
        """
        if self._parent is None:
            msg = (
                f"seed_scoped({type_!r}) requires a child container; got the root. "
                "Open one via container.child() or call this on the child inside "
                "call_scope / pre_hook."
            )
            raise TypeError(msg)
        self._providers[type_] = lambda v=value: v
        self._scope_metadata[type_] = Scope.SCOPED
        self._scoped_cache[type_] = value

    def expose_as_fastapi_depends(self, type_: type) -> Callable[[], Any]:
        """Cached FastAPI `Depends`-callable resolving ``type_`` via a2kit DI."""
        from a2kit.packages.di._fastapi_bridge import resolver_for

        return resolver_for(self, type_)

    def providers_view(self) -> dict[type, Factory]:
        """Snapshot of (parent-chain-aware) provider map."""
        merged: dict[type, Factory] = {}
        if self._parent is not None:
            merged.update(self._parent.providers_view())
        merged.update(self._providers)
        return merged

    def snapshot(self) -> Container:
        """Return a fresh unsealed Container carrying this container's registrations.

        Copies the full registration state — providers, per-type scope
        metadata, and wire scopes — into a new root container. No built
        instances, cleanup state, or the sealed flag are carried.

        ``providers_view`` alone is an incomplete snapshot: it returns
        only ``{type: factory}`` and drops scope metadata and wire
        scopes. The finisher's ``build(app)`` step uses ``snapshot`` to
        construct an ``AppRuntime``'s runtime container independently of
        the App's mutable compose-phase container, so post-build
        composition cannot reach a running runtime.
        """
        fresh = Container()
        fresh._providers = dict(self._providers)
        fresh._scope_metadata = dict(self._scope_metadata)
        fresh._wire_scopes = {name: set(types) for name, types in self._wire_scopes.items()}
        return fresh

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
            if type_ in self._root()._singletons:
                return self._root()._singletons[type_]
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
    async def call_scope(
        self,
        fn: Callable[..., Any],
        wire_kwargs: dict[str, Any] | None = None,
        *,
        pre_hook: Callable[..., Any] | None = None,
        framework_seeds: dict[type, Any] | None = None,
        scoped_seeds: dict[type, Any] | None = None,
    ) -> Any:
        """Open the per-call DI scope for one tool dispatch.

        Opens a child resolver, applies ``framework_seeds`` (explicit
        typed instances published on the child by framework-tier code —
        Principal, LddState, per-request Container), optionally calls
        ``pre_hook`` for wire-side resolution, resolves ``fn``'s
        injectable kwargs (including ``Lazy[T]`` closures), merges
        everything, yields the merged kwarg dict. On exit, unwinds the
        child's cleanup stack.

        ``pre_hook`` contract: ``(fn, wire_kwargs, seed) -> dict`` — the
        hook does wire-side conversion (e.g. ``"conn_name"`` →
        ``TrackerConn`` instance) and publishes typed instances on the
        child via ``seed(type_, value)``. May be sync or async.

        ``framework_seeds``: ``{Type: instance}`` — sourced from
        ``request_scope.all_seeds()`` by dispatch stages. App-author
        seeds continue to flow through ``pre_hook``'s ``seed: SeedFn``.

        ``scoped_seeds``: deprecation alias for ``framework_seeds``.
        Removed one release after ``generalise-context-bridges``.
        """
        seeds = framework_seeds
        if scoped_seeds is not None:
            import warnings

            warnings.warn(
                "Container.call_scope(scoped_seeds=...) is deprecated; "
                "rename to framework_seeds=. The old keyword forwards "
                "to the new one with identical semantics.",
                DeprecationWarning,
                stacklevel=2,
            )
            if seeds is None:
                seeds = scoped_seeds
        wire: dict[str, Any] = dict(wire_kwargs) if wire_kwargs else {}
        async with self.child() as child:
            if seeds:
                for type_, value in seeds.items():
                    if value is not None:
                        child.seed_scoped(type_, value)
            if pre_hook is not None:
                hook_result = pre_hook(fn, wire, child.seed_scoped)
                if inspect.isawaitable(hook_result):
                    hook_result = await hook_result
                wire = dict(hook_result) if hook_result else {}
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

        Root container: seals registration via :meth:`seal` (idempotent —
        the finisher's ``App._seal`` already sealed it).

        Child container: no-op; child enters its scope on construction.
        """
        if self._parent is None:
            self.seal()
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
            if type_ in root._singletons:
                return root._singletons[type_]
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
            lazy_inner = _lazy_inner_type(ann)
            if lazy_inner is not None:
                # Spec di-conditional-injection §1 — factory params with
                # Lazy[T] receive a deferred closure, same as tool kwargs.
                # Scope correctness for SINGLETON factories enclosing
                # Lazy[per-call-T] is enforced at app-entry by
                # ``_validate_scope_graph``.
                kwargs[spec.name] = self._make_lazy_closure(lazy_inner)
                continue
            if self.has_provider(ann) or _looks_like_basesettings(ann):
                kwargs[spec.name] = await self.get(ann)
                continue
            if spec.has_default:
                continue
            raise UnresolvableType(ann, [])
        return kwargs

    def _validate_scope_graph(self) -> None:
        """Reject app-scope factories that depend on per-call types,
        directly or via ``Lazy[per-call-T]``.

        ``_make_lazy_closure`` captures ``self`` — the container the
        factory is being resolved on. SINGLETON factories resolve on
        root, so a captured ``Lazy[per-call-T]`` closure would call
        ``root.get(per-call-T)`` later, populating ``root._scoped_cache``
        and silently breaking per-call semantics. Reject at app entry.
        """
        for type_, scope in self._scope_metadata.items():
            if scope is not Scope.SINGLETON:
                continue
            factory = self._providers.get(type_)
            if factory is None:
                continue
            for spec in self._params_for(factory):
                dep = spec.annotation

                # Direct per-call dep — original guard.
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

                # Lazy[per-call-T] dep — mirror guard.
                lazy_inner = _lazy_inner_type(dep)
                if lazy_inner is not None and self._scope_metadata.get(lazy_inner) is Scope.SCOPED:
                    inner_name = getattr(lazy_inner, "__name__", repr(lazy_inner))
                    msg = (
                        f"scope violation: app-scope captures Lazy[per-call]. "
                        f"App-scope provider for {type_!r} declares parameter "
                        f"{spec.name!r} of type `Lazy[{inner_name}]` where "
                        f"`{inner_name}` is per-call. The captured closure "
                        f"would resolve `{inner_name}` on the root container, "
                        "pinning a single instance for the app's lifetime and "
                        "breaking per-call semantics. Either move "
                        f"`{inner_name}` to app-scope (`per_call=False`), or "
                        f"make `{getattr(type_, '__name__', repr(type_))}` "
                        "per-call (`per_call=True`) so the closure captures "
                        "the per-call child container."
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
