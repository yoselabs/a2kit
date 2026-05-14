"""Opt-in stdio subprocess smoke for the transport-parity matrix.

Gated on ``A2KIT_SLOW_TESTS=1`` because spawning a subprocess +
stdio JSON-RPC framing is slower than the in-memory FastMCP client
used by ``tests/test_transport_parity.py``.

This test exists to canary the JSON-RPC framing layer **below** the
tool dispatcher. The wrapper-chain bug fixed by
``fix-mcp-dispatch-strips-ctx`` lives entirely above that boundary
and is exercised by the in-memory matrix; this file just confirms
the framing doesn't independently regress.
"""

from __future__ import annotations

import asyncio
import os
import sys
import textwrap

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("A2KIT_SLOW_TESTS") != "1",
    reason="opt-in slow test; set A2KIT_SLOW_TESTS=1 to enable",
)


_SERVER_SCRIPT = textwrap.dedent(
    '''
    """In-process MCP server for the stdio parity smoke."""
    import a2kit


    class _State:
        tag = "S"


    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def tool_both(
            self, *, msg: str, state: _State, ctx: a2kit.ToolContext
        ) -> dict:
            return {"msg": msg, "state_tag": state.tag, "has_ctx": ctx is not None}

        tools = (tool_both,)


    if __name__ == "__main__":
        app = a2kit.App("parity-stdio")
        app.add_router(R())
        app.provide(_State, lambda: _State())
        a2kit.run(app)
    '''
).strip()


@pytest.mark.asyncio
async def test_stdio_smoke_tool_both_round_trips(tmp_path) -> None:
    """Spawn an MCP server subprocess, invoke tool_both via stdio, assert payload."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_py = tmp_path / "_parity_stdio_server.py"
    server_py.write_text(_SERVER_SCRIPT)

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_py), "demo", "serve"],
        env={**os.environ},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("tool_both", {"msg": "x"})

    # Extract structured payload regardless of MCP SDK version.
    text_block = next(
        (b for b in result.content if getattr(b, "type", None) == "text"),
        None,
    )
    assert text_block is not None
    import json as _json

    payload = _json.loads(text_block.text)  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them
    assert payload == {"msg": "x", "state_tag": "S", "has_ctx": True}


# Silence unused-import warnings when test is skipped at module level.
_ = asyncio
