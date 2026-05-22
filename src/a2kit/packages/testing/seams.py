"""DI test seams — ``lazy`` / ``peek`` / ``resolve``.

``lazy`` wraps a pre-built value as a ``Lazy[T]`` thunk; ``peek`` is the
synchronous container read for sync test bodies; ``resolve`` is its async
sibling that drives the full DI resolution chain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2kit.app import App
    from a2kit.runtime import AppRuntime

_T = TypeVar("_T")


def lazy(value: _T) -> Callable[[], Awaitable[_T]]:
    """Wrap ``value`` in a zero-arg async thunk matching ``Lazy[T]``.

    ``Lazy[T] = Callable[[], Awaitable[T]]`` (see
    :mod:`a2kit.packages.di._lazy`) is the tool-seam shape for
    deferred dependencies. In tests, you usually have a pre-built
    fake and want to inject it where a tool expects ``Lazy[T]``::

        fake_browser = make_fake_browser()
        await client.invoke("fetch", browser=a2kit.testing.lazy(fake_browser))

    The returned thunk yields the original ``value`` by identity on
    every call — no copy, no caching wrapper. Callers needing
    per-call freshness build their own thunk.
    """

    async def _thunk() -> _T:
        return value

    return _thunk


def peek(app_: App, type_: type) -> Any:
    """Test-only sync container peek over :meth:`Container.get`.

    Production code resolves via :meth:`Container.get` during dispatch.
    ``peek`` exists to give a discoverable name for the assertion pattern
    in synchronous tests::

        state = a2kit.testing.peek(app, AppState)
        assert state.config.foo == "bar"

    Driven by ``asyncio.run`` over ``Container.get`` — works from sync test
    bodies. For async tests, use :func:`resolve` (the async sibling of this
    helper).
    """
    import asyncio

    container = app_.container()
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop running — drive Container.get via asyncio.run.
        return asyncio.run(container.get(type_))
    # Inside an async test: read the app-scope cache directly. Async tests
    # should `await container.get(T)` if the instance isn't already built;
    # peek's role from inside a loop is to inspect already-resolved state
    # (the common case being post-dispatch).
    cached = container._singletons.get(type_)  # noqa: SLF001 -- test seam
    if cached is None:
        msg = (
            f"peek({type_!r}) called from inside an event loop with no cached "
            f"app-scope instance. Use `await app.container().get({type_.__name__})` "
            "in async tests instead."
        )
        raise LookupError(msg)
    return cached


async def resolve(app_: App | AppRuntime, type_: type) -> Any:
    """Async DI resolution test seam — the async sibling of :func:`peek`.

    Runs the full DI resolution chain on ``app``'s container: builds
    ``type_`` via the registered factory (chain-resolving constructor
    parameters), enters ``__aenter__`` for resources, records cleanup
    on the appropriate scope's stack. Subsequent calls return cached
    instances per the registered scope (SINGLETON across the app,
    SCOPED within one per-call child container).

    Where :func:`peek` reads already-cached singletons from
    ``Container._singletons``, ``resolve`` triggers the full
    resolution chain — useful when a test needs the resolved value
    of a type that has not been touched by any tool dispatch yet.

    Callers SHOULD invoke this inside an entered app context::

        async with a2kit.testing.client(app) as c:
            state = await a2kit.testing.resolve(app, AppState)

    Calling outside an entered app leaves resources half-entered
    with no scope to exit them — matches today's behaviour of
    ``await app.container().get(T)``.
    """
    return await app_.container().get(type_)
