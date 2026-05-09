"""``serve`` Click command for the MCP adapter.

Lazy-imported by ``a2kit.packages.cli.builder.build_full_cli`` so that
``import a2kit`` (and ``a2kit lint``, ``a2kit connections``) never trigger a
fastmcp import.
"""

from __future__ import annotations

import click

from a2kit.packages.cli.app_ctx import _APP_CTX


@click.command("serve")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"]),
    default="stdio",
    show_default=True,
)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, type=int, show_default=True)
def serve_command(transport: str, host: str, port: int) -> None:
    """Run the MCP server."""
    from a2kit.packages.mcp.server import build_mcp_server

    app = _APP_CTX.get()
    server = build_mcp_server(app)
    if transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="http", host=host, port=port)


__all__ = ["serve_command"]
