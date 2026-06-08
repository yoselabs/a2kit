"""Transport mounters filter tools by declared `visibility` tier.

`visibility="all"` (default) — registered on CLI and MCP.
`visibility="cli"` — registered on CLI, skipped on MCP.
`visibility="hidden"` — registered on CLI but absent from --help; skipped on MCP.
"""

from __future__ import annotations

import a2kit
from a2kit.routers import Router
from a2kit.testing import app_of


class _SurfRouter(Router):
    slug = "surf"
    name = "surf"

    @a2kit.read(visibility="cli")
    async def cli_only(self) -> dict[str, int]:
        return {"k": 1}

    @a2kit.read(visibility="hidden")
    async def hidden_op(self) -> dict[str, int]:
        return {"k": 1}

    @a2kit.read()
    async def both(self) -> dict[str, int]:
        return {"k": 1}


def _app() -> a2kit.App:
    return app_of("surftest", _SurfRouter())


def test_cli_builder_mounts_all_tiers() -> None:
    """CLI mounts all three tiers; visibility only affects --help and MCP."""
    from a2kit.packages.cli.builder import build_full_cli

    cli = build_full_cli(_app())
    surf_group = cli.commands["surf"]  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them
    cmd_names = set(surf_group.commands.keys())
    assert "cli-only" in cmd_names or "cli_only" in cmd_names
    assert "hidden-op" in cmd_names or "hidden_op" in cmd_names
    assert "both" in cmd_names


def test_cli_hidden_tier_marked_hidden_in_click() -> None:
    """`visibility="hidden"` propagates to Click's `hidden=True`."""
    from a2kit.packages.cli.builder import build_full_cli

    cli = build_full_cli(_app())
    surf_group = cli.commands["surf"]  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them
    # Resolve name (Typer kebab-cases by default).
    hidden_cmd_name = "hidden-op" if "hidden-op" in surf_group.commands else "hidden_op"
    hidden_cmd = surf_group.commands[hidden_cmd_name]
    assert hidden_cmd.hidden is True
    cli_cmd_name = "cli-only" if "cli-only" in surf_group.commands else "cli_only"
    assert surf_group.commands[cli_cmd_name].hidden is False
    assert surf_group.commands["both"].hidden is False


def test_mcp_server_skips_cli_and_hidden_tools() -> None:
    """MCP only registers `visibility="all"` tools."""
    import asyncio

    from a2kit.packages.mcp.server import build_mcp_server

    server = build_mcp_server(_app(), code_mode=False)

    async def _names() -> set[str]:
        return {t.name for t in await server.list_tools()}

    names = asyncio.run(_names())
    assert "surf_both" in names
    assert "surf_cli_only" not in names
    assert "surf_hidden_op" not in names


def test_default_visibility_visible_on_both() -> None:
    """Tool with no `visibility=` (resolves to "all") appears on every transport."""
    import asyncio

    from a2kit.packages.cli.builder import build_full_cli
    from a2kit.packages.mcp.server import build_mcp_server

    app = _app()
    cli = build_full_cli(app)
    server = build_mcp_server(app, code_mode=False)

    surf_group = cli.commands["surf"]  # ty: ignore[unresolved-attribute]  # why: stub object exposes attributes only at runtime; static checker can't see them

    async def _names() -> set[str]:
        return {t.name for t in await server.list_tools()}

    mcp_names = asyncio.run(_names())

    assert "both" in surf_group.commands
    assert "surf_both" in mcp_names
