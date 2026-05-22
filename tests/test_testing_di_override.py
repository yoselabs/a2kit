"""Tests — DI overrides in tests are re-build, not post-seal mutation.

The dedicated test-override seam (`TestClient.override` +
`Container._override` / `_snapshot` / `_restore`) was removed in v0.40.
Swapping a real service for a fake is plain composition-root
re-registration: construct a fresh `a2kit.App` and `provide` the fake
last (last-write-wins). This reconciles the code with ADR 0006, whose
Y-statement always said there is no override after the container is
sealed. See ADR 0017.
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


def test_reregistered_fake_wins_last_write() -> None:
    """A fake provided last on the App beats the real registration."""
    app = a2kit.App("t").provide(_LLM, lambda: _LLM("real")).provide(_LLM, lambda: _FakeLLM()).add_router(_SingletonRouter())

    async def go() -> None:
        async with client(app) as c:
            result = await c.invoke("whoami")
            assert result == {"model": "fake"}

    asyncio.run(go())


def test_rebuild_gives_each_test_a_fresh_app() -> None:
    """Re-build is the isolation mechanism — two Apps, two independent wirings."""

    def build(*, fake: bool) -> a2kit.App:
        app = a2kit.App("t").add_router(_SingletonRouter())
        app.provide(_LLM, (lambda: _FakeLLM()) if fake else (lambda: _LLM("real")))
        return app

    async def go() -> None:
        async with client(build(fake=True)) as c:
            assert (await c.invoke("whoami")) == {"model": "fake"}
        async with client(build(fake=False)) as c:
            assert (await c.invoke("whoami")) == {"model": "real"}

    asyncio.run(go())


def test_fake_for_an_async_factory_registration() -> None:
    """Re-registering over an async factory works — the fake is plain."""

    async def make_llm() -> _LLM:
        return _LLM("async-real")

    app = a2kit.App("t").provide(_LLM, make_llm).provide(_LLM, lambda: _FakeLLM()).add_router(_SingletonRouter())

    async def go() -> None:
        async with client(app) as c:
            assert (await c.invoke("whoami")) == {"model": "fake"}

    asyncio.run(go())


def test_testclient_override_raises_migration_hint() -> None:
    """The removed `TestClient.override` raises with the re-build recipe."""
    app = a2kit.App("t").provide(_LLM, lambda: _LLM("real")).add_router(_SingletonRouter())

    async def go() -> None:
        async with client(app) as c:
            with pytest.raises(TypeError, match=r"re-build|fresh a2kit\.App"):
                c.override(_LLM, _FakeLLM())  # the removed seam — TestClient.__getattr__ raises

    asyncio.run(go())
