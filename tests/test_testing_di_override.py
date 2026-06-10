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
from a2kit.testing import app_of, client


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


def test_reregistered_fake_wins_last_write() -> None:
    """A fake provided last on the App beats the real registration."""
    app = app_of("t", _SingletonRouter()).provide(_LLM, lambda: _LLM("real")).provide(_LLM, lambda: _FakeLLM())

    async def go() -> None:
        async with client(app) as c:
            result = await c.invoke("_singleton_whoami")
            assert result == {"model": "fake"}

    asyncio.run(go())


def test_rebuild_gives_each_test_a_fresh_app() -> None:
    """Re-build is the isolation mechanism — two Apps, two independent wirings."""

    def build(*, fake: bool) -> a2kit.App:
        app = app_of("t", _SingletonRouter())
        app.provide(_LLM, (lambda: _FakeLLM()) if fake else (lambda: _LLM("real")))
        return app

    async def go() -> None:
        async with client(build(fake=True)) as c:
            assert (await c.invoke("_singleton_whoami")) == {"model": "fake"}
        async with client(build(fake=False)) as c:
            assert (await c.invoke("_singleton_whoami")) == {"model": "real"}

    asyncio.run(go())


def test_fake_for_an_async_factory_registration() -> None:
    """Re-registering over an async factory works — the fake is plain."""

    async def make_llm() -> _LLM:
        return _LLM("async-real")

    app = app_of("t", _SingletonRouter()).provide(_LLM, make_llm).provide(_LLM, lambda: _FakeLLM())

    async def go() -> None:
        async with client(app) as c:
            assert (await c.invoke("_singleton_whoami")) == {"model": "fake"}

    asyncio.run(go())


def test_testclient_override_is_removed() -> None:
    """The removed `TestClient.override` is gone — plain AttributeError."""
    app = app_of("t", _SingletonRouter()).provide(_LLM, lambda: _LLM("real"))

    async def go() -> None:
        async with client(app) as c:
            with pytest.raises(AttributeError):
                getattr(c, "override")  # noqa: B009 -- dynamic access is the trigger

    asyncio.run(go())
