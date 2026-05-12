"""App lifecycle + DI tests for v0.31 (lifespan-over-lifecycle-hooks).

Covers:
- Sync resolution end-to-end.
- App.singleton sync-only factories (async rejected for ``provide``).
- Two-app singleton isolation.
- Lifespan: signature validation, App.lifespan_cm composition,
  startup-failure propagation, shutdown-failure swallow.
- MCP lifespan adapter wires the App's lifespan into FastMCP.
- CLI lifecycle integration runs the lifespan around the tool body.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import pytest

from a2kit.app import App, UNRESOLVED
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
    """Async singleton factories are accepted; awaited on first resolution."""

    async def factory() -> _State:
        return _State("async")

    app = App("t")
    app.singleton(_State, factory)
    assert app.has_singleton(_State)


def test_provide_async_factory_rejected() -> None:
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


# ----- Section 3: lifespan shape + construction ------------------------- #


def test_sync_lifespan_rejected_at_construction() -> None:
    def lifespan(app):  # noqa: ANN001, ARG001 -- intentional sync def
        return None

    with pytest.raises(TypeError, match="async def"):
        App("t", lifespan=lifespan)


def test_async_lifespan_accepted_at_construction() -> None:
    @asynccontextmanager
    async def lifespan(app):
        yield

    app = App("t", lifespan=lifespan)
    assert app.has_lifespan() is True


def test_no_lifespan_uses_nullcontext() -> None:
    """App without a lifespan returns a context manager that no-ops."""
    app = App("t")

    async def go() -> None:
        cm = app.lifespan_cm()
        async with cm:
            pass

    asyncio.run(go())


@pytest.mark.asyncio
async def test_lifespan_body_runs_around_yield() -> None:
    order: list[str] = []

    @asynccontextmanager
    async def lifespan(app):
        order.append("enter")
        try:
            yield
        finally:
            order.append("exit")

    app = App("t", lifespan=lifespan)
    async with app.lifespan_cm():
        order.append("body")
    assert order == ["enter", "body", "exit"]


@pytest.mark.asyncio
async def test_lifespan_body_resolves_singleton_explicitly() -> None:
    captured: list[_State] = []

    @asynccontextmanager
    async def lifespan(app):
        s = await app.container().aresolve(_State)
        captured.append(s)
        yield

    app = App("t", lifespan=lifespan)
    app.singleton(_State, lambda: _State("from-di"))
    async with app.lifespan_cm():
        pass
    assert len(captured) == 1
    assert captured[0].label == "from-di"


@pytest.mark.asyncio
async def test_lifespan_startup_failure_propagates() -> None:
    @asynccontextmanager
    async def lifespan(app):
        msg = "boom"
        raise RuntimeError(msg)
        yield  # unreachable

    app = App("t", lifespan=lifespan)
    with pytest.raises(RuntimeError, match="boom"):
        async with app.lifespan_cm():
            pass


@pytest.mark.asyncio
async def test_warm_async_singletons_resolves_async_factories() -> None:
    async def factory() -> _State:
        return _State("warmed")

    app = App("t")
    app.singleton(_State, factory)
    assert app.singletons()[_State] is UNRESOLVED
    await app.warm_async_singletons()
    assert app.singletons()[_State].label == "warmed"


@pytest.mark.asyncio
async def test_warm_async_singletons_idempotent() -> None:
    calls = {"n": 0}

    async def factory() -> _State:
        calls["n"] += 1
        return _State("warmed")

    app = App("t")
    app.singleton(_State, factory)
    await app.warm_async_singletons()
    await app.warm_async_singletons()
    assert calls["n"] == 1


# ----- Section 4: compose helper --------------------------------------- #


@pytest.mark.asyncio
async def test_compose_runs_in_declared_order_unwinds_reverse() -> None:
    from a2kit.lifespan import compose

    order: list[str] = []

    def make(name):  # noqa: ANN001, ANN202
        @asynccontextmanager
        async def _ls(app):
            order.append(f"{name}-enter")
            try:
                yield
            finally:
                order.append(f"{name}-exit")

        _ls.__name__ = name
        return _ls

    composed = compose(make("L1"), make("L2"), make("L3"))
    app = App("t")
    async with composed(app):
        order.append("body")
    assert order == [
        "L1-enter",
        "L2-enter",
        "L3-enter",
        "body",
        "L3-exit",
        "L2-exit",
        "L1-exit",
    ]


@pytest.mark.asyncio
async def test_compose_shutdown_failure_logged_and_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from a2kit.lifespan import compose

    order: list[str] = []

    @asynccontextmanager
    async def l1(app):
        order.append("L1-enter")
        try:
            yield
        finally:
            order.append("L1-exit")

    @asynccontextmanager
    async def l2(app):
        order.append("L2-enter")
        try:
            yield
        finally:
            order.append("L2-exit")
            raise RuntimeError("close failed")

    @asynccontextmanager
    async def l3(app):
        order.append("L3-enter")
        try:
            yield
        finally:
            order.append("L3-exit")

    composed = compose(l1, l2, l3)
    app = App("t")
    with caplog.at_level(logging.ERROR, logger="a2kit.lifecycle"):
        async with composed(app):
            order.append("body")
    # All entered, all exits ran, L1 ran after L2's exit failed.
    assert "L1-enter" in order
    assert "L2-enter" in order
    assert "L3-enter" in order
    assert order.index("L3-exit") < order.index("L2-exit") < order.index("L1-exit")
    assert any("shutdown" in rec.message.lower() for rec in caplog.records)


@pytest.mark.asyncio
async def test_compose_mid_stack_startup_failure_unwinds_prior() -> None:
    from a2kit.lifespan import compose

    order: list[str] = []

    @asynccontextmanager
    async def l1(app):
        order.append("L1-enter")
        try:
            yield
        finally:
            order.append("L1-exit")

    @asynccontextmanager
    async def l2_raises(app):
        order.append("L2-enter-attempt")
        msg = "mid-stack boom"
        raise RuntimeError(msg)
        yield

    @asynccontextmanager
    async def l3(app):
        order.append("L3-enter")
        try:
            yield
        finally:
            order.append("L3-exit")

    composed = compose(l1, l2_raises, l3)
    app = App("t")
    with pytest.raises(RuntimeError, match="mid-stack boom"):
        async with composed(app):
            pass
    assert "L1-enter" in order
    assert "L1-exit" in order
    assert "L3-enter" not in order


# ----- Section 5: MCP lifespan adapter --------------------------------- #


@pytest.mark.asyncio
async def test_mcp_adapter_back_reference_and_runs_app_lifespan() -> None:
    from a2kit.packages.mcp.server import _build_fastmcp_lifespan

    order: list[str] = []

    @asynccontextmanager
    async def app_lifespan(app):
        order.append("a2k_start")
        try:
            yield
        finally:
            order.append("a2k_stop")

    app = App("t", lifespan=app_lifespan)

    class _Server:
        pass

    server = _Server()

    @asynccontextmanager
    async def user_lifespan(srv):
        order.append("user_enter")
        try:
            yield {"user": True}
        finally:
            order.append("user_exit")

    adapter = _build_fastmcp_lifespan(app, user_lifespan)
    async with adapter(server) as state:
        order.append("body")
        assert state == {"user": True}
    assert server._a2kit_app is app
    assert order == ["a2k_start", "user_enter", "body", "user_exit", "a2k_stop"]


@pytest.mark.asyncio
async def test_mcp_adapter_without_user_lifespan() -> None:
    from a2kit.packages.mcp.server import _build_fastmcp_lifespan

    order: list[str] = []

    @asynccontextmanager
    async def app_lifespan(app):
        order.append("start")
        try:
            yield
        finally:
            order.append("stop")

    app = App("t", lifespan=app_lifespan)

    class _Server:
        pass

    adapter = _build_fastmcp_lifespan(app, None)
    server = _Server()
    async with adapter(server) as state:
        assert state is None
        order.append("body")
    assert server._a2kit_app is app
    assert order == ["start", "body", "stop"]


# ----- Section 6: CLI integration --------------------------------------- #


def test_cli_invoke_tool_sync_runs_full_lifecycle() -> None:
    from a2kit.packages.cli.runtime import invoke_tool_sync

    order: list[str] = []

    @asynccontextmanager
    async def lifespan(app):
        order.append("start")
        try:
            yield
        finally:
            order.append("stop")

    app = App("t", lifespan=lifespan)

    async def my_tool() -> dict:
        order.append("tool")
        return {"ok": True}

    invoke_tool_sync(my_tool, {}, fmt="json", app=app)
    assert order == ["start", "tool", "stop"]


def test_cli_invoke_tool_sync_runs_shutdown_on_tool_error() -> None:
    from a2kit.packages.cli.runtime import invoke_tool_sync

    order: list[str] = []

    @asynccontextmanager
    async def lifespan(app):
        order.append("start")
        try:
            yield
        finally:
            order.append("stop")

    app = App("t", lifespan=lifespan)

    async def bad_tool() -> dict:
        order.append("tool")
        msg = "tool failed"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="tool failed"):
        invoke_tool_sync(bad_tool, {}, fmt="json", app=app)
    assert order == ["start", "tool", "stop"]


def test_cli_invoke_tool_sync_no_lifecycle_when_no_lifespan() -> None:
    from a2kit.packages.cli.runtime import invoke_tool_sync

    app = App("t")

    async def t() -> dict:
        return {"ok": True}

    invoke_tool_sync(t, {}, fmt="json", app=app)


def test_cli_lifecycle_state_isolated_to_loop() -> None:
    """State opened in the lifespan body is bound to the loop the tool body uses."""
    from a2kit.packages.cli.runtime import invoke_tool_sync

    captured: dict[str, object] = {}

    @asynccontextmanager
    async def lifespan(app):
        captured["lock"] = asyncio.Lock()
        yield

    app = App("t", lifespan=lifespan)

    async def use_resource() -> None:
        async with captured["lock"]:  # type: ignore[arg-type]
            pass

    async def my_tool() -> dict:
        await use_resource()
        return {"ok": True}

    invoke_tool_sync(my_tool, {}, fmt="json", app=app)
