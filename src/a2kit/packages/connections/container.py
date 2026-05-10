"""Request-scoped DI container — typed providers, parameter-annotation chaining.

The container lives in ``packages/connections`` because connection-rooted
DI is its concrete use case. Core ``a2kit/*.py`` knows nothing about it;
the dispatch hook protocol in ``a2kit.tool`` is the only seam.

Resolution flow per tool call::

    wire kwargs (incl. connection: str)
        │
        ▼
    Container.apply_kwargs(fn, wire_kwargs, ...)
        │
        ▼
    For each fn kwarg whose type is a registered provider:
        Container.resolve(T, connection=...) walks the chain
        (factories' parameter annotations) with per-call cache.
        │
        ▼
    fn called with merged dict (wire + resolved injectables);
    the wire-only ``connection: str`` is stripped if fn has no
    ``connection`` parameter of its own.

The ``ConnectionConfig`` provider is the *only* one permitted to take a
``connection: str`` parameter; lint rule ``A2K-DI-CHAIN`` enforces.
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


class SyncResolveUnavailable(Exception):
    """Raised by :meth:`Container.resolve_sync` when an async factory is in the chain.

    ``async_link`` names the type whose factory is async (or whose singleton has
    not yet been resolved and is async-backed). Callers should switch to
    ``await container.resolve(T)`` for the offending chain.
    """

    def __init__(self, type_: Any, async_link: Any) -> None:
        self.type_ = type_
        self.async_link = async_link
        super().__init__(
            f"cannot resolve {type_!r} synchronously: {async_link!r} requires async factory; use `await container.resolve(...)` instead"
        )


class _ParamSpec:
    __slots__ = ("annotation", "has_default", "name")

    def __init__(self, name: str, annotation: Any, has_default: bool) -> None:
        self.name = name
        self.annotation = annotation
        self.has_default = has_default


def _factory_callable(factory: Factory) -> Callable[..., Any]:
    """Return the introspectable callable for a factory.

    For a class, that's its ``__init__``; for a singleton wrapper, the underlying
    user factory (so signature introspection sees the user's parameters, not
    ``__call__``'s ``*args, **kwargs``); for a callable, the callable itself.
    """
    if getattr(factory, "_is_a2kit_singleton", False):
        user = factory.user_factory  # ty: ignore[unresolved-attribute]
        return user.__init__ if inspect.isclass(user) else user
    if inspect.isclass(factory):
        return factory.__init__
    return factory


def _factory_params(factory: Factory) -> list[_ParamSpec]:
    """List the factory's input parameters (skipping ``self``)."""
    from a2kit.signature import resolve_hints

    target = _factory_callable(factory)
    hints = resolve_hints(target)
    sig = inspect.signature(target)
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
    # Pydantic BaseModel and subclasses are wire-shaped (serializable input).
    try:
        from pydantic import BaseModel

        if inspect.isclass(t) and issubclass(t, BaseModel):
            return True
    except ImportError:
        pass
    return False


class Container:
    """Per-app provider registry. Construct one ``Container`` per ``App``.

    Resolution is per-call: pass a fresh cache dict to :meth:`resolve` each
    time so two kwargs of the same type share *one* instance within a call
    but never across calls.
    """

    def __init__(self) -> None:
        self._providers: dict[type, Factory] = {}
        # Cached parameter introspection per factory (keyed by id(factory)).
        self._param_cache: dict[int, list[_ParamSpec]] = {}
        # Always-provided types (filled by core during boot).
        self._allowlist: dict[type, Callable[[], Any]] = {}

    # -- registration --------------------------------------------------- #

    def register(self, type_: type, factory: Factory | None = None) -> None:
        """Register ``factory`` (or ``type_`` itself) as the provider for ``type_``.

        When ``factory`` is None, the class itself becomes the factory and
        the container will introspect ``type_.__init__`` at resolve time.
        Class providers must have annotated constructor parameters; lambdas
        with a single ``connection`` parameter are accepted unannotated
        (treated as ``connection: str``).
        """
        if factory is None:
            factory = type_
        if inspect.isclass(factory):
            # Strict check for class-as-factory — class authors should be typed.
            for spec in _factory_params(factory):
                if not spec.has_default and spec.annotation is inspect.Parameter.empty:
                    msg = f"provider for {type_!r}: parameter {spec.name!r} lacks an annotation"
                    raise ValueError(msg)
        self._providers[type_] = factory

    def has(self, type_: Any) -> bool:
        return type_ in self._providers

    def has_allowlisted(self, type_: Any) -> bool:
        return type_ in self._allowlist

    def allowlist(self, type_: type, factory: Callable[[], Any]) -> None:
        """Mark ``type_`` as always-provided by core (e.g., ``ToolContext``)."""
        self._allowlist[type_] = factory

    def providers(self) -> dict[type, Factory]:
        return dict(self._providers)

    # -- resolution ----------------------------------------------------- #

    async def resolve(
        self,
        type_: type,
        *,
        connection: str | None = None,
        cache: dict[type, Any] | None = None,
        chain: list[type] | None = None,
    ) -> Any:
        if cache is None:
            cache = {}
        if chain is None:
            chain = []
        if type_ in cache:
            return cache[type_]
        if type_ in chain:
            msg = f"provider cycle: {[*chain, type_]}"
            raise ValueError(msg)
        factory = self._providers.get(type_)
        if factory is None:
            raise UnresolvableType(type_, [*chain])

        new_chain = [*chain, type_]
        kwargs = await self._resolve_factory_kwargs(factory, connection, cache, new_chain)

        result = factory(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        cache[type_] = result
        return result

    def resolve_sync(
        self,
        type_: type,
        *,
        connection: str | None = None,
        cache: dict[type, Any] | None = None,
        chain: list[type] | None = None,
    ) -> Any:
        """Synchronously resolve ``type_`` if every factory in the reachable chain is sync.

        Raises :class:`SyncResolveUnavailable` if any factory in the chain is async
        (or if a singleton wrapper backs an unresolved async user-factory). Singleton
        types whose value has already been cached short-circuit as sync regardless of
        the original factory's async-ness.
        """
        if cache is None:
            cache = {}
        if chain is None:
            chain = []
        if type_ in cache:
            return cache[type_]
        if type_ in chain:
            msg = f"provider cycle: {[*chain, type_]}"
            raise ValueError(msg)
        factory = self._providers.get(type_)
        if factory is None:
            raise UnresolvableType(type_, [*chain])

        # Singleton fast-path: cached value is sync regardless of original factory.
        sw = _as_singleton_wrapper(factory)
        if sw is not None and sw.is_resolved():
            cached = sw.get_cached()
            cache[type_] = cached
            return cached

        # Reject async factories upfront with a clear offender.
        async_link = self._is_sync_chain(type_)
        if async_link is not None:
            raise SyncResolveUnavailable(type_, async_link=async_link)

        new_chain = [*chain, type_]
        kwargs = self._resolve_factory_kwargs_sync(factory, connection, cache, new_chain)
        result = factory(**kwargs)
        # Defensive: a sync chain should never produce an awaitable, but guard anyway.
        if inspect.isawaitable(result):
            raise SyncResolveUnavailable(type_, async_link=type_)
        cache[type_] = result
        return result

    def _is_sync_chain(
        self,
        type_: type,
        seen: set[type] | None = None,
    ) -> Any:
        """Walk the provider graph; return the first async link or ``None`` if all sync.

        Singleton-cached values short-circuit as sync. Singleton wrappers backing
        an async user-factory return ``type_`` as the offending link only if the
        cached value is not yet present.
        """
        if seen is None:
            seen = set()
        if type_ in seen or self._providers.get(type_) is None:
            return None
        seen.add(type_)
        factory = self._providers[type_]
        if self._factory_is_async(factory):
            return type_
        return self._first_async_dep(factory, seen)

    @staticmethod
    def _factory_is_async(factory: Factory) -> bool:
        sw = _as_singleton_wrapper(factory)
        if sw is not None:
            return not sw.is_resolved() and sw.is_async
        return inspect.iscoroutinefunction(factory)

    def _first_async_dep(self, factory: Factory, seen: set[type]) -> Any:
        # Singleton wrappers backing already-resolved values short-circuit.
        sw = _as_singleton_wrapper(factory)
        if sw is not None and sw.is_resolved():
            return None
        for spec in self._params_for(factory):
            if not self.has(spec.annotation):
                continue
            bad = self._is_sync_chain(spec.annotation, seen)
            if bad is not None:
                return bad
        return None

    def _resolve_factory_kwargs_sync(
        self,
        factory: Factory,
        connection: str | None,
        cache: dict[type, Any],
        new_chain: list[type],
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        for spec in self._params_for(factory):
            if spec.name == "connection" and (spec.annotation is str or spec.annotation is inspect.Parameter.empty):
                if connection is None:
                    raise UnresolvableType(str, new_chain)
                kwargs["connection"] = connection
                continue
            if self.has(spec.annotation):
                kwargs[spec.name] = self.resolve_sync(
                    spec.annotation,
                    connection=connection,
                    cache=cache,
                    chain=new_chain,
                )
                continue
            if spec.has_default:
                continue
            raise UnresolvableType(spec.annotation, new_chain)
        return kwargs

    async def _resolve_factory_kwargs(
        self,
        factory: Factory,
        connection: str | None,
        cache: dict[type, Any],
        new_chain: list[type],
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        for spec in self._params_for(factory):
            if spec.name == "connection" and (spec.annotation is str or spec.annotation is inspect.Parameter.empty):
                if connection is None:
                    raise UnresolvableType(str, new_chain)
                kwargs["connection"] = connection
                continue
            if self.has(spec.annotation):
                kwargs[spec.name] = await self.resolve(
                    spec.annotation,
                    connection=connection,
                    cache=cache,
                    chain=new_chain,
                )
                continue
            if spec.has_default:
                continue
            raise UnresolvableType(spec.annotation, new_chain)
        return kwargs

    # -- partition + dispatch ------------------------------------------- #

    def partition_kwargs(self, fn: Callable[..., Any]) -> tuple[set[str], set[str], bool]:
        """Return ``(wire_keys, injectable_keys, needs_connection)`` for ``fn``.

        ``needs_connection`` is True when at least one injectable's chain
        reaches a ``connection: str`` parameter — that signal lets schema
        gen auto-add ``connection`` to the wire input.
        """
        wire: set[str] = set()
        injectable: set[str] = set()
        needs_conn = False
        for spec in _params_for_method(fn):
            if spec.name in self._allowlist_names():
                continue
            ann = spec.annotation
            # Allowlisted types (ToolContext, App) — always provided.
            if ann in self._allowlist:
                continue
            if self.has(ann):
                injectable.add(spec.name)
                if self._chain_reaches_connection(ann):
                    needs_conn = True
                continue
            wire.add(spec.name)
        return wire, injectable, needs_conn

    def _allowlist_names(self) -> set[str]:
        # Reserved kwarg names handled by core (currently empty — allowlist
        # is keyed by type, not name).
        return set()

    def _chain_reaches_connection(
        self,
        type_: type,
        seen: set[type] | None = None,
    ) -> bool:
        if seen is None:
            seen = set()
        if type_ in seen:
            return False
        seen.add(type_)
        factory = self._providers.get(type_)
        if factory is None:
            return False
        for spec in self._params_for(factory):
            if spec.name == "connection" and (spec.annotation is str or spec.annotation is inspect.Parameter.empty):
                return True
            if self.has(spec.annotation) and self._chain_reaches_connection(spec.annotation, seen):
                return True
        return False

    async def apply_kwargs(
        self,
        fn: Callable[..., Any],
        wire_kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve injectable kwargs for ``fn`` and merge with ``wire_kwargs``.

        Wire kwargs are passed through; injectable kwargs are resolved via
        :meth:`resolve`; allowlisted kwargs are filled by core (the caller
        passes those through ``wire_kwargs`` for now). Stripping of any
        wire ``connection: str`` that the tool method does not declare is
        done here so the tool gets a clean kwargs dict.
        """
        params = _params_for_method(fn)
        param_names = {p.name for p in params}
        connection = wire_kwargs.get("connection") if "connection" in wire_kwargs else None
        cache: dict[type, Any] = {}
        out: dict[str, Any] = {}
        for spec in params:
            if spec.name in wire_kwargs:
                out[spec.name] = wire_kwargs[spec.name]
                continue
            if spec.annotation in self._allowlist:
                # Allowlisted types are filled by the dispatch caller (e.g.,
                # ToolContext is built by runtime). Skip — caller injects.
                continue
            if self.has(spec.annotation):
                out[spec.name] = await self.resolve(
                    spec.annotation,
                    connection=connection if isinstance(connection, str) else None,
                    cache=cache,
                )
                continue
            # Wire kwarg with no value supplied → omit; caller / Click /
            # MCP layer is responsible for missing-required diagnostics.
        # Pass through extras the caller wants (e.g., context kwargs the
        # runtime set on the dict directly).
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


# ---- Dispatch hook helpers -------------------------------------------- #


async def container_dispatch(
    fn: Callable[..., Any],
    wire_kwargs: dict[str, Any],
    container: Container,
) -> dict[str, Any]:
    """Resolve a tool method's kwargs through ``container``.

    Used by :class:`a2kit.app.App` when at least one provider is registered.
    """
    return await container.apply_kwargs(fn, wire_kwargs)


def install_connection_providers(container: Container, conn_types: tuple[type, ...]) -> None:
    """Register a typed provider per ``ConnectionConfig`` subclass on ``container``.

    Idempotent: providers already present are left alone (manual ``provide``
    wins). Each factory takes a wire ``connection: str`` parameter and resolves
    via the connection store. Lives in this package so core ``a2kit/app.py``
    stays free of feature-name references.
    """
    from a2kit.packages.connections.store import ConnectionStore

    for ct in conn_types:
        if container.has(ct):
            continue
        store: Any = ConnectionStore(ct)  # ty: ignore[invalid-argument-type]

        def _make_factory(_store: Any = store) -> Callable[..., Any]:
            async def _factory(connection: str) -> Any:
                parts = tuple(p.strip() for p in connection.split(",")) if "," in connection else (connection,)
                if len(parts) == 1:
                    return await _store.load(parts[0])
                return await _store.load(*parts)

            return _factory

        container.register(ct, _make_factory())


def _as_singleton_wrapper(factory: Any) -> Any:
    """Return ``factory`` if it is a singleton wrapper marker, else ``None``.

    The singleton wrapper carries ``_is_a2kit_singleton = True`` so the container
    can special-case sync-resolve and chain analysis without importing ``app``.
    """
    if getattr(factory, "_is_a2kit_singleton", False):
        return factory
    return None


__all__ = [
    "Container",
    "Factory",
    "SyncResolveUnavailable",
    "UnresolvableType",
    "container_dispatch",
    "install_connection_providers",
]
