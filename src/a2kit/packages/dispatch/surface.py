"""``Surface`` Protocol + ``DecoratorSurface[R]`` template + ``SurfaceRegistry``.

The framework's extension point for substrate adapters. Every substrate
(MCP, HTTP, future A2A/gRPC/GraphQL) satisfies the ``Surface`` Protocol.
Surfaces are PASSIVE — importing a surface module does NOT mutate any
registry. The registry is composed explicitly at ``runtime.build()``
time from its ``surfaces=`` tuple, per the ``bootstrap-surfaces-explicit``
change.

The module-level ``SURFACE_REGISTRY`` is a deprecation shim proxy that
routes to the active runtime's registry (``runtime.surfaces``) when one
is bound, and raises a clear ``RuntimeError`` otherwise. Direct
``SURFACE_REGISTRY.register_surface(...)`` calls emit
``DeprecationWarning`` pointing at the explicit-composition pattern.

This module sits at L4 (dispatch) and MUST NOT import any substrate
library (fastapi, fastmcp, etc.). Cold-start preserved.
"""

from __future__ import annotations

import warnings
from collections import OrderedDict
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Protocol, TypeVar, runtime_checkable

from a2kit._surface_names import register_surface_name

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextvars import Token

R = TypeVar("R")


@runtime_checkable
class Surface(Protocol):
    """Contract for a substrate adapter.

    Implementations declare their substrate-reserved types and
    substrate-dep markers as ClassVars so the dispatch-layer
    signature splitter can consume them uniformly without
    string discrimination.

    - ``name``: stable identifier used as the mount path
      (``/api``, ``/mcp``, ``/<name>`` for future substrates) and
      as the value authors pass to ``expose=``.
    - ``reserved_types``: substrate-native types the substrate fills
      itself (FastAPI: ``Request``/``Response``/``BackgroundTasks``/
      ``WebSocket``; FastMCP: ``Context``). The dispatch signature
      splitter passes these through to the substrate-facing wrapper.
    - ``substrate_dep_markers``: marker classes that, when found as
      ``Annotated[T, marker]`` metadata, signal the substrate owns the
      resolution path (FastAPI: ``Depends``/``Security``; FastMCP:
      empty for now).
    - ``bind(runtime, descriptors)``: build the substrate-native app
      (``FastAPI`` / ``FastMCP``) from the runtime + tool descriptors.
    - ``install_di_bridge(runtime, substrate_app)``: wire the
      substrate-native DI bridge into the built app. Called by
      ``bind`` post-construction.
    """

    name: ClassVar[str]
    reserved_types: ClassVar[frozenset[type]]
    substrate_dep_markers: ClassVar[frozenset[type]]

    def bind(self, runtime: Any, descriptors: Any = None) -> Any: ...

    def install_di_bridge(self, runtime: Any, substrate_app: Any) -> None: ...


class DecoratorSurface(Generic[R]):
    """Template for surfaces that accumulate decorator registrations.

    Subclasses bind the concrete registration dataclass type via the
    generic parameter ``R`` and use ``_record(r)`` to append. The
    accumulator lives here so subclasses don't redeclare ``registrations``
    and so future cross-surface concerns (e.g. iteration helpers, count
    summaries) live in one place.

    Subclasses still own their per-verb decorator shape (e.g. ``McpSurface``
    has ``tool``/``prompt``/``resource``; ``ApiSurface`` has
    ``get``/``post``/...) because those signatures diverge — the verb
    shape is not what's shared, the accumulator is.
    """

    # Concrete subclasses populate this on construction. Kept as a list
    # internally so `_record` is O(1); `registrations` returns a tuple
    # view to discourage external mutation.
    _registrations: list[R]

    def __init__(self) -> None:
        self._registrations = []

    @property
    def registrations(self) -> tuple[R, ...]:
        return tuple(self._registrations)

    def _record(self, registration: R) -> None:
        self._registrations.append(registration)


class SurfaceRegistry:
    """Ordered registry of ``Surface`` instances keyed by ``surface.name``.

    Insertion order is preserved (relied on by ``build_parent_app`` in
    the sibling ``remove-substrate-literal`` change). Duplicate names
    are rejected — two surfaces sharing a name would collide on the
    mount path and on ``expose=`` validation.
    """

    def __init__(self) -> None:
        self._by_name: OrderedDict[str, Surface] = OrderedDict()

    def register_surface(self, surface: Surface) -> None:
        name = surface.name
        if name in self._by_name:
            msg = f"surface name {name!r} already registered with {type(self._by_name[name]).__name__}"
            raise ValueError(msg)
        self._by_name[name] = surface
        register_surface_name(name)

    def get(self, name: str) -> Surface:
        return self._by_name[name]

    def names(self) -> tuple[str, ...]:
        return tuple(self._by_name.keys())

    def __iter__(self) -> Iterator[Surface]:
        return iter(self._by_name.values())

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._by_name


# --- Active-registry binding -------------------------------------------------
#
# `runtime.build()` creates a per-runtime `SurfaceRegistry` and binds it as
# the active registry for the process via `bind_active_registry`. The legacy
# `SURFACE_REGISTRY` proxy below routes its reads/writes through whatever's
# bound. The binding is process-global (not async-scoped) because a2kit's
# typical deployment runs one `AppRuntime` per process; if multi-tenant
# parallel runtimes ever become a real case, swap to a ContextVar with
# `.set()`/`.reset()` discipline at the build boundary.

_ACTIVE_REGISTRY: ContextVar[SurfaceRegistry | None] = ContextVar("a2kit_active_surface_registry", default=None)


def current_registry() -> SurfaceRegistry | None:
    """Return the active `SurfaceRegistry` if `runtime.build()` has bound one."""
    return _ACTIVE_REGISTRY.get()


def bind_active_registry(registry: SurfaceRegistry) -> Token[SurfaceRegistry | None]:
    """Bind `registry` as the active registry. Returns a token for resetting."""
    return _ACTIVE_REGISTRY.set(registry)


def reset_active_registry(token: Token[SurfaceRegistry | None]) -> None:
    """Reset the active-registry binding."""
    _ACTIVE_REGISTRY.reset(token)


class _SurfaceRegistryProxy:
    """Deprecation shim — the module-level `SURFACE_REGISTRY` of yore.

    Routes every operation to the active runtime's registry (bound by
    `runtime.build()`). Raises `RuntimeError` when accessed before any
    runtime is built — that's the new contract: registry reads need a
    runtime in scope. Direct `register_surface(...)` emits
    `DeprecationWarning` pointing at the `surfaces=` parameter.
    """

    def _active(self) -> SurfaceRegistry:
        reg = _ACTIVE_REGISTRY.get()
        if reg is None:
            msg = (
                "SURFACE_REGISTRY accessed before any AppRuntime was built. "
                "Build a runtime via `a2kit.runtime.build(app, surfaces=(...))` first, "
                "or read from `runtime.surfaces` directly."
            )
            raise RuntimeError(msg)
        return reg

    def register_surface(self, surface: Surface) -> None:
        warnings.warn(
            "SURFACE_REGISTRY.register_surface(...) is deprecated; pass surfaces via `runtime.build(app, surfaces=(...))` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._active().register_surface(surface)

    def get(self, name: str) -> Surface:
        return self._active().get(name)

    def names(self) -> tuple[str, ...]:
        return self._active().names()

    def __iter__(self) -> Iterator[Surface]:
        return iter(self._active())

    def __contains__(self, name: object) -> bool:
        return name in self._active()


SURFACE_REGISTRY = _SurfaceRegistryProxy()


__all__ = [
    "SURFACE_REGISTRY",
    "DecoratorSurface",
    "Surface",
    "SurfaceRegistry",
    "bind_active_registry",
    "current_registry",
    "reset_active_registry",
]
