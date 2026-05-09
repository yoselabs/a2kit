"""``serve`` Click command factory for the MCP adapter.

Materialized lazily by ``a2kit.packages.cli.builder.build_full_cli`` so that
``import a2kit`` never triggers a fastmcp import. The factory closes over
the ``App`` directly — no ContextVar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from a2kit.app import App


def build_serve_command(app: App) -> click.Command:
    """Return a ``serve`` Click command bound to ``app`` via closure."""

    @click.command("serve")
    @click.option(
        "--transport",
        type=click.Choice(["stdio", "http"]),
        default="stdio",
        show_default=True,
    )
    @click.option("--host", default="127.0.0.1", show_default=True)
    @click.option("--port", default=8000, type=int, show_default=True)
    def serve_cmd(transport: str, host: str, port: int) -> None:
        """Run the MCP server."""
        from a2kit.packages.mcp.server import build_mcp_server

        server = build_mcp_server(app)
        if transport == "stdio":
            server.run(transport="stdio")
        else:
            server.run(transport="http", host=host, port=port)

    return serve_cmd


__all__ = ["build_serve_command"]
