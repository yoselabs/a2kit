"""``Resolver`` protocol — the framework-facing seam over the DI container.

Framework modules (dispatcher, App, TestClient) MUST reference this
protocol, never the concrete ``Container``. The protocol surface is
intentionally minimal: ``get``, ``provide``, ``child``, ``aclose``.

The concrete :class:`a2kit.packages.di.Container` implements it; future
extraction to a standalone PyPI package only needs to keep the protocol
shape stable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.packages.di.scope import Scope


T = TypeVar("T")


@runtime_checkable
class Resolver(Protocol):
    """Minimal framework-facing surface of a DI container.

    All resolution is async — the dispatcher already runs in an event
    loop, and async factories / ``__aenter__`` lifecycle make a sync
    path actively misleading. See ``design.md`` D7.
    """

    async def get(self, type_: type[T]) -> T:
        """Resolve ``type_`` honoring its registered scope; await any async work."""
        ...

    def provide(
        self,
        type_: type[T],
        factory: Callable[..., Any] | None = None,
        *,
        scope: Scope = ...,  # type: ignore[assignment]
    ) -> None:
        """Register a provider for ``t``. Last-write-wins overrides prior providers."""
        ...

    def child(self) -> Resolver:
        """Open a per-call child resolver sharing this resolver's providers."""
        ...

    async def aclose(self) -> None:
        """Unwind this resolver's cleanup stack in LIFO order."""
        ...


__all__ = ["Resolver"]
