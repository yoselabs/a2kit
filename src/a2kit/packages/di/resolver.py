"""``Resolver`` protocol — the framework-facing seam over the DI container.

Framework modules (dispatcher, App, TestClient) MUST reference this
protocol, never the concrete ``Container``. The protocol surface covers
the full v0.38 framework-facing seam: registration (``provide``),
resolution (``get`` / ``resolve_params``), per-call dispatch
(``dispatch`` async-CM), child opening (``child``), lifecycle
(``__aenter__`` / ``__aexit__`` / ``aclose``).

The concrete :class:`a2kit.packages.di.Container` implements it; future
extraction to a standalone PyPI package only needs to keep the protocol
shape stable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

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

    async def resolve_params(self, fn: Callable[..., Any]) -> dict[str, Any]:
        """Resolve ``fn``'s parameter kwargs, honoring ``Lazy[T]``."""
        ...

    def call_scope(
        self,
        fn: Callable[..., Any],
        wire_kwargs: dict[str, Any] | None = None,
        *,
        pre_hook: Callable[..., Any] | None = None,
        framework_seeds: dict[type, Any] | None = None,
    ) -> AbstractAsyncContextManager[dict[str, Any]]:
        """Open the per-call DI scope (async context manager).

        Returns an async-CM whose ``__aenter__`` yields the merged kwarg
        dict and whose ``__aexit__`` unwinds the per-call cleanup stack.

        ``framework_seeds`` publishes typed instances on the child as
        SCOPED providers before resolution — sourced from
        ``request_scope.all_seeds()`` by dispatch stages.
        """
        ...

    def child(self) -> Resolver:
        """Open a per-call child resolver sharing this resolver's providers."""
        ...

    async def aclose(self) -> None:
        """Unwind this resolver's cleanup stack in LIFO order."""
        ...

    async def __aenter__(self) -> Resolver:
        """Enter the resolver's lifecycle scope (root: seal + validate)."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        """Exit the resolver's lifecycle scope, unwinding cleanups."""
        ...


__all__ = ["Resolver"]
