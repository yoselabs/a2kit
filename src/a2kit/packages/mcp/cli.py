"""``serve`` Click command factory for the a2kit server.

Materialized lazily by ``a2kit.packages.cli.builder.build_full_cli`` so that
``import a2kit`` never triggers a fastmcp import. The factory closes over
the ``App`` directly — no ContextVar.

``serve --transport=http`` runs a multiplexed server: one process, one
port, an a2kit-owned parent ASGI app mounting the MCP surface under
``/mcp`` and the REST surface under ``/api``. ``--mcp-only`` /
``--rest-only`` narrow that to a single surface. The default ``stdio``
transport serves the MCP surface only — a stdio pipe cannot multiplex
more than one protocol.
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
    @click.option(
        "--mcp-only",
        is_flag=True,
        default=False,
        help="Serve only the MCP surface (omit the REST surface).",
    )
    @click.option(
        "--rest-only",
        is_flag=True,
        default=False,
        help="Serve only the REST surface (omit the MCP surface); requires --transport=http.",
    )
    def serve_cmd(transport: str, host: str, port: int, mcp_only: bool, rest_only: bool) -> None:
        """Run the a2kit server."""
        if mcp_only and rest_only:
            msg = "--mcp-only and --rest-only are mutually exclusive."
            raise click.UsageError(msg)

        if transport == "stdio":
            # A stdio pipe carries one protocol — MCP. `--mcp-only` is a
            # redundant no-op here; `--rest-only` is a contradiction.
            if rest_only:
                msg = (
                    "--rest-only cannot be used with stdio transport: REST cannot "
                    "be served over a single-protocol stdio pipe. Use --transport=http."
                )
                raise click.UsageError(msg)
            from a2kit.packages.mcp.server import build_mcp_server

            build_mcp_server(app).run(transport="stdio")
            return

        # http: one process, one port, an a2kit-owned parent app mounting
        # each enabled surface. uvicorn and the parent composition are
        # imported here so `import a2kit` never pays their cost.
        import uvicorn

        from a2kit.packages.serve import build_parent_app

        parent = build_parent_app(app, mcp=not rest_only, rest=not mcp_only)
        uvicorn.run(parent, host=host, port=port)

    return serve_cmd


__all__ = ["build_serve_command"]
