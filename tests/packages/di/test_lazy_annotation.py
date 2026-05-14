"""BDD: ``Lazy[T]`` annotation for conditional dependency injection.

Covers spec ``di-conditional-injection``: alias importability, dispatcher
recognition of ``Lazy[T]`` / ``Callable[[], Awaitable[T]]``, scope-honoring
closure semantics, cleanup wiring through the lazy path.
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.packages.di import Lazy


class _BrowserPool:
    instances_created: int = 0
    cleanup_count: int = 0

    def __init__(self) -> None:
        type(self).instances_created += 1

    async def __aenter__(self) -> _BrowserPool:
        return self

    async def __aexit__(self, *exc: object) -> None:
        type(self).cleanup_count += 1


class _Transaction:
    instances_created: int = 0
    cleanup_count: int = 0

    def __init__(self) -> None:
        type(self).instances_created += 1

    async def __aenter__(self) -> _Transaction:
        return self

    async def __aexit__(self, *exc: object) -> None:
        type(self).cleanup_count += 1


@pytest.fixture(autouse=True)
def _reset_counters() -> None:
    _BrowserPool.instances_created = 0
    _BrowserPool.cleanup_count = 0
    _Transaction.instances_created = 0
    _Transaction.cleanup_count = 0


def test_lazy_alias_importable() -> None:
    """``from a2kit.packages.di import Lazy`` succeeds and is a generic alias."""
    # ``Lazy[T]`` parameterises like a generic alias.
    parameterised = Lazy[_BrowserPool]
    assert parameterised is not None


@pytest.mark.asyncio
async def test_lazy_param_receives_callable_not_instance() -> None:
    """A ``Lazy[T]`` parameter on a tool yields an awaitable callable, not ``T``."""

    app = a2kit.App("test")
    app.provide(_BrowserPool)

    captured: dict[str, object] = {}

    async def tool_body(browser: Lazy[_BrowserPool]) -> None:
        captured["browser"] = browser

    async with app, app._resolver.child() as call:
        kwargs = await call.resolve_params(tool_body)
        await tool_body(**kwargs)

    browser = captured["browser"]
    assert callable(browser), "Lazy[T] param did not receive a callable"
    assert not isinstance(browser, _BrowserPool), (
        "Lazy[T] param was given the resolved instance instead of a deferred closure"
    )


@pytest.mark.asyncio
async def test_lazy_never_invoked_resource_never_entered() -> None:
    """If the tool body never calls the Lazy closure, the resource is not entered."""

    app = a2kit.App("test")
    app.provide(_BrowserPool)

    async def tool_body(browser: Lazy[_BrowserPool]) -> str:
        return "done"  # never calls `browser()`

    async with app, app._resolver.child() as call:
        kwargs = await call.resolve_params(tool_body)
        result = await tool_body(**kwargs)

    assert result == "done"
    assert _BrowserPool.instances_created == 0, "factory invoked despite Lazy never called"
    assert _BrowserPool.cleanup_count == 0, "cleanup ran for unused Lazy"


@pytest.mark.asyncio
async def test_lazy_honors_app_scope_cache() -> None:
    """Lazy[T] of app-scope returns the same instance across calls."""

    app = a2kit.App("test")
    app.provide(_BrowserPool)  # app-scope default

    async def tool_body(browser: Lazy[_BrowserPool]) -> _BrowserPool:
        return await browser()

    async with app:
        async with app._resolver.child() as call:
            kwargs = await call.resolve_params(tool_body)
            bp1 = await tool_body(**kwargs)
        async with app._resolver.child() as call2:
            kwargs2 = await call2.resolve_params(tool_body)
            bp2 = await tool_body(**kwargs2)

    assert bp1 is bp2, "Lazy[T] of app-scope returned distinct instances across calls"
    assert _BrowserPool.instances_created == 1


@pytest.mark.asyncio
async def test_lazy_honors_per_call_cache() -> None:
    """Lazy[T] of per-call: same instance within a call, fresh across calls."""

    app = a2kit.App("test")
    app.provide(_Transaction, per_call=True)

    async def tool_body(tx: Lazy[_Transaction]) -> tuple[_Transaction, _Transaction]:
        return await tx(), await tx()

    async with app:
        async with app._resolver.child() as call1:
            kwargs = await call1.resolve_params(tool_body)
            a, b = await tool_body(**kwargs)
        async with app._resolver.child() as call2:
            kwargs = await call2.resolve_params(tool_body)
            c, _ = await tool_body(**kwargs)

    assert a is b, "Lazy[T] of per-call returned distinct instances within one call"
    assert a is not c, "Lazy[T] of per-call returned same instance across two calls"
    assert _Transaction.instances_created == 2


@pytest.mark.asyncio
async def test_lazy_resource_cleaned_up_at_scope_exit() -> None:
    """A resource resolved through Lazy is cleaned up at the same scope as direct injection."""

    app = a2kit.App("test")
    app.provide(_BrowserPool)
    app.provide(_Transaction, per_call=True)

    async def app_scope_tool(browser: Lazy[_BrowserPool]) -> None:
        await browser()  # triggers entry

    async def per_call_tool(tx: Lazy[_Transaction]) -> None:
        await tx()  # triggers entry

    async with app:
        async with app._resolver.child() as call:
            kwargs = await call.resolve_params(app_scope_tool)
            await app_scope_tool(**kwargs)
            kwargs = await call.resolve_params(per_call_tool)
            await per_call_tool(**kwargs)

        # After call ends: per-call transaction cleaned up; app-scope pool still alive.
        assert _Transaction.cleanup_count == 1, "per-call Lazy resource not cleaned at call exit"
        assert _BrowserPool.cleanup_count == 0, "app-scope Lazy resource cleaned prematurely"

    # After app exit: app-scope pool cleaned.
    assert _BrowserPool.cleanup_count == 1, "app-scope Lazy resource not cleaned at app exit"
