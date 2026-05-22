"""BDD: capability-gating of the code-execution sandbox (code-execution-surface §3)."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import a2kit
from a2kit.packages.mcp.server import build_mcp_server


def _result_text(result: object) -> str:
    data = getattr(result, "data", None)
    return str(data if data is not None else getattr(result, "content", result))


@pytest.mark.asyncio
async def test_non_destructive_tools_reachable_from_sandbox(gate_app: a2kit.App) -> None:
    """Read and non-destructive write tools are callable from `execute`."""
    server = build_mcp_server(gate_app)
    async with Client(server) as c:
        ping = await c.call_tool("execute", {"code": 'await call_tool("ping", {})'})
        touch = await c.call_tool("execute", {"code": 'await call_tool("touch", {})'})
    assert "pong" in _result_text(ping)
    assert "touched" in _result_text(touch)


@pytest.mark.asyncio
async def test_destructive_tool_gated_by_default(gate_app: a2kit.App) -> None:
    """A `destructive` tool is unreachable from the sandbox without an operator grant."""
    server = build_mcp_server(gate_app)
    async with Client(server) as c:
        with pytest.raises(ToolError):
            await c.call_tool("execute", {"code": 'await call_tool("wipe", {})'})


@pytest.mark.asyncio
async def test_operator_grant_opens_destructive(gate_app: a2kit.App) -> None:
    """`code_mode_allow_destructive=True` makes destructive tools reachable."""
    server = build_mcp_server(gate_app, code_mode_allow_destructive=True)
    async with Client(server) as c:
        result = await c.call_tool("execute", {"code": 'await call_tool("wipe", {})'})
    assert "wiped" in _result_text(result)


@pytest.mark.asyncio
async def test_search_hides_destructive_tool(gate_app: a2kit.App) -> None:
    """Discovery (`search`) does not surface gated destructive tools."""
    server = build_mcp_server(gate_app)
    async with Client(server) as c:
        found = await c.call_tool("search", {"query": "write", "detail": "full"})
    text = _result_text(found)
    assert "touch" in text
    assert "wipe" not in text


@pytest.mark.asyncio
async def test_execute_has_no_self_grant_argument(gate_app: a2kit.App) -> None:
    """The agent cannot self-grant — `execute` takes only `code`."""
    server = build_mcp_server(gate_app)
    async with Client(server) as c:
        tools = {t.name: t for t in await c.list_tools()}
    props = set(tools["execute"].inputSchema.get("properties", {}))
    assert props == {"code"}
