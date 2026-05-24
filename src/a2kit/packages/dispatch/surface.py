"""``Surface`` Protocol + ``DecoratorSurface[R]`` template + ``SurfaceRegistry``.

The framework's extension point for substrate adapters. Every substrate
(MCP, HTTP, future A2A/gRPC/GraphQL) satisfies the ``Surface`` Protocol
and self-registers with the module-level ``SURFACE_REGISTRY`` from its
package's lazy front-door load.

This module sits at L4 (dispatch) and MUST NOT import any substrate
library (fastapi, fastmcp, etc.). Cold-start preserved.

The split-out from the bespoke ``McpSurface``/``ApiSurface`` classes
landed in `add-surface-protocol-additive`. The sibling
`remove-substrate-literal` change retires ``Substrate = Literal[...]``
and wires ``split_signature``/``install_substrate_signature`` to consume
``Surface`` attributes directly.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable

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

    def bind(self, runtime: Any, descriptors: Any) -> Any: ...

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

    def get(self, name: str) -> Surface:
        return self._by_name[name]

    def names(self) -> tuple[str, ...]:
        return tuple(self._by_name.keys())

    def __iter__(self) -> Iterable[Surface]:
        return iter(self._by_name.values())

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._by_name


SURFACE_REGISTRY = SurfaceRegistry()


__all__ = [
    "SURFACE_REGISTRY",
    "DecoratorSurface",
    "Surface",
    "SurfaceRegistry",
]
