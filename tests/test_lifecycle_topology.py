"""BDD contract for consolidate-lifecycle-on-async-cm-protocol task 1.5.

Singletons enter in topological order (dependencies first), exit in
reverse. Concurrent first-touch on a router coalesces.
"""

from __future__ import annotations

import asyncio

import pytest

import a2kit

pytestmark = pytest.mark.skip(reason="contract for consolidate-lifecycle-on-async-cm-protocol; un-skip when impl lands")


@pytest.mark.asyncio
async def test_dependent_enters_after_dependency() -> None:
    order: list[str] = []

    class _DB:
        async def __aenter__(self) -> _DB:
            order.append("DB-enter")
            return self

        async def __aexit__(self, *_exc: object) -> None:
            order.append("DB-exit")

    class _Repo:
        def __init__(self, db: _DB) -> None:
            self.db = db

        async def __aenter__(self) -> _Repo:
            order.append("Repo-enter")
            return self

        async def __aexit__(self, *_exc: object) -> None:
            order.append("Repo-exit")

    app = a2kit.App("x")
    app.singleton(_DB)
    app.singleton(_Repo)

    async with app:
        pass

    assert order == ["DB-enter", "Repo-enter", "Repo-exit", "DB-exit"]


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

        @a2kit.read
        async def get(self) -> dict:  # type: ignore[override]
            return {}

        tools = (get,)

    app = a2kit.App("x")
    app.add_router(_R())

    async with a2kit.testing.client(app) as client:
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

        @a2kit.read
        async def get(self) -> dict:  # type: ignore[override]
            return {}

        tools = (get,)

    app = a2kit.App("x")
    app.add_router(_R())

    async with a2kit.testing.client(app) as client:
        with pytest.raises(Exception):  # noqa: BLE001 -- shape of exception is router-impl-defined
            await client.invoke("r.get")
        # Second dispatch retries __aenter__ since first failed.
        result = await client.invoke("r.get")
        assert result == {}

    assert attempts == 2
