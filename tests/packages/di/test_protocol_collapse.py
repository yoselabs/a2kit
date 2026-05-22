"""BDD: single lifecycle protocol convention.

Covers spec ``lazy-init-resources``: only ``__aenter__``/``__aexit__`` and
``@asynccontextmanager`` factories are recognized. ``aclose()`` and
``close()`` methods are NOT auto-detected for cleanup.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import pytest

import a2kit
from a2kit.runtime import build


@pytest.mark.asyncio
async def test_aexit_protocol_works() -> None:
    """Class with ``__aenter__``/``__aexit__`` is entered and exited at scope boundaries."""

    class _Resource:
        entered = False
        exited = False

        async def __aenter__(self) -> _Resource:
            type(self).entered = True
            return self

        async def __aexit__(self, *exc: object) -> None:
            type(self).exited = True

    app = a2kit.App("test")
    app.provide(_Resource)

    async with build(app) as app:
        await app._resolver.get(_Resource)
        assert _Resource.entered is True
        assert _Resource.exited is False

    assert _Resource.exited is True


@pytest.mark.asyncio
async def test_asynccontextmanager_factory_works() -> None:
    """An ``@asynccontextmanager`` factory yields the instance and runs ``finally`` on exit."""

    setup_called = False
    teardown_called = False

    class _Resource:
        pass

    @asynccontextmanager
    async def resource_factory() -> AsyncIterator[_Resource]:
        nonlocal setup_called, teardown_called
        setup_called = True
        try:
            yield _Resource()
        finally:
            teardown_called = True

    app = a2kit.App("test")
    app.provide(_Resource, resource_factory)

    async with build(app) as app:
        await app._resolver.get(_Resource)
        assert setup_called is True
        assert teardown_called is False

    assert teardown_called is True


@pytest.mark.asyncio
async def test_aclose_not_detected() -> None:
    """A class with ``aclose()`` but no ``__aexit__`` is NOT auto-cleaned-up."""

    class _Resource:
        aclose_called = False

        async def aclose(self) -> None:
            type(self).aclose_called = True

    app = a2kit.App("test")
    app.provide(_Resource)

    async with build(app) as app:
        await app._resolver.get(_Resource)

    assert _Resource.aclose_called is False, "framework auto-detected aclose() — should be banned per protocol collapse"


@pytest.mark.asyncio
async def test_close_not_detected() -> None:
    """A class with ``close()`` but no ``__aexit__`` is NOT auto-cleaned-up."""

    class _Resource:
        close_called = False

        def close(self) -> None:
            type(self).close_called = True

    app = a2kit.App("test")
    app.provide(_Resource)

    async with build(app) as app:
        await app._resolver.get(_Resource)

    assert _Resource.close_called is False, "framework auto-detected close() — should be banned per protocol collapse"
