"""BDD: code-mode wiring in `build_mcp_server` (code-execution-surface §4)."""

from __future__ import annotations

import pytest
from fastmcp import Client

import a2kit
from a2kit.packages.mcp.server import build_mcp_server


def _result_text(result: object) -> str:
    data = getattr(result, "data", None)
    return str(data if data is not None else getattr(result, "content", result))


@pytest.mark.asyncio
async def test_default_build_collapses_catalog(gate_app: a2kit.App) -> None:
    """`build_mcp_server(app)` with no `code_mode` argument installs code mode."""
    server = build_mcp_server(gate_app)
    async with Client(server) as c:
        names = sorted(t.name for t in await c.list_tools())
    assert names == ["execute", "get_schema", "search"]


@pytest.mark.asyncio
async def test_code_mode_off_lists_full_catalog(gate_app: a2kit.App) -> None:
    """`code_mode=False` leaves the real catalog listed and no `execute` tool."""
    server = build_mcp_server(gate_app, code_mode=False)
    async with Client(server) as c:
        names = sorted(t.name for t in await c.list_tools())
    assert "execute" not in names
    assert {"gate_ping", "gate_wipe", "gate_touch"} <= set(names)
    # A `cli`-tier tool is never on the MCP surface, code mode or not.
    assert "gate_cli_only" not in names


@pytest.mark.asyncio
async def test_real_tools_callable_by_name_under_code_mode(gate_app: a2kit.App) -> None:
    """Under code mode real tools vanish from `list_tools` but stay callable."""
    server = build_mcp_server(gate_app)
    async with Client(server) as c:
        listed = {t.name for t in await c.list_tools()}
        assert "gate_ping" not in listed
        result = await c.call_tool("gate_ping", {})
    assert "pong" in _result_text(result)
