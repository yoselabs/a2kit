"""BDD: per-call scope contract for ``provide(..., per_call=True)``.

Covers spec ``di-per-call-scope``: child container per dispatch, fresh
instances per call, within-call caching, cleanup on normal return and on
exception, cross-scope dependency resolution, and graph validation of
app-scope-depends-on-per-call (rejected).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import pytest

import a2kit


class _Transaction:
    instances_created: int = 0
    cleanup_count: int = 0
    last_exc: BaseException | None = None

    def __init__(self) -> None:
        type(self).instances_created += 1

    async def __aenter__(self) -> _Transaction:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: object) -> None:
        type(self).cleanup_count += 1
        type(self).last_exc = exc


class _ConnectionPool:
    instances_created: int = 0

    def __init__(self) -> None:
        type(self).instances_created += 1

    async def __aenter__(self) -> _ConnectionPool:
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass


@pytest.fixture(autouse=True)
def _reset_counters() -> None:
    _Transaction.instances_created = 0
    _Transaction.cleanup_count = 0
    _Transaction.last_exc = None
    _ConnectionPool.instances_created = 0


@pytest.mark.asyncio
async def test_per_call_yields_fresh_instance_per_dispatch() -> None:
    """Two dispatches receive distinct ``Transaction`` instances; factory invoked twice."""
    app = a2kit.App("test")
    app.provide(_Transaction, per_call=True)

    async with app:
        # Simulate two dispatches by opening two per-call children.
        async with app._resolver.child() as call1:
            tx1 = await call1.get(_Transaction)
        async with app._resolver.child() as call2:
            tx2 = await call2.get(_Transaction)

    assert tx1 is not tx2, "per-call resources must be distinct across dispatches"
    assert _Transaction.instances_created == 2


@pytest.mark.asyncio
async def test_per_call_caches_within_single_call() -> None:
    """Two resolves of the same per-call type within one dispatch share an instance."""
    app = a2kit.App("test")
    app.provide(_Transaction, per_call=True)

    async with app, app._resolver.child() as call:
        a = await call.get(_Transaction)
        b = await call.get(_Transaction)

    assert a is b, "within-call cache miss: per-call resolved twice yielded distinct objects"
    assert _Transaction.instances_created == 1


@pytest.mark.asyncio
async def test_per_call_cleanup_runs_on_normal_return() -> None:
    """``__aexit__`` runs when the per-call scope closes after normal completion."""
    app = a2kit.App("test")
    app.provide(_Transaction, per_call=True)

    async with app, app._resolver.child() as call:
        tx = await call.get(_Transaction)
        assert _Transaction.cleanup_count == 0, "cleanup ran too early"

    # After ``async with call`` exits cleanly:
    assert _Transaction.cleanup_count == 1
    assert _Transaction.last_exc is None


@pytest.mark.asyncio
async def test_per_call_cleanup_runs_on_exception() -> None:
    """``__aexit__`` runs with exception in scope, then the exception propagates."""
    app = a2kit.App("test")
    app.provide(_Transaction, per_call=True)

    class _BodyError(RuntimeError):
        pass

    async with app:
        with pytest.raises(_BodyError):
            async with app._resolver.child() as call:
                await call.get(_Transaction)
                raise _BodyError("body failed")

    assert _Transaction.cleanup_count == 1
    assert isinstance(_Transaction.last_exc, _BodyError), (
        f"cleanup did not see propagating exception, saw {_Transaction.last_exc!r}"
    )


@pytest.mark.asyncio
async def test_per_call_depends_on_app_scope() -> None:
    """A per-call factory may depend on an app-scope type; app-scope is resolved through the parent."""

    @asynccontextmanager
    async def tx_factory(pool: _ConnectionPool) -> AsyncIterator[_Transaction]:
        # The factory closes over the app-scope pool.
        tx = _Transaction()
        tx.pool = pool  # type: ignore[attr-defined]
        async with tx:
            yield tx

    app = a2kit.App("test")
    app.provide(_ConnectionPool)
    app.provide(_Transaction, tx_factory, per_call=True)

    async with app:
        async with app._resolver.child() as call1:
            tx1 = await call1.get(_Transaction)
        async with app._resolver.child() as call2:
            tx2 = await call2.get(_Transaction)

    # Two per-call transactions, but both share the one app-scope pool.
    assert tx1 is not tx2
    assert _ConnectionPool.instances_created == 1, (
        f"app-scope pool created {_ConnectionPool.instances_created} times — expected 1"
    )
    assert tx1.pool is tx2.pool  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_app_scope_cannot_depend_on_per_call() -> None:
    """Graph validation rejects app-scope→per-call dependency at ``async with app:``."""

    @asynccontextmanager
    async def bad_app_factory(tx: _Transaction) -> AsyncIterator[object]:
        yield object()

    app = a2kit.App("test")
    app.provide(_Transaction, per_call=True)
    app.provide(object, bad_app_factory)  # app-scope default; depends on per-call _Transaction

    with pytest.raises(TypeError) as excinfo:
        async with app:
            pass

    msg = str(excinfo.value)
    # Spec: message names both types and the violation phrase.
    assert "app-scope depends on per-call" in msg
