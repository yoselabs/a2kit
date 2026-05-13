"""Tests for ``app.singleton(T, factory, teardown=fn)`` — framework-owned
shutdown with topological ordering and error isolation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

import a2kit
from a2kit.packages.di.container import Container


# ----------------------------------------------------------- Container-level


class _A:
    pass


class _B:
    def __init__(self, a: _A) -> None:
        self.a = a


class _C:
    def __init__(self, b: _B) -> None:
        self.b = b


# Module-level factory-graph classes used by the topological-ordering test.
# Inner classes inside a test function can't be resolved by ``get_type_hints``
# under ``from __future__ import annotations`` (stringified annotations require
# the type name to be visible in the module's globals at resolve time).
class _SqliteR:
    closed_log: list[str] = []

    def close(self) -> None:
        type(self).closed_log.append("sqlite")


class _PoolR:
    def __init__(self, sql: _SqliteR) -> None:
        self.sql = sql

    def close(self) -> None:
        _SqliteR.closed_log.append("pool")


def test_teardown_order_empty_when_no_teardowns_registered() -> None:
    c = Container()
    c.register_singleton(_A, _A)
    assert c.teardown_order() == []


def test_teardown_order_excludes_unresolved_singletons() -> None:
    c = Container()
    c.register_singleton(_A, _A, teardown=lambda x: None)
    # Not resolved yet → sentinel stays — should not appear in teardown_order.
    assert c.teardown_order() == []


def test_teardown_order_linear_chain_dependents_first() -> None:
    """A depends on nothing; B depends on A; C depends on B.

    Resolve C (which transitively resolves B and A) and assert teardown
    order is C → B → A (dependents first).
    """
    c = Container()
    c.register_singleton(_A, _A, teardown=lambda x: None)
    c.register_singleton(_B, _B, teardown=lambda x: None)
    c.register_singleton(_C, _C, teardown=lambda x: None)
    c.resolve(_C)
    order = c.teardown_order()
    assert order == [_C, _B, _A]


def test_teardown_order_skips_singletons_without_teardown() -> None:
    """Only singletons with registered teardown appear in the output."""
    c = Container()
    c.register_singleton(_A, _A)  # no teardown
    c.register_singleton(_B, _B, teardown=lambda x: None)
    c.resolve(_B)
    order = c.teardown_order()
    assert order == [_B]


def test_teardown_order_handles_cycle_deterministically(caplog: Any) -> None:
    """Synthetic cycle in the factory graph → deterministic break + WARN."""
    c = Container()

    class _X:
        pass

    class _Y:
        pass

    c.register_singleton(_X, _X, teardown=lambda x: None)
    c.register_singleton(_Y, _Y, teardown=lambda x: None)
    c.resolve(_X)
    c.resolve(_Y)
    # Synthesize a cycle by direct provider manipulation post-resolution.
    from a2kit.packages.di.container import _ParamSpec

    c._param_cache[c._providers[_X]] = [_ParamSpec("y", _Y, has_default=False)]  # noqa: SLF001
    c._param_cache[c._providers[_Y]] = [_ParamSpec("x", _X, has_default=False)]  # noqa: SLF001

    with caplog.at_level(logging.WARNING, logger="a2kit.packages.di.container"):
        order = c.teardown_order()
    assert set(order) == {_X, _Y}
    assert any("cycle" in rec.message for rec in caplog.records)


# ----------------------------------------------------------- App-level


def test_teardown_fires_on_lifespan_exit() -> None:
    """Register one singleton with a sync teardown; assert it ran."""
    closed: list[str] = []

    class _R:
        def close(self) -> None:
            closed.append("R")

    app = a2kit.App("t")
    app.singleton(_R, _R, teardown=lambda r: r.close())

    async def go() -> None:
        async with app.lifespan_cm():
            app.container().resolve(_R)

    asyncio.run(go())
    assert closed == ["R"]


def test_async_teardown_is_awaited() -> None:
    closed: list[str] = []

    class _R:
        async def aclose(self) -> None:
            await asyncio.sleep(0)
            closed.append("R")

    app = a2kit.App("t")
    app.singleton(_R, _R, teardown=lambda r: r.aclose())

    async def go() -> None:
        async with app.lifespan_cm():
            app.container().resolve(_R)

    asyncio.run(go())
    assert closed == ["R"]


def test_teardown_topological_order_dependents_first() -> None:
    """B depends on A; both have teardowns. B closes before A."""
    _SqliteR.closed_log = []

    app = a2kit.App("t")
    # Register sqlite first (production-realistic order: factory deps
    # often force this).
    app.singleton(_SqliteR, _SqliteR, teardown=lambda r: r.close())
    app.singleton(_PoolR, _PoolR, teardown=lambda r: r.close())

    async def go() -> None:
        async with app.lifespan_cm():
            app.container().resolve(_PoolR)

    asyncio.run(go())
    # Dependents first → pool closes before sqlite.
    assert _SqliteR.closed_log == ["pool", "sqlite"]


def test_teardown_error_isolation_records_failure() -> None:
    """A raising teardown does not abort siblings; failure recorded."""
    closed: list[str] = []

    class _A2:
        def close(self) -> None:
            closed.append("A")

    class _B2:
        def close(self) -> None:
            raise RuntimeError("boom")

    class _C2:
        def close(self) -> None:
            closed.append("C")

    app = a2kit.App("t")
    app.singleton(_A2, _A2, teardown=lambda r: r.close())
    app.singleton(_B2, _B2, teardown=lambda r: r.close())
    app.singleton(_C2, _C2, teardown=lambda r: r.close())

    async def go() -> None:
        async with app.lifespan_cm():
            app.container().resolve(_A2)
            app.container().resolve(_B2)
            app.container().resolve(_C2)

    asyncio.run(go())
    # A and C still closed despite B raising.
    assert set(closed) == {"A", "C"}
    # Failure recorded.
    assert len(app.teardown_failures) == 1
    failed_type, exc = app.teardown_failures[0]
    assert failed_type is _B2
    assert isinstance(exc, RuntimeError)
    assert str(exc) == "boom"


def test_app_without_user_lifespan_but_with_teardown_still_fires() -> None:
    closed: list[str] = []

    class _R:
        def close(self) -> None:
            closed.append("R")

    app = a2kit.App("t")
    app.singleton(_R, _R, teardown=lambda r: r.close())
    # No user lifespan, no Router lifespan.
    assert app.has_lifespan() is True

    async def go() -> None:
        async with app.lifespan_cm():
            app.container().resolve(_R)

    asyncio.run(go())
    assert closed == ["R"]


def test_user_lifespan_finally_runs_before_framework_teardown() -> None:
    """User ``finally`` blocks run inside their own scope; framework
    teardowns run after the user lifespan fully exits.
    """
    order: list[str] = []

    class _R:
        def close(self) -> None:
            order.append("framework_teardown")

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def user_lifespan(app: Any) -> Any:  # noqa: ARG001
        order.append("user_enter")
        try:
            yield
        finally:
            order.append("user_exit")

    app = a2kit.App("t", lifespan=user_lifespan)
    app.singleton(_R, _R, teardown=lambda r: r.close())

    async def go() -> None:
        async with app.lifespan_cm():
            app.container().resolve(_R)

    asyncio.run(go())
    assert order == ["user_enter", "user_exit", "framework_teardown"]


def test_singletons_without_teardown_are_skipped() -> None:
    """Mixed: some singletons have teardowns, others don't.

    Only the ones with teardowns fire; others remain cached untouched.
    """
    closed: list[str] = []

    class _Has:
        def close(self) -> None:
            closed.append("has")

    class _Hasnt:
        pass

    app = a2kit.App("t")
    app.singleton(_Has, _Has, teardown=lambda r: r.close())
    app.singleton(_Hasnt, _Hasnt)

    async def go() -> None:
        async with app.lifespan_cm():
            app.container().resolve(_Has)
            app.container().resolve(_Hasnt)

    asyncio.run(go())
    assert closed == ["has"]
    assert app.teardown_failures == []


def test_no_teardowns_and_no_lifespan_returns_nullcontext() -> None:
    """App with no lifespan AND no teardown returns nullcontext (no behavior change)."""
    from contextlib import nullcontext as _nc

    app = a2kit.App("t")
    assert app.has_lifespan() is False
    cm = app.lifespan_cm()
    assert isinstance(cm, type(_nc()))


def test_a2kit_singleton_teardown_error_aggregates() -> None:
    """The exception class aggregates failures for programmatic introspection."""
    from a2kit.exceptions import A2KitError, A2KitSingletonTeardownError

    exc = A2KitSingletonTeardownError([(_A, ValueError("x")), (_B, RuntimeError("y"))])
    assert isinstance(exc, A2KitError)
    assert isinstance(exc, RuntimeError)
    assert len(exc.failures) == 2
    msg = str(exc)
    assert "_A" in msg
    assert "ValueError" in msg
    assert "_B" in msg
    assert "RuntimeError" in msg


# Silence pytest collection of imported helpers.
_ = pytest
