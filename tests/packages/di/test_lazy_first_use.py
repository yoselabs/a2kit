"""BDD: lazy first-use resolution for app-scope resources.

Covers spec ``app-lifecycle`` (no eager entry at ``__aenter__``) and
``app-singletons`` (first-dispatch warm-up + lock-coalesce). Implementation
arrives in §2-§3 of the di-scoped-lifecycle task list; until then these tests
fail naturally (the ``App.provide`` API does not yet exist).
"""

from __future__ import annotations

import asyncio

import pytest

import a2kit


class _BrowserPool:
    enter_count: int = 0
    exit_count: int = 0

    def __init__(self) -> None:
        pass

    async def __aenter__(self) -> _BrowserPool:
        type(self).enter_count += 1
        return self

    async def __aexit__(self, *exc: object) -> None:
        type(self).exit_count += 1


class _SqliteResource:
    enter_count: int = 0
    exit_count: int = 0

    async def __aenter__(self) -> _SqliteResource:
        type(self).enter_count += 1
        return self

    async def __aexit__(self, *exc: object) -> None:
        type(self).exit_count += 1


@pytest.fixture(autouse=True)
def _reset_counters() -> None:
    _BrowserPool.enter_count = 0
    _BrowserPool.exit_count = 0
    _SqliteResource.enter_count = 0
    _SqliteResource.exit_count = 0


@pytest.mark.asyncio
async def test_app_scope_resource_not_entered_at_aenter() -> None:
    """Spec: ``async with app`` does not enter resources eagerly.

    An app-scope registration MUST NOT trigger ``__aenter__`` on the resource
    when the App enters. Only a tool dispatch that resolves the resource
    triggers entry. This is the core lazy-first-use contract from
    ``app-lifecycle``.
    """
    app = a2kit.App("test")
    app.provide(_BrowserPool)
    app.provide(_SqliteResource)

    async with app:
        # Lifespan body runs without dispatching any tool that needs them.
        pass

    assert _BrowserPool.enter_count == 0, "BrowserPool entered eagerly"
    assert _SqliteResource.enter_count == 0, "SqliteResource entered eagerly"
    assert _BrowserPool.exit_count == 0
    assert _SqliteResource.exit_count == 0


@pytest.mark.asyncio
async def test_first_dispatch_warms_resource_once() -> None:
    """Spec: first dispatch warms the resource; subsequent dispatches reuse.

    First resolution invokes ``__aenter__`` exactly once and caches the
    instance. Second resolution returns the cached instance without
    re-entering. App close runs ``__aexit__`` exactly once.
    """
    app = a2kit.App("test")
    app.provide(_BrowserPool)

    async with app:
        first = await app._resolver.get(_BrowserPool)
        second = await app._resolver.get(_BrowserPool)

        assert first is second, "cached instance not reused across resolves"
        assert _BrowserPool.enter_count == 1, f"expected one __aenter__, got {_BrowserPool.enter_count}"

    assert _BrowserPool.exit_count == 1, f"expected one __aexit__ on app close, got {_BrowserPool.exit_count}"


@pytest.mark.asyncio
async def test_concurrent_first_touches_coalesce() -> None:
    """Spec: concurrent first-touches coalesce under per-type lock.

    Ten concurrent tasks each trigger first-resolution of the same app-scope
    type. The factory MUST be awaited exactly once; all tasks share the same
    resolved instance.
    """
    enter_started = asyncio.Event()
    release_enter = asyncio.Event()

    class _SlowResource:
        instances_created: int = 0

        def __init__(self) -> None:
            type(self).instances_created += 1

        async def __aenter__(self) -> _SlowResource:
            enter_started.set()
            await release_enter.wait()
            return self

        async def __aexit__(self, *exc: object) -> None:
            pass

    app = a2kit.App("test")
    app.provide(_SlowResource)

    async with app:
        # Spawn ten concurrent resolutions.
        tasks = [asyncio.create_task(app._resolver.get(_SlowResource)) for _ in range(10)]
        # Wait until __aenter__ is in flight, then release.
        await enter_started.wait()
        release_enter.set()

        results = await asyncio.gather(*tasks)

        # All ten tasks share the same instance.
        first = results[0]
        for r in results[1:]:
            assert r is first, "concurrent first-resolves returned distinct instances"

        # Construction + __aenter__ ran exactly once.
        assert _SlowResource.instances_created == 1, f"factory invoked {_SlowResource.instances_created} times under concurrent load"
