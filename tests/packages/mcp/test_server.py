"""``build_mcp_server`` registration round-trip tests."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import a2kit
from a2kit.metadata import ListViewSettings
from a2kit.packages.mcp import build_mcp_server


class _SampleRouter(a2kit.Router):
    name = "sample"

    @a2kit.read("ping")
    async def ping(self, *, name: str = "world") -> dict[str, str]:
        return {"hello": name}

    @a2kit.list_("rows", list_view=ListViewSettings(default_fields=("id", "name"), page_size=2))
    async def rows(self) -> list[dict[str, Any]]:
        return [
            {"id": 1, "name": "a", "extra": "drop"},
            {"id": 2, "name": "b", "extra": "drop"},
            {"id": 3, "name": "c", "extra": "drop"},
        ]


@pytest.fixture
def app() -> a2kit.App:
    a = a2kit.App("sample-app")
    a.use(_SampleRouter())
    return a


def test_build_mcp_server_returns_fastmcp(app: a2kit.App) -> None:
    from fastmcp import FastMCP

    server = build_mcp_server(app)
    assert isinstance(server, FastMCP)
    assert server.name == "sample-app"


def test_tools_registered_with_a2kit_meta(app: a2kit.App) -> None:
    server = build_mcp_server(app)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        assert "ping" in tools
        ping = tools["ping"]
        meta = ping.meta or {}
        a2kit_meta = meta.get("a2kit")
        assert isinstance(a2kit_meta, dict)
        assert a2kit_meta["verb"] == "read"
        assert a2kit_meta["tool_name"] == "ping"
        assert "read" in a2kit_meta["tags"]
        assert a2kit_meta["router_slug"] == "sample"
        # enricher dropped (callable, non-serializable)
        assert "enricher" not in a2kit_meta
        # annotations serialized via model_dump
        ann = a2kit_meta["annotations"]
        assert isinstance(ann, dict)

    asyncio.run(_check())


def test_list_view_settings_round_trip(app: a2kit.App) -> None:
    server = build_mcp_server(app)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        rows = tools["rows"]
        a2kit_meta = (rows.meta or {})["a2kit"]
        lv = a2kit_meta["list_view"]
        assert list(lv["default_fields"]) == ["id", "name"]
        assert lv["page_size"] == 2

    asyncio.run(_check())


def test_forwards_fastmcp_kwargs(app: a2kit.App) -> None:
    """`auth=None` is the easy passthrough; the real test is that an arbitrary
    kwarg lands on `FastMCP.__init__` without a2kit translation."""
    server = build_mcp_server(app, instructions="test instructions", mask_error_details=True)
    assert server.instructions == "test instructions"


def test_unknown_fastmcp_kwarg_propagates(app: a2kit.App) -> None:
    with pytest.raises(TypeError):
        build_mcp_server(app, definitely_not_a_fastmcp_param=True)


def test_enricher_fires_before_registration() -> None:
    """An enricher attached to a tool must wrap before FunctionTool.from_function.

    Module-level fn (not a class method) so we can verify enricher fires when
    the wrapped fn is invoked directly without binding shenanigans.
    """
    fired: list[Exception] = []

    def my_enricher(exc: Exception, tool_name: str) -> Exception:
        fired.append(exc)
        return ValueError(f"enriched: {exc!s}")

    @a2kit.read("boom", enricher=my_enricher)
    async def boom() -> dict[str, str]:
        raise RuntimeError("kaboom")

    class R(a2kit.Router):
        name = "r"

    r = R()
    r._tools.append(boom)  # bypass class-method collection

    app = a2kit.App("e").use(r)
    server = build_mcp_server(app)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        bt = tools["boom"]
        with pytest.raises(ValueError, match="enriched: kaboom"):
            await bt.fn()

    asyncio.run(_check())
    assert len(fired) == 1


def test_sync_and_async_tools_both_register() -> None:
    class R(a2kit.Router):
        name = "r"

        @a2kit.read("sync_one")
        def sync_one(self) -> dict[str, int]:
            return {"x": 1}

        @a2kit.read("async_one")
        async def async_one(self) -> dict[str, int]:
            return {"x": 2}

    app = a2kit.App("a").use(R())
    server = build_mcp_server(app)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        assert {"sync_one", "async_one"}.issubset(tools.keys())

    asyncio.run(_check())


def test_init_does_not_export_more_than_build_mcp_server() -> None:
    import a2kit.packages.mcp as pkg

    assert pkg.__all__ == ["build_mcp_server"]
