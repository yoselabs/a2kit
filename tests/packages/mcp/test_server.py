"""``build_mcp_server`` registration round-trip tests."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import a2kit
from a2kit.packages.mcp import build_mcp_server


class _SampleRouter(a2kit.Router):
    slug = "sample"
    name = "sample"

    @a2kit.read()
    async def ping(self, *, name: str = "world") -> dict[str, str]:
        return {"hello": name}

    @a2kit.list_("id", "name", page_size=2)
    async def rows(self) -> list[dict[str, Any]]:
        return [
            {"id": 1, "name": "a", "extra": "drop"},
            {"id": 2, "name": "b", "extra": "drop"},
            {"id": 3, "name": "c", "extra": "drop"},
        ]

    tools = (
        ping,
        rows,
    )


@pytest.fixture
def app() -> a2kit.App:
    a = a2kit.App("sample-app")
    a.add_router(_SampleRouter())
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
        assert a2kit_meta["extras"]["router_slug"] == "sample"
        # report_type is dropped from wire (non-JSON-serializable)
        assert "report_type" not in a2kit_meta["extras"]
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
        lv = a2kit_meta["extras"]["list_view"]
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
    """A class-attribute enricher must wrap fn before FunctionTool.from_function."""
    fired: list[Exception] = []

    def my_enricher(exc: Exception) -> str | None:
        fired.append(exc)
        return f"enriched: {exc!s}"

    class R(a2kit.Router):
        slug = "r"
        name = "r"
        enrichers = [my_enricher]

        @a2kit.read()
        async def boom(self) -> dict[str, str]:
            raise RuntimeError("kaboom")

        tools = (boom,)

    app = a2kit.App("e").add_router(R())
    server = build_mcp_server(app)

    async def _check() -> None:
        import json as _json

        from fastmcp.exceptions import ToolError

        tools = {t.name: t for t in await server.list_tools()}
        bt = tools["boom"]
        # Enricher runs innermost; the outermost wire-error envelope
        # then wraps the enriched RuntimeError into ToolError(json).
        with pytest.raises(ToolError) as ei:
            await bt.fn()
        payload = _json.loads(str(ei.value))
        assert payload["class"] == "RuntimeError"
        assert payload["message"] == "enriched: kaboom"

    asyncio.run(_check())
    assert len(fired) == 1


def test_sync_and_async_tools_both_register() -> None:
    class R(a2kit.Router):
        slug = "r"
        name = "r"

        @a2kit.read()
        def sync_one(self) -> dict[str, int]:
            return {"x": 1}

        @a2kit.read()
        async def async_one(self) -> dict[str, int]:
            return {"x": 2}

        tools = (
            sync_one,
            async_one,
        )

    app = a2kit.App("a").add_router(R())
    server = build_mcp_server(app)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        assert {"sync_one", "async_one"}.issubset(tools.keys())

    asyncio.run(_check())


def test_init_does_not_export_more_than_build_mcp_server() -> None:
    import a2kit.packages.mcp as pkg

    assert pkg.__all__ == ["build_mcp_server"]
