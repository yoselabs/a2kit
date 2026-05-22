"""BDD: ``Lazy[T]`` honored as a factory parameter, not just a tool kwarg.

Covers the spec drift between ``di-conditional-injection`` (which
already promises both tool AND factory recognition) and the
implementation (which only honors tool dispatch).

Closes a2web round-10 Friction E by enabling aggregate
``AppState``-like factories to carry deferred handles for
heavy/conditional resources without polluting every tool signature
with three injectables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

import a2kit
from a2kit.runtime import build
from a2kit.packages.di import Lazy


class _Inner:
    """App-scope resource with enter/exit counters."""

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


class _PerCallThing:
    """Per-call resource — fresh per dispatch."""

    instances_created: int = 0

    def __init__(self) -> None:
        type(self).instances_created += 1


@dataclass(slots=True)
class _Outer:
    """Aggregate carrying a Lazy[_Inner] handle, built by a factory."""

    inner_lazy: Any  # Lazy[_Inner] at runtime; Any annotation keeps the dataclass simple


@dataclass(slots=True)
class _OuterWithPerCall:
    """Aggregate trying to carry Lazy[per-call]; should be rejected."""

    pc_lazy: Any


@dataclass(slots=True)
class _PerCallAggregate:
    """Per-call aggregate with a Lazy[T] handle."""

    inner_lazy: Any


@pytest.fixture(autouse=True)
def _reset_counters() -> None:
    _Inner.instances_created = 0
    _Inner.entered = 0
    _Inner.exited = 0
    _PerCallThing.instances_created = 0


@pytest.mark.asyncio
async def test_singleton_factory_with_lazy_app_scope_t_works() -> None:
    """A SINGLETON factory declaring ``Lazy[_Inner]`` (Inner is also
    app-scope) receives a callable; awaiting it from a tool body
    resolves _Inner exactly once and caches it."""
    app = a2kit.App("test")
    app.provide(_Inner)

    def make_outer(inner_lazy: Lazy[_Inner]) -> _Outer:
        return _Outer(inner_lazy=inner_lazy)

    app.provide(_Outer, make_outer)

    async def tool_body(outer: _Outer) -> _Inner:
        return await outer.inner_lazy()

    async with build(app) as app, app._resolver.child() as call:
        kwargs = await call.resolve_params(tool_body)
        instance = await tool_body(**kwargs)

    assert isinstance(instance, _Inner)
    assert _Inner.instances_created == 1
    assert _Inner.entered == 1


@pytest.mark.asyncio
async def test_singleton_factory_lazy_handle_never_awaited() -> None:
    """If no tool body ever awaits the captured Lazy handle, _Inner's
    factory / __aenter__ never run."""
    app = a2kit.App("test")
    app.provide(_Inner)

    def make_outer(inner_lazy: Lazy[_Inner]) -> _Outer:
        return _Outer(inner_lazy=inner_lazy)

    app.provide(_Outer, make_outer)

    async def tool_body(outer: _Outer) -> str:
        # Never calls outer.inner_lazy().
        return "done"

    async with build(app) as app, app._resolver.child() as call:
        kwargs = await call.resolve_params(tool_body)
        await tool_body(**kwargs)

    assert _Inner.instances_created == 0
    assert _Inner.entered == 0


@pytest.mark.asyncio
async def test_singleton_factory_lazy_handle_cached_across_dispatches() -> None:
    """Awaiting the Lazy handle from two separate dispatches returns
    the same _Inner instance (app-scope cache hit on the second
    dispatch). The closure was captured during _Outer's construction
    on root, so subsequent awaits resolve through root.get(_Inner).
    """
    app = a2kit.App("test")
    app.provide(_Inner)

    def make_outer(inner_lazy: Lazy[_Inner]) -> _Outer:
        return _Outer(inner_lazy=inner_lazy)

    app.provide(_Outer, make_outer)

    async def tool_body(outer: _Outer) -> _Inner:
        return await outer.inner_lazy()

    async with build(app) as app:
        async with app._resolver.child() as call_a:
            kwargs_a = await call_a.resolve_params(tool_body)
            first = await tool_body(**kwargs_a)
        async with app._resolver.child() as call_b:
            kwargs_b = await call_b.resolve_params(tool_body)
            second = await tool_body(**kwargs_b)

    assert first is second
    assert _Inner.entered == 1


@pytest.mark.asyncio
async def test_singleton_factory_with_lazy_per_call_rejected() -> None:
    """A SINGLETON factory declaring ``Lazy[_PerCallThing]`` is
    rejected at ``async with build(app) as app:`` time with a TypeError naming the
    offending factory + the per-call inner type + migration paths."""
    app = a2kit.App("test")
    app.provide(_PerCallThing, per_call=True)

    def make_bad_outer(pc_lazy: Lazy[_PerCallThing]) -> _OuterWithPerCall:
        return _OuterWithPerCall(pc_lazy=pc_lazy)

    app.provide(_OuterWithPerCall, make_bad_outer)

    with pytest.raises(TypeError) as exc_info:
        async with build(app) as app:
            pass

    msg = str(exc_info.value)
    # Migration message names the inner per-call type and routes consumer to the fix.
    assert "_PerCallThing" in msg
    assert "Lazy" in msg
    # At least one of the migration paths is mentioned.
    assert ("per-call" in msg) or ("per_call" in msg)


@pytest.mark.asyncio
async def test_per_call_factory_with_lazy_t_works() -> None:
    """A per-call factory with ``Lazy[_Inner]`` (Inner is app-scope)
    is valid. Each dispatch builds a fresh per-call aggregate; the
    captured closure resolves through the per-call child's parent
    chain to the cached app-scope _Inner."""
    app = a2kit.App("test")
    app.provide(_Inner)  # app-scope

    def make_per_call(inner_lazy: Lazy[_Inner]) -> _PerCallAggregate:
        return _PerCallAggregate(inner_lazy=inner_lazy)

    app.provide(_PerCallAggregate, make_per_call, per_call=True)

    async def tool_body(agg: _PerCallAggregate) -> tuple[int, _Inner]:
        inner = await agg.inner_lazy()
        return id(agg), inner

    async with build(app) as app:
        async with app._resolver.child() as call_a:
            kwargs_a = await call_a.resolve_params(tool_body)
            id_a, inner_a = await tool_body(**kwargs_a)
        async with app._resolver.child() as call_b:
            kwargs_b = await call_b.resolve_params(tool_body)
            id_b, inner_b = await tool_body(**kwargs_b)

    # Fresh aggregate per dispatch.
    assert id_a != id_b
    # Inner is app-scope: same instance across dispatches.
    assert inner_a is inner_b
    assert _Inner.entered == 1
