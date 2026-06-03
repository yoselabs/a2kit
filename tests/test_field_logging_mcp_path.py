"""Repro + acceptance test for the field-logging-via-ldd change.

Today: the kwarg-emit pattern (``await ctx.info("msg", k=v)``) crashes
under the real MCP transport because fastmcp.Context.info doesn't
accept arbitrary kwargs. This test is XFAIL on the old surface and
XPASS once ``a2kit.ldd.log`` (with ``info``/``warning``/... aliases) lands.

The test invokes a tool through ``fastmcp.Client(transport=build_mcp_server(app))``
so it exercises the real fastmcp.Context, not the CLI subclass that
``a2kit.testing.client`` uses today. That's the structural gap the
change closes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastmcp import Client

import a2kit
from a2kit.packages.mcp.server import build_mcp_server


def _build_app() -> a2kit.App:
    """Construct an app whose tool calls ``a2kit.ldd.info`` with both
    string and instance forms.

    The instance form is exercised here as well as the string form so the
    test pins both call shapes against the real MCP wire.
    """
    from a2kit import log

    @dataclass
    class ImportStarted:
        file: str
        batch: int

    class R(a2kit.Router):
        slug = "r"

        @a2kit.read()
        async def emit_string(self, *, ctx: a2kit.ToolContext) -> dict[str, int]:
            await log.info("starting", batch=2, file="/x.csv")  # 
            return {"ok": 1}

        @a2kit.read()
        async def emit_instance(self, *, ctx: a2kit.ToolContext) -> dict[str, int]:
            await log.info(ImportStarted(file="/x.csv", batch=2))  # 
            return {"ok": 1}

        tools = (
            emit_string,
            emit_instance,
        )

    return a2kit.App("field-logging-probe").add_router(R())


async def _call(tool_name: str) -> Any:
    server = build_mcp_server(_build_app())
    async with Client(transport=server) as c:
        return await c.call_tool(tool_name, {})


def test_string_form_round_trips_through_real_mcp() -> None:
    """``a2kit.ldd.info("msg", **fields)`` must deliver through real MCP."""
    result = asyncio.run(_call("emit_string"))
    payload = result.data if hasattr(result, "data") else result.structured_content
    assert payload == {"ok": 1}


def test_instance_form_round_trips_through_real_mcp() -> None:
    """``a2kit.ldd.info(dataclass_instance)`` must deliver through real MCP."""
    result = asyncio.run(_call("emit_instance"))
    payload = result.data if hasattr(result, "data") else result.structured_content
    assert payload == {"ok": 1}
