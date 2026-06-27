"""Verification gate (ADR 0030, task 5.1): the collapsed pure stdio path.

After the three serve branches collapsed into one engine, plain `serve`
(stdio, no spoke, no services) runs the MCP surface through
`asyncio.run(_serve(...))` + `run_stdio_async()` with `own_app_lifecycle=False`,
instead of FastMCP's `.run("stdio")`. Reading proved the composition works *with*
the spoke; this is the one thing only a live round-trip can close — a real stdio
MCP server (the full CLI → `serve_process` → `_serve` path) answering
`tools/list` + a `call_tool`.
"""

from __future__ import annotations

import sys
import textwrap
from typing import Any

import pytest

_SERVER = textwrap.dedent(
    """
    import a2kit
    from a2kit.testing import app_of

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def echo(self, *, msg: str) -> dict:
            return {"msg": msg}

    # Full authored run path: App.serve(argv) -> a2kit.run -> CLI `serve`
    # (stdio default) -> serve_process -> _serve -> run_stdio_async.
    # --no-code-mode so the raw verb catalog is exposed directly (default
    # serve collapses to the code-execution surface per ADR 0013/0014).
    app_of("smoke", R()).serve(["serve", "--transport", "stdio", "--no-code-mode"])
    """
)


@pytest.mark.asyncio
async def test_plain_stdio_serve_answers_mcp_round_trip(tmp_path: Any) -> None:
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    script = tmp_path / "stdio_server.py"
    script.write_text(_SERVER)

    transport = StdioTransport(command=sys.executable, args=[str(script)])
    async with Client(transport) as client:
        tools = await client.list_tools()
        assert "demo_echo" in {t.name for t in tools}
        result = await client.call_tool("demo_echo", {"msg": "hi"})

    payload = result.data if getattr(result, "data", None) is not None else result.structured_content
    assert payload == {"msg": "hi"}
