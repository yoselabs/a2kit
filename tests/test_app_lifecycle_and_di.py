"""Tests for app-lifecycle-and-di-ergonomics:

- Section 1: Container.resolve_sync, default-None connection, SyncResolveUnavailable
- Section 2: App.singleton (sync/async, two-app isolation, connection rejection, introspection)
- Section 3+5: Lifecycle dispatch (ordering, failure semantics, MCP merge)
- Section 4: CLI lifecycle integration via invoke_tool_sync
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from a2kit.app import (
    UNRESOLVED,
    App,
    _SingletonWrapper,
    dispatch_shutdown,
    dispatch_startup,
)
from a2kit.packages.connections.container import SyncResolveUnavailable


# ----- Fixtures / helpers ----------------------------------------------- #


class _State:
    def __init__(self, label: str = "x") -> None:
        self.label = label


class _Settings:
    pass


class _Store:
    def __init__(self, settings: _Settings) -> None:
        self.settings = settings


# ----- Section 1: container ergonomics --------------------------------- #


@pytest.mark.asyncio
async def test_resolve_default_none_connection() -> None:
    app = App("t")
    app.provide(_Settings, lambda: _Settings())
    s = await app.container().resolve(_Settings)
    assert isinstance(s, _Settings)


def test_resolve_sync_walks_sync_chain() -> None:
    app = App("t")
    app.provide(_Settings, lambda: _Settings())

    def make_store(settings: _Settings) -> _Store:
        return _Store(settings)

    app.provide(_Store, make_store)
    store = app.container().resolve_sync(_Store)
    assert isinstance(store, _Store)
    assert isinstance(store.settings, _Settings)


def test_resolve_sync_async_link_raises_with_named_offender() -> None:
    async def make_settings() -> _Settings:
        return _Settings()

    app = App("t")
    app.provide(_Settings, make_settings)

    def make_store(settings: _Settings) -> _Store:
        return _Store(settings)

    app.provide(_Store, make_store)
    with pytest.raises(SyncResolveUnavailable) as ei:
        app.container().resolve_sync(_Store)
    assert ei.value.async_link is _Settings


@pytest.mark.asyncio
async def test_existing_connection_kwarg_still_works() -> None:
    """Preserve compat: connection-using providers continue to function."""
    app = App("t")

    def conn_factory(connection: str) -> dict:
        return {"conn": connection}

    app.provide(dict, conn_factory)
    out = await app.container().resolve(dict, connection="foo")
    assert out == {"conn": "foo"}


def test_resolve_sync_default_none_connection() -> None:
    app = App("t")
    app.provide(_Settings, lambda: _Settings())
    # No connection arg — chain doesn't reach connection.
    assert isinstance(app.container().resolve_sync(_Settings), _Settings)


# ----- Section 2: singletons ------------------------------------------- #


def test_singleton_method_form_caches() -> None:
    calls = {"n": 0}

    def factory() -> _State:
        calls["n"] += 1
        return _State(f"build{calls['n']}")

    app = App("t")
    app.singleton(_State, factory)
    a = app.container().resolve_sync(_State)
    b = app.container().resolve_sync(_State)
    assert a is b
    assert calls["n"] == 1


def test_singleton_decorator_form() -> None:
    app = App("t")

    @app.singleton(_State)
    def make_state() -> _State:
        return _State("decorated")

    s = app.container().resolve_sync(_State)
    assert s.label == "decorated"
    # Decorator returns the original function unchanged
    assert callable(make_state)


def test_two_apps_independent_singletons() -> None:
    app_a = App("a")
    app_b = App("b")
    app_a.singleton(_State, lambda: _State("A"))
    app_b.singleton(_State, lambda: _State("B"))
    sa = app_a.container().resolve_sync(_State)
    sb = app_b.container().resolve_sync(_State)
    assert sa is not sb
    assert sa.label == "A"
    assert sb.label == "B"


@pytest.mark.asyncio
async def test_singleton_async_factory_coalesces_concurrent_first_resolve() -> None:
    calls = {"n": 0}

    async def factory() -> _State:
        calls["n"] += 1
        await asyncio.sleep(0.01)
        return _State("async")

    app = App("t")
    app.singleton(_State, factory)
    container = app.container()
    results = await asyncio.gather(*(container.resolve(_State) for _ in range(10)))
    assert all(r is results[0] for r in results)
    assert calls["n"] == 1


def test_singleton_sync_resolve_after_async_cache_populated() -> None:
    async def factory() -> _State:
        return _State("async")

    app = App("t")
    app.singleton(_State, factory)
    # First resolve must be async (factory is async, not yet cached).
    s_async = asyncio.run(app.container().resolve(_State))
    # After cache populated, sync resolve works.
    s_sync = app.container().resolve_sync(_State)
    assert s_async is s_sync


def test_singleton_sync_resolve_fails_for_unresolved_async() -> None:
    async def factory() -> _State:
        return _State("async")

    app = App("t")
    app.singleton(_State, factory)
    with pytest.raises(SyncResolveUnavailable) as ei:
        app.container().resolve_sync(_State)
    assert ei.value.async_link is _State


def test_singleton_rejects_direct_connection_dep() -> None:
    app = App("t")

    def bad(connection: str) -> _State:
        return _State()

    with pytest.raises(ValueError, match="connection"):
        app.singleton(_State, bad)


def test_singleton_rejects_transitive_connection_dep() -> None:
    app = App("t")

    def conn_cfg(connection: str) -> dict:
        return {}

    app.provide(dict, conn_cfg)

    def bad(cfg: dict) -> _State:
        return _State()

    with pytest.raises(ValueError, match="transitively"):
        app.singleton(_State, bad)


def test_has_singleton_and_singletons_introspection() -> None:
    app = App("t")
    app.singleton(_State, lambda: _State())
    assert app.has_singleton(_State) is True
    snap = app.singletons()
    assert _State in snap
    assert snap[_State] is UNRESOLVED  # not yet resolved
    app.container().resolve_sync(_State)
    snap2 = app.singletons()
    assert isinstance(snap2[_State], _State)


def test_singleton_chain_with_provide() -> None:
    """Singleton can depend on provide-registered types; deps resolve per dispatch."""
    app = App("t")
    app.provide(_Settings, lambda: _Settings())

    def make_store(settings: _Settings) -> _Store:
        return _Store(settings)

    app.singleton(_Store, make_store)
    a = app.container().resolve_sync(_Store)
    b = app.container().resolve_sync(_Store)
    assert a is b  # singleton cached
    assert isinstance(a.settings, _Settings)


def test_provide_then_singleton_last_write_wins() -> None:
    app = App("t")
    app.provide(_State, lambda: _State("via_provide"))
    app.singleton(_State, lambda: _State("via_singleton"))
    a = app.container().resolve_sync(_State)
    b = app.container().resolve_sync(_State)
    assert a is b
    assert a.label == "via_singleton"


# ----- Section 3: lifecycle dispatch ----------------------------------- #


@pytest.mark.asyncio
async def test_startup_runs_in_registration_order() -> None:
    order: list[str] = []
    app = App("t")
    app.on_startup(lambda a: order.append("h1"))

    @app.on_startup
    async def h2(a: App) -> None:
        order.append("h2")

    app.on_startup(lambda a: order.append("h3"))
    await dispatch_startup(app)
    assert order == ["h1", "h2", "h3"]


@pytest.mark.asyncio
async def test_shutdown_runs_in_reverse_order() -> None:
    order: list[str] = []
    app = App("t")
    app.on_shutdown(lambda a: order.append("s1"))
    app.on_shutdown(lambda a: order.append("s2"))
    app.on_shutdown(lambda a: order.append("s3"))
    await dispatch_shutdown(app)
    assert order == ["s3", "s2", "s1"]


@pytest.mark.asyncio
async def test_startup_failure_aborts_subsequent_handlers() -> None:
    order: list[str] = []
    app = App("t")
    app.on_startup(lambda a: order.append("h1"))

    def boom(a: App) -> None:
        order.append("boom")
        raise RuntimeError("startup failed")

    app.on_startup(boom)
    app.on_startup(lambda a: order.append("h3"))

    with pytest.raises(RuntimeError, match="startup failed"):
        await dispatch_startup(app)
    assert order == ["h1", "boom"]


@pytest.mark.asyncio
async def test_shutdown_failure_logged_and_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    order: list[str] = []
    app = App("t")
    app.on_shutdown(lambda a: order.append("s1"))

    def bad(a: App) -> None:
        order.append("bad")
        raise RuntimeError("close failed")

    app.on_shutdown(bad)
    app.on_shutdown(lambda a: order.append("s3"))

    with caplog.at_level(logging.ERROR, logger="a2kit.lifecycle"):
        await dispatch_shutdown(app)  # must not raise
    # LIFO: s3 → bad → s1
    assert order == ["s3", "bad", "s1"]
    assert any("shutdown handler" in rec.message for rec in caplog.records)


def test_on_startup_and_on_shutdown_decorator_form() -> None:
    app = App("t")

    @app.on_startup
    async def boot(a: App) -> None:
        pass

    @app.on_shutdown
    async def quit_(a: App) -> None:
        pass

    assert boot in app._startup_handlers
    assert quit_ in app._shutdown_handlers
    # Decorators returned the original functions
    assert callable(boot) and callable(quit_)


def test_has_lifecycle_handlers_reflects_registration() -> None:
    app = App("t")
    assert app.has_lifecycle_handlers() is False
    app.on_startup(lambda a: None)
    assert app.has_lifecycle_handlers() is True


# ----- Section 5: MCP lifespan merge ----------------------------------- #


@pytest.mark.asyncio
async def test_mcp_merge_lifespan_runs_a2kit_around_user() -> None:
    from contextlib import asynccontextmanager

    from a2kit.packages.mcp.server import _merge_lifespan

    order: list[str] = []
    app = App("t")
    app.on_startup(lambda a: order.append("a2k_start"))
    app.on_shutdown(lambda a: order.append("a2k_stop"))

    @asynccontextmanager
    async def user_lifespan(server):
        order.append("user_enter")
        try:
            yield {"user": True}
        finally:
            order.append("user_exit")

    merged = _merge_lifespan(app, user_lifespan)
    async with merged(server=None) as state:
        order.append("body")
        assert state == {"user": True}
    assert order == ["a2k_start", "user_enter", "body", "user_exit", "a2k_stop"]


@pytest.mark.asyncio
async def test_mcp_merge_lifespan_without_user_lifespan() -> None:
    from a2kit.packages.mcp.server import _merge_lifespan

    order: list[str] = []
    app = App("t")
    app.on_startup(lambda a: order.append("start"))
    app.on_shutdown(lambda a: order.append("stop"))

    merged = _merge_lifespan(app, None)
    async with merged(server=None) as state:
        assert state is None
        order.append("body")
    assert order == ["start", "body", "stop"]


# ----- Section 4: CLI integration -------------------------------------- #


def test_cli_invoke_tool_sync_runs_full_lifecycle() -> None:
    from a2kit.packages.cli.runtime import invoke_tool_sync

    order: list[str] = []
    app = App("t")
    app.on_startup(lambda a: order.append("start"))
    app.on_shutdown(lambda a: order.append("stop"))

    async def my_tool() -> dict:
        order.append("tool")
        return {"ok": True}

    invoke_tool_sync(my_tool, {}, fmt="json", app=app)
    assert order == ["start", "tool", "stop"]


def test_cli_invoke_tool_sync_runs_shutdown_on_tool_error() -> None:
    from a2kit.packages.cli.runtime import invoke_tool_sync

    order: list[str] = []
    app = App("t")
    app.on_startup(lambda a: order.append("start"))
    app.on_shutdown(lambda a: order.append("stop"))

    async def bad_tool() -> dict:
        order.append("tool")
        raise RuntimeError("tool failed")

    with pytest.raises(RuntimeError, match="tool failed"):
        invoke_tool_sync(bad_tool, {}, fmt="json", app=app)
    assert order == ["start", "tool", "stop"]


def test_cli_invoke_tool_sync_no_lifecycle_when_no_handlers() -> None:
    from a2kit.packages.cli.runtime import invoke_tool_sync

    app = App("t")  # no handlers

    async def t() -> dict:
        return {"ok": True}

    # Just ensure it doesn't crash and doesn't try to read lifecycle state.
    invoke_tool_sync(t, {}, fmt="json", app=app)


def test_cli_lifecycle_state_isolated_to_loop() -> None:
    """Verify state created in startup is bound to the same event loop that runs the tool body."""
    from a2kit.packages.cli.runtime import invoke_tool_sync

    captured: dict[str, object] = {}

    async def open_resource(a: App) -> None:
        captured["lock"] = asyncio.Lock()  # bound to running loop

    async def use_resource(a: App) -> None:
        # Same loop — must be acquirable.
        async with captured["lock"]:  # type: ignore[arg-type]
            pass

    app = App("t")
    app.on_startup(open_resource)

    async def my_tool() -> dict:
        await use_resource(app)
        return {"ok": True}

    invoke_tool_sync(my_tool, {}, fmt="json", app=app)


# ----- Wrapper sanity --------------------------------------------------- #


def test_singleton_wrapper_signature_passthrough() -> None:
    """Container introspection sees the user factory's signature, not __call__'s."""
    import inspect

    def factory(settings: _Settings) -> _Store:
        return _Store(settings)

    app = App("t")
    app.provide(_Settings, lambda: _Settings())
    app.singleton(_Store, factory)
    wrapper = app.container().providers()[_Store]
    assert isinstance(wrapper, _SingletonWrapper)
    sig = inspect.signature(wrapper)
    assert "settings" in sig.parameters
