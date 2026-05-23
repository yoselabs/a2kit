"""``serve`` Click command factory for the a2kit server.

Materialized lazily by ``a2kit.packages.cli.builder.build_full_cli`` so that
``import a2kit`` never triggers a fastmcp import. The factory closes over
the ``App`` directly — no ContextVar.

``serve --transport=http`` runs a multiplexed server: one process, one
port, an a2kit-owned parent ASGI app auto-mounting the MCP surface
under ``/mcp`` and the HTTP/API surface under ``/api`` based on the
App's registrations. Use ``--select 'surface=mcp'`` /
``--select 'surface=api'`` (``add-tool-select``) to narrow to a single
surface. The default ``stdio`` transport serves the MCP surface only —
a stdio pipe cannot multiplex more than one protocol.
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
        "--select",
        "select",
        multiple=True,
        help=(
            "Filter the exposed tool surface (repeatable). "
            "Syntax: 'category=values' where category is verb|name|surface "
            "and values is comma-separated (use !value for exclude). "
            "Examples: --select 'verb=read,list', --select 'surface=mcp', "
            "--select 'name=fetch_*,!internal_*'. "
            "Multiple --select flags AND together."
        ),
    )
    def serve_cmd(transport: str, host: str, port: int, select: tuple[str, ...]) -> None:
        """Run the a2kit server.

        Substrate mounts under ``--transport=http`` are determined by the
        App's registrations — projection tools (``@app.read``/``.list``/
        ``.write``) expose on both ``/api`` and ``/mcp`` by default;
        ``@app.api.<method>`` is FastAPI-only; ``@app.mcp.<feature>`` is
        FastMCP-only. To narrow the deploy to one surface, use
        ``--select 'surface=mcp'`` (or ``surface=api``) — landing in
        ``add-tool-select``.
        """
        # Compile selectors up front: a parse error must exit 2 with a
        # one-line stderr message before any uvicorn/build work runs.
        select_list = list(select)
        if select_list:
            from a2kit.packages.select import SelectorError, compile_selector

            try:
                for expr in select_list:
                    compile_selector(expr)
            except SelectorError as exc:
                msg = f"--select expression invalid: {exc}"
                raise click.UsageError(msg) from exc

        if transport == "stdio":
            # A stdio pipe carries one protocol — MCP. Build the runtime
            # with selectors applied so `--select 'verb=read'` narrows
            # the stdio MCP surface too.
            from a2kit.packages.mcp.server import build_mcp_server
            from a2kit.runtime import build

            runtime = build(app, select=select_list or None)
            build_mcp_server(runtime).run(transport="stdio")
            return

        # http: one process, one port, an a2kit-owned parent app mounting
        # each populated surface. uvicorn and the parent composition are
        # imported here so `import a2kit` never pays their cost.
        import uvicorn

        from a2kit.packages.serve import build_parent_app
        from a2kit.runtime import build

        runtime = build(app, select=select_list or None)
        parent = build_parent_app(runtime)
        uvicorn.run(parent, host=host, port=port)

    return serve_cmd


__all__ = ["build_serve_command"]
