"""BDD scenarios for ``resolve``.

The async sibling of :func:`a2kit.testing.peek`. Where `peek` reads
already-cached singletons from `Container._singletons`, `resolve`
runs the full DI resolution chain (build via factory, enter
resources, chain-resolve constructor params, record cleanup).

Closes a2web round-10 feedback Friction A3 — replaces consumer-
side hand-rolled `make_default_state` helpers with a single
framework-owned async seam.
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.testing import resolve


class _Inner:
    """App-scope resource with construction + lifecycle counters."""

    instances_created: int = 0
    entered: int = 0
    exited: int = 0

    def __init__(self) -> None:
        type(self).instances_created += 1

    async def __aenter__(self) -> _Inner:
        type(self).entered += 1
        return self

    async def __aexit__(self, *exc: object) -> None:
        type(self).exited += 1


class _Outer:
    """App-scope aggregate that takes _Inner as a constructor param."""

    instances_created: int = 0

    def __init__(self, inner: _Inner) -> None:
        type(self).instances_created += 1
        self.inner = inner

    async def __aenter__(self) -> _Outer:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture(autouse=True)
def _reset_counters() -> None:
    _Inner.instances_created = 0
    _Inner.entered = 0
    _Inner.exited = 0
    _Outer.instances_created = 0


@pytest.mark.asyncio
async def test_resolve_runs_di_chain_on_first_call() -> None:
    """First `resolve(app, T)` call builds T via the registered factory."""
    app = a2kit.App("test")
    app.provide(_Inner)

    async with app:
        instance = await resolve(app, _Inner)

    assert isinstance(instance, _Inner)
    assert _Inner.instances_created == 1


@pytest.mark.asyncio
async def test_resolve_enters_resource_via_aenter() -> None:
    """`__aenter__` runs exactly once on first resolve; `__aexit__`
    fires at lifespan close, not per resolve call."""
    app = a2kit.App("test")
    app.provide(_Inner)

    async with app:
        await resolve(app, _Inner)
        assert _Inner.entered == 1
        assert _Inner.exited == 0  # still in flight

    assert _Inner.exited == 1  # lifespan unwound


@pytest.mark.asyncio
async def test_resolve_returns_cached_singleton_on_second_call() -> None:
    """Two calls in the same lifespan return the same instance."""
    app = a2kit.App("test")
    app.provide(_Inner)

    async with app:
        first = await resolve(app, _Inner)
        second = await resolve(app, _Inner)

    assert first is second
    assert _Inner.entered == 1


@pytest.mark.asyncio
async def test_resolve_walks_dependency_chain() -> None:
    """`resolve(app, _Outer)` runs `_Outer`'s factory with the
    resolved `_Inner` injected; subsequent `resolve(_Inner)` returns
    the same `_Inner` instance the outer received."""
    app = a2kit.App("test")
    app.provide(_Inner)
    app.provide(_Outer)

    async with app:
        outer = await resolve(app, _Outer)
        inner_direct = await resolve(app, _Inner)

    assert isinstance(outer, _Outer)
    assert outer.inner is inner_direct
    assert _Inner.entered == 1
    assert _Outer.instances_created == 1
