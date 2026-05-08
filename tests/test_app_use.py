"""End-to-end tests for the v0.15 App surface.

Exercises `App.connect` + `App.use` + `App.run_server` + the
Annotated[Conn, Depends(get_conn)] resolution path through the
underlying MCPRunner / FastMCP server.
"""

from typing import Annotated

import pytest

import a2kit
from a2kit.contrib.connections import get_conn_factory
from a2kit.di import Depends


class _AppConn(a2kit.ConnectionInfo):
    url: str = "https://example.com"
    read_only: bool = False


# ---------------------------------------------------------------------------- #


def test_app_connect_returns_store(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("test")
    store = app.connect(_AppConn, config_dir=tmp_path)
    assert store.connection_class is _AppConn


def test_app_connect_rejects_double_register(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("test")
    app.connect(_AppConn, config_dir=tmp_path)
    with pytest.raises(ValueError, match="already has a ConnectionStore"):
        app.connect(_AppConn, config_dir=tmp_path)


def test_app_use_rejects_non_router() -> None:
    app = a2kit.App("test")
    with pytest.raises(TypeError, match="only accepts Router"):
        app.use("not-a-router")  # type: ignore[arg-type]


async def test_app_use_router_class_and_instance(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("test")
    app.connect(_AppConn, config_dir=tmp_path)

    class ARouter(a2kit.Router):
        pass

    @ARouter.read()
    async def hello() -> dict:  # noqa: RUF029
        return {"ok": True}

    # class form
    app.use(ARouter)

    class BRouter(a2kit.Router):
        pass

    @BRouter.read()
    async def world() -> dict:  # noqa: RUF029
        return {"ok": True}

    # instance form
    app.use(BRouter())

    app._ensure_routers_applied()
    names = {t.name for t in app.server._tool_manager.list_tools()}
    assert "hello" in names
    assert "world" in names


# ---------------------------------------------------------------------------- #
# Annotated/Depends end-to-end                                                  #
# ---------------------------------------------------------------------------- #


async def test_annotated_depends_resolves_with_saved_connection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("e2e")
    store = app.connect(_AppConn, config_dir=tmp_path)
    await store.save(_AppConn(key=("prod",), url="https://prod.example"))

    get_conn = get_conn_factory(app, _AppConn)

    class FooRouter(a2kit.Router):
        pass

    @FooRouter.read()
    async def show(*, conn: Annotated[_AppConn, Depends(get_conn)]) -> dict:
        return {"url": conn.url}

    app.use(FooRouter)
    app._ensure_routers_applied()
    target = next(t for t in app.server._tool_manager.list_tools() if t.name == "show")
    out = await target.fn(connection="prod")
    assert out == {"url": "https://prod.example"}


async def test_dependency_overrides_swap_factory(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("override")
    app.connect(_AppConn, config_dir=tmp_path)
    get_conn = get_conn_factory(app, _AppConn)

    async def fake_get_conn(*, connection: str) -> _AppConn:  # noqa: ARG001
        return _AppConn(key=("fake",), url="https://fake")

    app.dependency_overrides[get_conn] = fake_get_conn

    class FooRouter(a2kit.Router):
        pass

    @FooRouter.read()
    async def show(*, conn: Annotated[_AppConn, Depends(get_conn)]) -> dict:
        return {"url": conn.url}

    app.use(FooRouter)
    app._ensure_routers_applied()
    target = next(t for t in app.server._tool_manager.list_tools() if t.name == "show")
    out = await target.fn(connection="anything")
    assert out == {"url": "https://fake"}


# ---------------------------------------------------------------------------- #
# Transitive Depends                                                           #
# ---------------------------------------------------------------------------- #


class _Store:
    def __init__(self, conn: _AppConn) -> None:
        self.conn = conn


async def test_transitive_annotated_depends(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("transitive")
    store = app.connect(_AppConn, config_dir=tmp_path)
    await store.save(_AppConn(key=("prod",), url="https://prod"))
    get_conn = get_conn_factory(app, _AppConn)

    async def get_store(*, conn: Annotated[_AppConn, Depends(get_conn)]) -> _Store:
        return _Store(conn)

    class StoreRouter(a2kit.Router):
        pass

    @StoreRouter.read()
    async def use_store(*, st: Annotated[_Store, Depends(get_store)]) -> dict:
        return {"url": st.conn.url}

    app.use(StoreRouter)
    app._ensure_routers_applied()
    target = next(t for t in app.server._tool_manager.list_tools() if t.name == "use_store")
    out = await target.fn(connection="prod")
    assert out == {"url": "https://prod"}


# ---------------------------------------------------------------------------- #
# WriteEnforce middleware on read-only connection                              #
# ---------------------------------------------------------------------------- #


async def test_write_enforce_blocks_readonly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("write-enforce")
    store = app.connect(_AppConn, config_dir=tmp_path)
    await store.save(_AppConn(key=("ro",), url="https://x", read_only=True))
    get_conn = get_conn_factory(app, _AppConn)

    class WRouter(a2kit.Router):
        pass

    @WRouter.write()
    async def mutate(*, conn: Annotated[_AppConn, Depends(get_conn)]) -> dict:  # noqa: ARG001
        return {"mutated": True}

    app.use(WRouter)
    app._ensure_routers_applied()
    target = next(t for t in app.server._tool_manager.list_tools() if t.name == "mutate")

    with pytest.raises(a2kit.WriteNotAllowed):
        await target.fn(connection="ro")


async def test_write_enforce_allows_writable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("write-ok")
    store = app.connect(_AppConn, config_dir=tmp_path)
    await store.save(_AppConn(key=("rw",), url="https://x", read_only=False))
    get_conn = get_conn_factory(app, _AppConn)

    class WRouter(a2kit.Router):
        pass

    @WRouter.write()
    async def mutate(*, conn: Annotated[_AppConn, Depends(get_conn)]) -> dict:  # noqa: ARG001
        return {"mutated": True}

    app.use(WRouter)
    app._ensure_routers_applied()
    target = next(t for t in app.server._tool_manager.list_tools() if t.name == "mutate")
    out = await target.fn(connection="rw")
    assert out == {"mutated": True}


# ---------------------------------------------------------------------------- #
# CLI surface                                                                   #
# ---------------------------------------------------------------------------- #


def test_app_cli_includes_serve_and_tool_subcommands(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("cli-test")
    app.connect(_AppConn, config_dir=tmp_path)

    class SomeRouter(a2kit.Router):
        pass

    @SomeRouter.read()
    async def some_tool() -> dict:  # noqa: RUF029
        return {}

    app.use(SomeRouter)
    cli = app.cli
    cmd_names = set(cli.commands)
    assert "serve" in cmd_names
    assert "some_tool" in cmd_names
    assert "login" in cmd_names  # from build_cli (store registered)


def test_app_cli_no_store_skips_login() -> None:
    app = a2kit.App("storeless")
    cli = app.cli
    assert "serve" in cli.commands
    assert "login" not in cli.commands


def test_reserved_subcommand_collision_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("collision")
    app.connect(_AppConn, config_dir=tmp_path)

    class XRouter(a2kit.Router):
        pass

    @XRouter.read(tool_name="serve")
    async def x() -> dict:  # noqa: RUF029
        return {}

    app.use(XRouter)
    with pytest.raises(ValueError, match=r"[Rr]eserved"):
        _ = app.cli
