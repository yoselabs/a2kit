"""Transport mounters filter tools by declared Surface."""

from __future__ import annotations

import a2kit
from a2kit.routers import Router
from a2kit.surface import Surface


class _SurfRouter(Router):
    name = "surf"

    @a2kit.read(surfaces=Surface.CLI)
    async def cli_only(self) -> dict[str, int]:
        return {"k": 1}

    @a2kit.read(surfaces=Surface.MCP)
    async def mcp_only(self) -> dict[str, int]:
        return {"k": 1}

    @a2kit.read()
    async def both(self) -> dict[str, int]:
        return {"k": 1}


def _app() -> a2kit.App:
    app = a2kit.App("surftest")
    app.add_router(_SurfRouter())
    return app


def test_cli_builder_skips_mcp_only_tools() -> None:
    from a2kit.packages.cli.builder import build_full_cli

    cli = build_full_cli(_app())
    surf_group = cli.commands["surf"]
    cmd_names = set(surf_group.commands.keys())
    assert "cli-only" in cmd_names or "cli_only" in cmd_names
    assert "both" in cmd_names
    assert "mcp-only" not in cmd_names and "mcp_only" not in cmd_names


def test_mcp_server_skips_cli_only_tools() -> None:
    import asyncio

    from a2kit.packages.mcp.server import build_mcp_server

    server = build_mcp_server(_app())

    async def _names() -> set[str]:
        return {t.name for t in await server.list_tools()}

    names = asyncio.run(_names())
    assert "mcp_only" in names
    assert "both" in names
    assert "cli_only" not in names


def test_default_surface_all_visible_on_both() -> None:
    """Tool with default Surface.ALL appears on every transport."""
    import asyncio

    from a2kit.packages.cli.builder import build_full_cli
    from a2kit.packages.mcp.server import build_mcp_server

    app = _app()
    cli = build_full_cli(app)
    server = build_mcp_server(app)

    surf_group = cli.commands["surf"]

    async def _names() -> set[str]:
        return {t.name for t in await server.list_tools()}

    mcp_names = asyncio.run(_names())

    assert "both" in surf_group.commands
    assert "both" in mcp_names
