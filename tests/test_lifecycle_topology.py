"""BDD contract for consolidate-lifecycle-on-async-cm-protocol task 1.5.

Singletons enter in topological order (dependencies first), exit in
reverse. Concurrent first-touch on a router coalesces.
"""

from __future__ import annotations

import asyncio

import pytest

import a2kit
from a2kit.testing import client as _testing_client


class _TopoDB:
    def __init__(self, order: list[str]) -> None:
        self._order = order

    async def __aenter__(self) -> _TopoDB:
        self._order.append("DB-enter")
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self._order.append("DB-exit")


class _TopoRepo:
    def __init__(self, db: _TopoDB, order: list[str]) -> None:
        self.db = db
        self._order = order

    async def __aenter__(self) -> _TopoRepo:
        self._order.append("Repo-enter")
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self._order.append("Repo-exit")


@pytest.mark.asyncio
async def test_dependent_enters_after_dependency() -> None:
    order: list[str] = []

    def _make_db() -> _TopoDB:
        return _TopoDB(order)

    def _make_repo(db: _TopoDB) -> _TopoRepo:
        return _TopoRepo(db, order)

    app = a2kit.App("x")
    # Register _TopoRepo BEFORE _TopoDB to confirm registration order
    # does not win over the DI topo order.
    app.singleton(_TopoRepo, _make_repo)
    app.singleton(_TopoDB, _make_db)

    async with app:
        pass

    assert order == ["DB-enter", "Repo-enter", "Repo-exit", "DB-exit"]


@pytest.mark.asyncio
async def test_unrelated_singletons_preserve_registration_order() -> None:
    order: list[str] = []

    class _X:
        async def __aenter__(self) -> _X:
            order.append("X")
            return self

        async def __aexit__(self, *_exc: object) -> None: ...

    class _Y:
        async def __aenter__(self) -> _Y:
            order.append("Y")
            return self

        async def __aexit__(self, *_exc: object) -> None: ...

    class _Z:
        async def __aenter__(self) -> _Z:
            order.append("Z")
            return self

        async def __aexit__(self, *_exc: object) -> None: ...

    app = a2kit.App("x")
    app.singleton(_X)
    app.singleton(_Y)
    app.singleton(_Z)

    async with app:
        pass

    assert order == ["X", "Y", "Z"]


@pytest.mark.asyncio
async def test_concurrent_first_dispatch_coalesces_router_enter() -> None:
    started = asyncio.Event()
    allow_finish = asyncio.Event()
    enter_count = 0

    class _R(a2kit.Router):
        slug = "r"

        async def __aenter__(self) -> _R:
            nonlocal enter_count
            enter_count += 1
            started.set()
            await allow_finish.wait()
            return self

        async def __aexit__(self, *_exc: object) -> None: ...

        @a2kit.read()
        async def get(self) -> dict:  # type: ignore[override]
            return {}

        tools = (get,)

    app = a2kit.App("x")
    app.add_router(_R())

    async with _testing_client(app) as client:
        t1 = asyncio.create_task(client.invoke("r.get"))
        t2 = asyncio.create_task(client.invoke("r.get"))
        await started.wait()
        allow_finish.set()
        await asyncio.gather(t1, t2)

    assert enter_count == 1


@pytest.mark.asyncio
async def test_router_aenter_failure_does_not_cache_entered_state() -> None:
    attempts = 0

    class _R(a2kit.Router):
        slug = "r"

        async def __aenter__(self) -> _R:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("boom")
            return self

        async def __aexit__(self, *_exc: object) -> None: ...

        @a2kit.read()
        async def get(self) -> dict:  # type: ignore[override]
            return {}

        tools = (get,)

    app = a2kit.App("x")
    app.add_router(_R())

    async with _testing_client(app) as client:
        with pytest.raises(Exception):  # noqa: BLE001 -- shape of exception is router-impl-defined
            await client.invoke("r.get")
        # Second dispatch retries __aenter__ since first failed.
        result = await client.invoke("r.get")
        assert result == {}

    assert attempts == 2
