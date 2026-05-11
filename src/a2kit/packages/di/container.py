"""Synchronous typed DI container — feature-agnostic.

Resolution flow per tool call::

    wire kwargs
        │
        ▼
    Container.apply_kwargs(fn, wire_kwargs)
        │
        ▼
    For each fn kwarg whose type is a registered provider:
        Container.resolve(T) walks the chain (factories' parameter
        annotations) with per-call cache.
        │
        ▼
    fn called with merged dict (wire + resolved injectables)

The container has NO feature-specific knowledge. Factories MUST be
synchronous; async resource initialization belongs in resource classes
(lazy-init pattern) or at the composition root (lifespan pattern).
Wire-input transformation (e.g. ``connection: str`` → typed config) lives
in the consumer's dispatch hook, before the container sees kwargs.
"""

from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Callable
from typing import Any, TypeVar, get_origin

T = TypeVar("T")
Factory = Callable[..., Any]


class UnresolvableType(Exception):
    """Raised when the container cannot satisfy a requested type."""

    def __init__(self, type_: Any, chain: list[Any]) -> None:
        self.type_ = type_
        self.chain = list(chain)
        super().__init__(f"cannot resolve {type_!r}; chain: {self.chain}")


class _ParamSpec:
    __slots__ = ("annotation", "has_default", "name")

    def __init__(self, name: str, annotation: Any, has_default: bool) -> None:
        self.name = name
        self.annotation = annotation
        self.has_default = has_default


def _factory_callable(factory: Factory) -> Callable[..., Any]:
    """Return the introspectable callable for a factory."""
    if inspect.isclass(factory):
        return factory.__init__
    return factory


def _factory_params(factory: Factory) -> list[_ParamSpec]:
    """List the factory's input parameters (skipping ``self``)."""
    from a2kit.signature import resolve_hints

    target = _factory_callable(factory)
    hints = resolve_hints(target)
    try:
        sig = inspect.signature(target)
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


def _is_primitive_or_external(t: Any) -> bool:
    """Return True for types that are wire-shaped (not container-injectable)."""
    if t is inspect.Parameter.empty or t is Any:
        return True
    if t in (str, int, float, bool, bytes, type(None)):
        return True
    origin = get_origin(t)
    if origin in (list, tuple, dict, set, frozenset, type, typing.Union, types.UnionType):
        return True
    if origin is typing.Literal:
        return True
    try:
        from pydantic import BaseModel

        if inspect.isclass(t) and issubclass(t, BaseModel):
            return True
    except ImportError:
        pass
    return False


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
        # Cached parameter introspection per factory (keyed by id(factory)).
        self._param_cache: dict[int, list[_ParamSpec]] = {}
        # Generic "wire-scoped string" registry. Consumer packages register
        # a scope name (e.g. ``"connection"``) and the types whose values
        # are populated from that wire string. The container holds the
        # mapping but knows nothing about specific scope semantics — those
        # live in the consumer's dispatch hook. Schema generation consults
        # this to synthesize the wire-side string param.
        self._wire_scopes: dict[str, set[type]] = {}

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

        First :meth:`resolve` call invokes the factory and caches the result;
        subsequent calls return the cached value. Factory MUST be sync.
        """
        if inspect.iscoroutinefunction(factory):
            msg = (
                f"singleton factory for {type_!r}: factory is `async def`, but "
                "singleton factories must be synchronous. Async resource opens belong "
                "inside resource classes (lazy-init pattern)."
            )
            raise ValueError(msg)
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

    # -- partition + dispatch ------------------------------------------- #

    def partition_kwargs(self, fn: Callable[..., Any]) -> tuple[set[str], set[str]]:
        """Return ``(wire_keys, injectable_keys)`` for ``fn``."""
        wire: set[str] = set()
        injectable: set[str] = set()
        for spec in _params_for_method(fn):
            if self.has(spec.annotation):
                injectable.add(spec.name)
                continue
            wire.add(spec.name)
        return wire, injectable

    def apply_kwargs(
        self,
        fn: Callable[..., Any],
        wire_kwargs: dict[str, Any],
        *,
        pre_resolved: dict[type, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve injectable kwargs for ``fn`` and merge with ``wire_kwargs``.

        Wire kwargs are passed through; injectable kwargs are resolved via
        :meth:`resolve`. Synchronous; no coroutines are awaited.

        ``pre_resolved`` is an optional ``{type → instance}`` map. Consumer
        dispatch hooks that do async work upstream (e.g. awaiting a
        connection store) seed pre-resolved instances here so the container's
        chain resolution sees them without ever calling their factories.
        """
        params = _params_for_method(fn)
        param_names = {p.name for p in params}
        cache: dict[type, Any] = dict(pre_resolved) if pre_resolved else {}
        out: dict[str, Any] = {}
        for spec in params:
            if spec.name in wire_kwargs:
                out[spec.name] = wire_kwargs[spec.name]
                continue
            if self.has(spec.annotation):
                out[spec.name] = self.resolve(spec.annotation, cache=cache)
                continue
            # Wire kwarg with no value supplied → omit; caller diagnoses.
        for k, v in wire_kwargs.items():
            if k in param_names and k not in out:
                out[k] = v
        return out

    # -- internal ------------------------------------------------------- #

    def _params_for(self, factory: Factory) -> list[_ParamSpec]:
        key = id(factory)
        cached = self._param_cache.get(key)
        if cached is not None:
            return cached
        params = _factory_params(factory)
        self._param_cache[key] = params
        return params


class _Unresolved:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<UNRESOLVED>"


_UNRESOLVED: Any = _Unresolved()


def _params_for_method(fn: Callable[..., Any]) -> list[_ParamSpec]:
    """Method-aware variant of :func:`_factory_params` (skips ``self``)."""
    from a2kit.signature import resolve_hints

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


def container_dispatch(
    fn: Callable[..., Any],
    wire_kwargs: dict[str, Any],
    container: Container,
) -> dict[str, Any]:
    """Resolve a tool method's kwargs through ``container`` (sync).

    The default dispatch hook for apps with at least one registered provider.
    Connection-aware apps install a different hook (in
    ``a2kit.packages.connections.dispatch``) that runs an async pre-step
    before delegating to this function.
    """
    return container.apply_kwargs(fn, wire_kwargs)


__all__ = [
    "Container",
    "Factory",
    "UnresolvableType",
    "container_dispatch",
]
