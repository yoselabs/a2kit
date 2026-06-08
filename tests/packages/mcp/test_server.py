"""``build_mcp_server`` registration round-trip tests."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import a2kit
from a2kit.packages.mcp import build_mcp_server
from a2kit.testing import app_of


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


@pytest.fixture
def app() -> a2kit.App:
    return app_of("sample-app", _SampleRouter())


def test_build_mcp_server_returns_fastmcp(app: a2kit.App) -> None:
    from fastmcp import FastMCP

    server = build_mcp_server(app, code_mode=False)
    assert isinstance(server, FastMCP)
    assert server.name == "sample-app"


def test_tools_registered_with_a2kit_meta(app: a2kit.App) -> None:
    server = build_mcp_server(app, code_mode=False)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        assert "sample_ping" in tools
        ping = tools["sample_ping"]
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
    server = build_mcp_server(app, code_mode=False)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        rows = tools["sample_rows"]
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
    """An instance-decorator enricher wraps fn before FunctionTool.from_function;
    the framework translates raised exceptions to the registered AppError type."""
    from a2effect import AppError

    fired: list[Exception] = []

    class EnrichedError(AppError):
        kind = "infra"

    class R(a2kit.Router):
        slug = "r"
        name = "r"

        @a2kit.read()
        async def boom(self) -> dict[str, str]:
            raise RuntimeError("kaboom")

    router = R()

    @router.enricher
    def my_enricher(exc: RuntimeError) -> EnrichedError | None:
        fired.append(exc)
        return EnrichedError(f"enriched: {exc!s}")

    app = app_of("e", router)
    server = build_mcp_server(app, code_mode=False)

    async def _check() -> None:
        # NOTE: full wire-envelope rendering lands in Group 14 (MCP surface
        # rendering). For now we verify the EnricherStage translates the
        # raised RuntimeError into the registered AppError type.
        from fastmcp.exceptions import ToolError

        tools = {t.name: t for t in await server.list_tools()}
        bt = tools["r_boom"]
        with pytest.raises((ToolError, EnrichedError)):
            await bt.fn()  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them

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

    app = app_of("a", R())
    server = build_mcp_server(app, code_mode=False)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        assert {"r_sync_one", "r_async_one"}.issubset(tools.keys())

    asyncio.run(_check())


def test_init_does_not_export_more_than_build_mcp_server() -> None:
    import a2kit.packages.mcp as pkg

    assert pkg.__all__ == ["build_mcp_server"]
