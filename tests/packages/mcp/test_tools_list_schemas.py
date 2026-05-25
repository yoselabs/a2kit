"""outputSchema is the oneOf union when a tool declares Raises(...) (Group 14.4-14.6).

For tools without Raises, the bare ReturnT schema is emitted (no union).
"""

from __future__ import annotations

from typing import Annotated

import a2kit
from a2effect import AppError, Raises
from a2kit.packages.mcp.server import build_mcp_server
from a2kit.runtime import build


class _NF(AppError):
    kind = "input"
    http_status = 404


async def test_tool_without_raises_emits_bare_schema() -> None:
    from fastmcp import Client

    class R(a2kit.Router):
        slug = "x"

        @a2kit.read()
        async def plain(self) -> dict:
            return {"ok": True}

        tools = (plain,)

    server = build_mcp_server(build(a2kit.App("t").add_router(R())), code_mode=False)
    async with Client(server) as client:
        tools = await client.list_tools()
    plain = next(t for t in tools if t.name == "plain")
    assert plain.outputSchema is not None
    assert "oneOf" not in plain.outputSchema


async def test_tool_with_raises_emits_oneof_union() -> None:
    from fastmcp import Client

    class R(a2kit.Router):
        slug = "x"

        @a2kit.read()
        async def typed(self, *, id: str) -> Annotated[dict, Raises(_NF)]:
            return {"id": id}

        tools = (typed,)

    server = build_mcp_server(build(a2kit.App("t").add_router(R())), code_mode=False)
    async with Client(server) as client:
        tools = await client.list_tools()
    typed = next(t for t in tools if t.name == "typed")
    schema = typed.outputSchema
    assert schema is not None
    assert "oneOf" in schema, f"expected oneOf union, got {schema}"
    branches = schema["oneOf"]
    assert len(branches) == 2
    # one branch carries the bare return shape; the other carries the envelope
    env_branch = next(b for b in branches if "properties" in b and "envelope_version" in b.get("properties", {}))
    assert env_branch["properties"]["kind"]["type"] == "string"
    assert env_branch["properties"]["type"]["type"] == "string"
