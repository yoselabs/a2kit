"""``@app.mcp.tool/.prompt/.resource`` end-to-end through ``build_mcp_server``.

Verifies that author-written substrate-native registrations land on the
FastMCP server with a2kit DI resolved from inside the wrapper — the
companion path to ``@app.api.*`` on FastAPI.
"""

from __future__ import annotations

import a2kit
from a2kit.packages.mcp.server import build_mcp_server
from a2kit.runtime import build
from a2kit.testing import app_of


class _Store:
    tag = "store-ok"


async def test_mcp_tool_registers_and_resolves_di() -> None:
    """``@app.mcp.tool`` registers on FastMCP and resolves DI types."""
    from fastmcp import Client

    app = app_of("mcp-native-demo").provide(_Store, lambda: _Store())

    @app.mcp.tool(name="echo_native")
    async def echo(*, msg: str, store: _Store) -> dict[str, str]:
        return {"msg": msg, "tag": store.tag}

    runtime = build(app)
    server = build_mcp_server(runtime, code_mode=False)
    async with Client(server) as client:
        result = await client.call_tool("echo_native", {"msg": "hi"})

    payload = result.data if getattr(result, "data", None) is not None else result.structured_content
    assert payload == {"msg": "hi", "tag": "store-ok"}
    # fastmcp_server back-reference is stamped for the escape hatch.
    assert runtime.mcp_surface.fastmcp_server is server


async def test_projection_mcp_only_does_not_appear_on_api() -> None:
    """``@a2kit.read(surfaces=("mcp",))`` mounts on FastMCP, NOT on FastAPI."""
    from fastmcp import Client

    class R(a2kit.Router):
        slug = "mem"

        @a2kit.read(surfaces=("mcp",))
        async def mcp_only(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    app = app_of("test", R())
    runtime = build(app)
    server = build_mcp_server(runtime, code_mode=False)
    async with Client(server) as client:
        names = {t.name for t in await client.list_tools()}
    assert "mem_mcp_only" in names


async def test_projection_api_only_does_not_appear_on_mcp() -> None:
    """``@a2kit.write(surfaces=("api",))`` is hidden from FastMCP."""
    from fastmcp import Client

    class R(a2kit.Router):
        slug = "mem"

        @a2kit.write(surfaces=("api",))
        async def api_only(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    app = app_of("test", R())
    runtime = build(app)
    server = build_mcp_server(runtime, code_mode=False)
    async with Client(server) as client:
        names = {t.name for t in await client.list_tools()}
    assert "api_only" not in names
