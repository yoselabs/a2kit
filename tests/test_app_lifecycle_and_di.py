"""App lifecycle + DI tests for v0.27 (di-sync-and-unleak).

Covers:
- Sync resolution end-to-end.
- App.singleton sync-only factories (async rejected).
- Two-app singleton isolation.
- DI-aware lifecycle hooks: handlers take typed kwargs resolved via container.
- Ordering / failure semantics for startup + shutdown.
- MCP lifespan merge ordering.
- CLI lifecycle integration.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from a2kit.app import App, UNRESOLVED, dispatch_shutdown, dispatch_startup
from a2kit.packages.di.container import UnresolvableType


class _State:
    def __init__(self, label: str = "x") -> None:
        self.label = label


class _Settings:
    pass


class _Store:
    def __init__(self, settings: _Settings) -> None:
        self.settings = settings


# ----- Section 1: sync resolve end-to-end ------------------------------- #


def test_resolve_simple_chain_sync() -> None:
    app = App("t")
    app.provide(_Settings, lambda: _Settings())
    app.provide(_Store, _Store)
    store = app.container().resolve(_Store)
    assert isinstance(store, _Store)
    assert isinstance(store.settings, _Settings)


def test_container_is_non_optional_after_construction() -> None:
    """v0.27: container() returns Container (never None) after App.__init__."""
    app = App("t")
    c = app.container()
    assert c is not None
    # Same container across calls (eager-init).
    assert app.container() is c


def test_resolve_unresolvable_raises() -> None:
    app = App("t")
    with pytest.raises(UnresolvableType):
        app.container().resolve(_Settings)


# ----- Section 2: singletons (sync only) -------------------------------- #


def test_singleton_method_form_caches() -> None:
    calls = {"n": 0}

    def factory() -> _State:
        calls["n"] += 1
        return _State(f"build{calls['n']}")

    app = App("t")
    app.singleton(_State, factory)
    a = app.container().resolve(_State)
    b = app.container().resolve(_State)
    assert a is b
    assert calls["n"] == 1


def test_singleton_decorator_form() -> None:
    app = App("t")

    @app.singleton(_State)
    def make_state() -> _State:
        return _State("decorated")

    s = app.container().resolve(_State)
    assert s.label == "decorated"
    assert callable(make_state)


def test_two_apps_independent_singletons() -> None:
    app_a = App("a")
    app_b = App("b")
    app_a.singleton(_State, lambda: _State("A"))
    app_b.singleton(_State, lambda: _State("B"))
    sa = app_a.container().resolve(_State)
    sb = app_b.container().resolve(_State)
    assert sa is not sb
    assert sa.label == "A"
    assert sb.label == "B"


def test_singleton_async_factory_accepted_at_registration() -> None:
    """Async singleton factories are accepted; awaited on first resolution.

    See `tests/test_singleton_async_factories.py` for the full behaviour
    suite — this pins the registration-side contract only."""

    async def factory() -> _State:
        return _State("async")

    app = App("t")
    app.singleton(_State, factory)
    assert app.has_singleton(_State)


def test_provide_async_factory_rejected() -> None:
    """Same rule applies to ``provide`` factories."""

    async def factory() -> _Settings:
        return _Settings()

    app = App("t")
    with pytest.raises(ValueError, match="async"):
        app.provide(_Settings, factory)


def test_has_singleton_and_singletons_introspection() -> None:
    app = App("t")
    app.singleton(_State, lambda: _State())
    assert app.has_singleton(_State) is True
    snap = app.singletons()
    assert _State in snap
    assert snap[_State] is UNRESOLVED
    app.container().resolve(_State)
    snap2 = app.singletons()
    assert isinstance(snap2[_State], _State)


def test_singleton_chain_with_provide() -> None:
    """Singleton can depend on provide-registered types; deps resolve per dispatch."""
    app = App("t")
    app.provide(_Settings, lambda: _Settings())

    def make_store(settings: _Settings) -> _Store:
        return _Store(settings)

    app.singleton(_Store, make_store)
    a = app.container().resolve(_Store)
    b = app.container().resolve(_Store)
    assert a is b
    assert isinstance(a.settings, _Settings)


def test_provide_then_singleton_last_write_wins() -> None:
    app = App("t")
    app.provide(_State, lambda: _State("via_provide"))
    app.singleton(_State, lambda: _State("via_singleton"))
    a = app.container().resolve(_State)
    b = app.container().resolve(_State)
    assert a is b
    assert a.label == "via_singleton"


# ----- Section 3: lifecycle dispatch is DI-aware ------------------------ #


@pytest.mark.asyncio
async def test_startup_runs_in_registration_order() -> None:
    order: list[str] = []
    app = App("t")
    app.on_startup(lambda: order.append("h1"))

    @app.on_startup
    async def h2() -> None:
        order.append("h2")

    app.on_startup(lambda: order.append("h3"))
    await dispatch_startup(app)
    assert order == ["h1", "h2", "h3"]


@pytest.mark.asyncio
async def test_shutdown_runs_in_reverse_order() -> None:
    order: list[str] = []
    app = App("t")
    app.on_shutdown(lambda: order.append("s1"))
    app.on_shutdown(lambda: order.append("s2"))
    app.on_shutdown(lambda: order.append("s3"))
    await dispatch_shutdown(app)
    assert order == ["s3", "s2", "s1"]


@pytest.mark.asyncio
async def test_startup_resolves_typed_kwargs() -> None:
    """v0.27: lifecycle handlers go through DI like @health_check does."""
    app = App("t")
    app.singleton(_State, lambda: _State("from-di"))
    captured: list[_State] = []

    @app.on_startup
    async def warm(state: _State) -> None:
        captured.append(state)

    await dispatch_startup(app)
    assert len(captured) == 1
    assert captured[0].label == "from-di"


@pytest.mark.asyncio
async def test_shutdown_resolves_typed_kwargs() -> None:
    app = App("t")
    app.singleton(_State, lambda: _State("shutdown"))
    seen: list[_State] = []

    @app.on_shutdown
    async def close(state: _State) -> None:
        seen.append(state)

    # Trigger singleton creation so shutdown sees the same instance.
    s = app.container().resolve(_State)
    await dispatch_shutdown(app)
    assert seen == [s]


@pytest.mark.asyncio
async def test_startup_failure_aborts_subsequent_handlers() -> None:
    order: list[str] = []
    app = App("t")
    app.on_startup(lambda: order.append("h1"))

    def boom() -> None:
        order.append("boom")
        raise RuntimeError("startup failed")

    app.on_startup(boom)
    app.on_startup(lambda: order.append("h3"))

    with pytest.raises(RuntimeError, match="startup failed"):
        await dispatch_startup(app)
    assert order == ["h1", "boom"]


@pytest.mark.asyncio
async def test_shutdown_failure_logged_and_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    order: list[str] = []
    app = App("t")
    app.on_shutdown(lambda: order.append("s1"))

    def bad() -> None:
        order.append("bad")
        raise RuntimeError("close failed")

    app.on_shutdown(bad)
    app.on_shutdown(lambda: order.append("s3"))

    with caplog.at_level(logging.ERROR, logger="a2kit.lifecycle"):
        await dispatch_shutdown(app)
    assert order == ["s3", "bad", "s1"]
    assert any("shutdown handler" in rec.message for rec in caplog.records)


def test_on_startup_and_on_shutdown_decorator_form() -> None:
    app = App("t")

    @app.on_startup
    async def boot() -> None:
        pass

    @app.on_shutdown
    async def quit_() -> None:
        pass

    assert boot in app._startup_handlers
    assert quit_ in app._shutdown_handlers
    assert callable(boot) and callable(quit_)


def test_has_lifecycle_handlers_reflects_registration() -> None:
    app = App("t")
    assert app.has_lifecycle_handlers() is False
    app.on_startup(lambda: None)
    assert app.has_lifecycle_handlers() is True


# ----- Section 4: MCP lifespan merge ------------------------------------ #


@pytest.mark.asyncio
async def test_mcp_merge_lifespan_runs_a2kit_around_user() -> None:
    from contextlib import asynccontextmanager

    from a2kit.packages.mcp.server import _merge_lifespan

    order: list[str] = []
    app = App("t")
    app.on_startup(lambda: order.append("a2k_start"))
    app.on_shutdown(lambda: order.append("a2k_stop"))

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
    app.on_startup(lambda: order.append("start"))
    app.on_shutdown(lambda: order.append("stop"))

    merged = _merge_lifespan(app, None)
    async with merged(server=None) as state:
        assert state is None
        order.append("body")
    assert order == ["start", "body", "stop"]


# ----- Section 5: CLI integration --------------------------------------- #


def test_cli_invoke_tool_sync_runs_full_lifecycle() -> None:
    from a2kit.packages.cli.runtime import invoke_tool_sync

    order: list[str] = []
    app = App("t")
    app.on_startup(lambda: order.append("start"))
    app.on_shutdown(lambda: order.append("stop"))

    async def my_tool() -> dict:
        order.append("tool")
        return {"ok": True}

    invoke_tool_sync(my_tool, {}, fmt="json", app=app)
    assert order == ["start", "tool", "stop"]


def test_cli_invoke_tool_sync_runs_shutdown_on_tool_error() -> None:
    from a2kit.packages.cli.runtime import invoke_tool_sync

    order: list[str] = []
    app = App("t")
    app.on_startup(lambda: order.append("start"))
    app.on_shutdown(lambda: order.append("stop"))

    async def bad_tool() -> dict:
        order.append("tool")
        raise RuntimeError("tool failed")

    with pytest.raises(RuntimeError, match="tool failed"):
        invoke_tool_sync(bad_tool, {}, fmt="json", app=app)
    assert order == ["start", "tool", "stop"]


def test_cli_invoke_tool_sync_no_lifecycle_when_no_handlers() -> None:
    from a2kit.packages.cli.runtime import invoke_tool_sync

    app = App("t")

    async def t() -> dict:
        return {"ok": True}

    invoke_tool_sync(t, {}, fmt="json", app=app)


def test_cli_lifecycle_state_isolated_to_loop() -> None:
    """State created in startup is bound to the loop that runs the tool body."""
    from a2kit.packages.cli.runtime import invoke_tool_sync

    captured: dict[str, object] = {}

    async def open_resource() -> None:
        captured["lock"] = asyncio.Lock()

    async def use_resource() -> None:
        async with captured["lock"]:  # type: ignore[arg-type]
            pass

    app = App("t")
    app.on_startup(open_resource)

    async def my_tool() -> dict:
        await use_resource()
        return {"ok": True}

    invoke_tool_sync(my_tool, {}, fmt="json", app=app)
