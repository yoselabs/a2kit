"""v0.15 prep: `get_conn_factory` — the Annotated/Depends idiom for
connection injection. Replaces the v0.12 `*, info: ConnT` autodetect path.

Note: no `from __future__ import annotations` — the resolver inspects
runtime annotations via `typing.get_type_hints(include_extras=True)`. PEP
593 metadata only survives that round-trip when annotations evaluate at
runtime.
"""

from typing import Annotated

import pytest

import a2kit
from a2kit.contrib.connections import get_conn_factory
from a2kit.di import Depends
from a2kit.exceptions import ConnectionNotFound


class _Conn(a2kit.ConnectionConfig):
    url: str = "https://example.com"


async def test_get_conn_factory_resolves_saved_connection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("test-get-conn")
    store = app.connect(_Conn, config_dir=tmp_path)
    await store.save(_Conn(key=("prod",), url="https://prod.example.com"))

    get_conn = get_conn_factory(app, _Conn)

    class ShowRouter(a2kit.Router):
        pass

    @ShowRouter.tool()
    async def show(*, conn: Annotated[_Conn, Depends(get_conn)]) -> dict:
        return {"url": conn.url}

    app.use(ShowRouter)
    app._ensure_routers_applied()
    target = next(t for t in app.server._tool_manager.list_tools() if t.name == "show")
    out = await target.fn(connection="prod")
    assert out == {"url": "https://prod.example.com"}


async def test_get_conn_factory_unknown_key_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("test-unknown")
    app.connect(_Conn, config_dir=tmp_path)
    get_conn = get_conn_factory(app, _Conn)

    with pytest.raises(ConnectionNotFound):
        await get_conn(connection="nope")


async def test_get_conn_factory_unregistered_type_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = a2kit.App("test-unreg")
    # Different conn type registered.

    class _Other(a2kit.ConnectionConfig):
        x: str = "y"

    app.connect(_Other, config_dir=tmp_path)
    with pytest.raises(ValueError, match="no ConnectionStore for _Conn"):
        get_conn_factory(app, _Conn)


async def test_dependency_overrides_swaps_get_conn(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`app.dependency_overrides[get_conn] = fake` replaces the factory at
    tool-call time — the canonical test-fake pattern for v0.15."""
    app = a2kit.App("test-overrides")
    app.connect(_Conn, config_dir=tmp_path)
    get_conn = get_conn_factory(app, _Conn)

    class OverrideRouter(a2kit.Router):
        pass

    @OverrideRouter.tool()
    async def show(*, conn: Annotated[_Conn, Depends(get_conn)]) -> dict:
        return {"url": conn.url}

    app.use(OverrideRouter)

    async def fake_get_conn(*, connection: str) -> _Conn:  # noqa: ARG001
        return _Conn(key=("fake",), url="fake://override")

    app.dependency_overrides[get_conn] = fake_get_conn

    app._ensure_routers_applied()
    target = next(t for t in app.server._tool_manager.list_tools() if t.name == "show")
    # `connection=` is still required (forwarded as call_ctx) even though the
    # override ignores it.
    out = await target.fn(connection="anything")
    assert out == {"url": "fake://override"}
