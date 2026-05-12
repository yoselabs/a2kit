"""Tests — TestClient.override (round-5 gap 3).

Snapshot/restore-based DI override on the in-process test client.
Replaces ad-hoc `monkeypatch.setattr` patterns; type-safe via TypeVar.
"""

from __future__ import annotations

import asyncio

import pytest

import a2kit
from a2kit.testing import client


class _LLM:
    """Fake-able dependency."""

    def __init__(self, model: str = "real") -> None:
        self.model = model

    def name(self) -> str:
        return self.model


class _FakeLLM:
    def __init__(self, model: str = "fake") -> None:
        self.model = model

    def name(self) -> str:
        return self.model


class _SingletonRouter(a2kit.Router):
    slug = "_singleton"
    @a2kit.read()
    async def whoami(self, llm: _LLM) -> dict[str, str]:
        return {"model": llm.name()}
    tools = (whoami,)


def test_override_replaces_singleton() -> None:
    app = a2kit.App("t").singleton(_LLM, lambda: _LLM("real")).add_router(_SingletonRouter())

    async def go() -> None:
        async with client(app) as c:
            c.override(_LLM, _FakeLLM())
            result = await c.invoke("whoami")
            assert result == {"model": "fake"}

    asyncio.run(go())


def test_override_is_restored_on_normal_exit() -> None:
    app = a2kit.App("t").singleton(_LLM, lambda: _LLM("real")).add_router(_SingletonRouter())

    async def first() -> None:
        async with client(app) as c:
            c.override(_LLM, _FakeLLM())
            r = await c.invoke("whoami")
            assert r == {"model": "fake"}

    async def second() -> None:
        async with client(app) as c:
            r = await c.invoke("whoami")
            assert r == {"model": "real"}

    asyncio.run(first())
    asyncio.run(second())


def test_override_is_restored_on_exception() -> None:
    app = a2kit.App("t").singleton(_LLM, lambda: _LLM("real")).add_router(_SingletonRouter())

    async def boomy() -> None:
        async with client(app) as c:
            c.override(_LLM, _FakeLLM())
            raise RuntimeError("boom")

    async def go() -> None:
        with pytest.raises(RuntimeError, match="boom"):
            await boomy()
        async with client(app) as c:
            r = await c.invoke("whoami")
            assert r == {"model": "real"}

    asyncio.run(go())


def test_override_of_unregistered_type_is_removed_on_exit() -> None:
    app = a2kit.App("t").add_router(_SingletonRouter())
    app.provide(_LLM, lambda: _LLM("real"))

    class _Other:
        pass

    async def go() -> None:
        async with client(app) as c:
            c.override(_Other, _Other())
            assert app.container().has(_Other)
        assert not app.container().has(_Other)

    asyncio.run(go())


def test_last_write_wins_within_session() -> None:
    app = a2kit.App("t").singleton(_LLM, lambda: _LLM("real")).add_router(_SingletonRouter())

    async def go() -> None:
        async with client(app) as c:
            c.override(_LLM, _FakeLLM())
            c.override(_LLM, _FakeLLM("fake-2"))
            result = await c.invoke("whoami")
            assert result == {"model": "fake-2"}

    asyncio.run(go())


def test_override_on_overlapping_session_raises() -> None:
    app = a2kit.App("t").singleton(_LLM, lambda: _LLM("real")).add_router(_SingletonRouter())

    async def go() -> None:
        async with client(app):

            async def _open_nested() -> None:
                async with client(app):
                    pass

            with pytest.raises(RuntimeError, match="override ownership"):
                await _open_nested()

    asyncio.run(go())


def test_override_works_via_peek() -> None:
    """`peek` and `override` are read/write complements — peek sees the fake."""
    from a2kit.testing import peek

    app = a2kit.App("t").singleton(_LLM, lambda: _LLM("real"))

    async def go() -> None:
        async with client(app) as c:
            fake = _FakeLLM()
            c.override(_LLM, fake)
            assert peek(app, _LLM) is fake

    asyncio.run(go())


def test_async_factory_singleton_override_works() -> None:
    """Overriding a type registered with an async factory: the override
    must bypass the async path (the fake is the resolved value)."""

    async def make_llm() -> _LLM:
        return _LLM("async-real")

    app = a2kit.App("t").singleton(_LLM, make_llm).add_router(_SingletonRouter())

    async def go() -> None:
        async with client(app) as c:
            c.override(_LLM, _FakeLLM())
            result = await c.invoke("whoami")
            assert result == {"model": "fake"}

    asyncio.run(go())
