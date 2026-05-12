"""Tests — async-factory singletons (round-5 gap 1).

The container's `register_singleton` accepts both sync and async
factories. Async factories are awaited on first `aresolve`, cached, and
returned synchronously on subsequent calls. Sync `resolve` on an
unresolved async singleton raises a precise error.
"""

from __future__ import annotations

import asyncio

import pytest

import a2kit
from a2kit.packages.di.container import Container


class _Resource:
    def __init__(self, label: str) -> None:
        self.label = label


class _DispatchStore:
    """Module-scope so `resolve_hints` can name-resolve it in router tests."""

    def __init__(self, label: str) -> None:
        self.label = label


class _DispatchRouter(a2kit.Router):
    @a2kit.read()
    async def whoami(self, store: _DispatchStore) -> dict[str, str]:
        return {"label": store.label}


def test_register_singleton_accepts_async_factory() -> None:
    """No ValueError on async-def registration."""
    container = Container()

    async def factory() -> _Resource:
        return _Resource("async")

    container.register_singleton(_Resource, factory)
    assert container.has_singleton(_Resource)
    assert container.has_async_singleton(_Resource)


def test_async_factory_awaited_once() -> None:
    container = Container()
    calls = 0

    async def factory() -> _Resource:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return _Resource("x")

    container.register_singleton(_Resource, factory)

    async def go() -> None:
        a = await container.aresolve(_Resource)
        b = await container.aresolve(_Resource)
        c = await container.aresolve(_Resource)
        assert a is b is c
        assert calls == 1

    asyncio.run(go())


def test_concurrent_first_resolution_coalesces() -> None:
    container = Container()
    calls = 0

    async def factory() -> _Resource:
        nonlocal calls
        calls += 1
        # Slow enough that 10 concurrent calls would race without the lock.
        await asyncio.sleep(0.01)
        return _Resource("c")

    container.register_singleton(_Resource, factory)

    async def go() -> None:
        results = await asyncio.gather(*(container.aresolve(_Resource) for _ in range(10)))
        first = results[0]
        assert all(r is first for r in results)
        assert calls == 1

    asyncio.run(go())


def test_distinct_async_singletons_resolve_in_parallel() -> None:
    container = Container()

    class A:
        pass

    class B:
        pass

    a_started = asyncio.Event()
    b_started = asyncio.Event()

    async def factory_a() -> A:
        a_started.set()
        await b_started.wait()  # only completes if B's factory runs concurrently
        return A()

    async def factory_b() -> B:
        b_started.set()
        await a_started.wait()
        return B()

    container.register_singleton(A, factory_a)
    container.register_singleton(B, factory_b)

    async def go() -> None:
        a, b = await asyncio.gather(container.aresolve(A), container.aresolve(B))
        assert isinstance(a, A)
        assert isinstance(b, B)

    # If the locks were container-wide, this would deadlock.
    asyncio.run(asyncio.wait_for(go(), timeout=1.0))


def test_async_factory_raises_propagates_no_cache() -> None:
    container = Container()
    attempts = 0

    async def factory() -> _Resource:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            msg = "first call fails"
            raise RuntimeError(msg)
        return _Resource("retry")

    container.register_singleton(_Resource, factory)

    async def go() -> None:
        with pytest.raises(RuntimeError, match="first call fails"):
            await container.aresolve(_Resource)
        # Cache must not retain a failure marker — second call retries.
        result = await container.aresolve(_Resource)
        assert result.label == "retry"
        assert attempts == 2

    asyncio.run(go())


def test_sync_resolve_on_unresolved_async_singleton_raises() -> None:
    container = Container()

    async def factory() -> _Resource:
        return _Resource("x")

    container.register_singleton(_Resource, factory)

    with pytest.raises(ValueError, match="async factory"):
        container.resolve(_Resource)


def test_sync_resolve_after_async_first_resolve_returns_cache() -> None:
    container = Container()

    async def factory() -> _Resource:
        return _Resource("ok")

    container.register_singleton(_Resource, factory)

    async def warm() -> _Resource:
        return await container.aresolve(_Resource)

    cached = asyncio.run(warm())
    # Now sync resolve works — the cache is populated.
    again = container.resolve(_Resource)
    assert again is cached


def test_two_apps_have_isolated_async_singletons() -> None:
    """App-scope isolation holds for async factories too."""
    app_a = a2kit.App("a")
    app_b = a2kit.App("b")

    async def make_a() -> _Resource:
        return _Resource("from-a")

    async def make_b() -> _Resource:
        return _Resource("from-b")

    app_a.singleton(_Resource, make_a)
    app_b.singleton(_Resource, make_b)

    async def go() -> tuple[_Resource, _Resource]:
        a = await app_a.container().aresolve(_Resource)
        b = await app_b.container().aresolve(_Resource)
        return a, b

    a, b = asyncio.run(go())
    assert a.label == "from-a"
    assert b.label == "from-b"
    assert a is not b


def test_has_singleton_true_after_async_registration() -> None:
    container = Container()

    async def factory() -> _Resource:
        return _Resource("y")

    container.register_singleton(_Resource, factory)
    assert container.has_singleton(_Resource)


def test_provide_still_rejects_async_factories() -> None:
    """The per-call provider path is unchanged — async there would pay
    an await tax every dispatch and isn't part of this change."""
    container = Container()

    async def factory() -> _Resource:
        return _Resource("z")

    with pytest.raises(ValueError, match="async def"):
        container.register(_Resource, factory)


def test_no_async_resource_decorator_or_lazyresource_export() -> None:
    """The framework deliberately does NOT expose `app.async_resource` or
    `LazyResource`. async-factory singletons are the only path."""
    app = a2kit.App("x")
    assert not hasattr(app, "async_resource")
    assert not hasattr(a2kit, "LazyResource")


def test_dispatch_through_async_singleton() -> None:
    """End-to-end: a router tool depending on an async-factory singleton
    resolves transparently through the dispatcher."""

    async def make_store() -> _DispatchStore:
        await asyncio.sleep(0)
        return _DispatchStore("dispatch-ok")

    app = a2kit.App("dispatch").singleton(_DispatchStore, make_store).add_router(_DispatchRouter())

    from a2kit.testing import client

    async def go() -> None:
        async with client(app) as c:
            result = await c.invoke("whoami")
            assert result == {"label": "dispatch-ok"}

    asyncio.run(go())
