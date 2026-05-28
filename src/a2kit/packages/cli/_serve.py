"""CLI ``serve`` and ``code`` subcommand registration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

import typer

if TYPE_CHECKING:
    from a2kit.runtime import AppRuntime


def register_serve(typer_app: Any, app: AppRuntime) -> None:
    """Register the ``serve`` subcommand. ``fastmcp`` is imported lazily inside the callback."""

    def serve_cmd(
        transport: Annotated[str, typer.Option(help="Transport: 'stdio' or 'http'.")] = "stdio",
        host: Annotated[str, typer.Option(help="HTTP bind host.")] = "127.0.0.1",
        port: Annotated[int, typer.Option(help="HTTP bind port.")] = 8000,
        code_mode_off: Annotated[
            bool,
            typer.Option("--code-mode-off", help="Disable the bundled code-execution surface."),
        ] = False,
        code_mode_allow_destructive: Annotated[
            bool,
            typer.Option(
                "--code-mode-allow-destructive",
                help="Let the code-execution sandbox reach destructive tools.",
            ),
        ] = False,
        compact: Annotated[
            bool,
            typer.Option(
                "--compact",
                help="Drop the structuredContent channel for non-conformant MCP clients.",
            ),
        ] = False,
        tools: Annotated[
            str | None,
            typer.Option(
                "--tools",
                help=(
                    "Comma-separated tool name subset to expose on the MCP "
                    "surface (e.g. --tools=ask,refresh). Intersects with the "
                    "A2KIT_TOOLS env var when both are set. Cannot re-enable "
                    "hidden tools."
                ),
            ),
        ] = None,
    ) -> None:
        """Run as an MCP server (stdio or HTTP)."""
        from a2kit.packages.mcp import build_mcp_server

        server = build_mcp_server(
            app,
            code_mode=not code_mode_off,
            code_mode_allow_destructive=code_mode_allow_destructive,
            compact=compact,
            tool_selection=tools,
        )
        if transport == "stdio":
            server.run(transport="stdio")
        else:
            server.run(transport="http", host=host, port=port)

    typer_app.command(name="serve")(serve_cmd)


async def run_code(app: AppRuntime, code: str, *, allow_destructive: bool = False) -> object:
    """Run ``code`` in the code-execution sandbox against ``app``'s tools.

    Builds an MCP server for ``app``, wraps it in a ``fastmcp.Client``, and
    invokes the bundled ``execute`` tool. This is CLI-side orchestration —
    the sole caller is the ``code`` subcommand below. The MCP ``execute``
    tool is built independently by ``A2kitCodeMode._make_execute_tool``;
    the two do not share code.

    The ``fastmcp`` / ``build_mcp_server`` imports are function-local so
    ``code`` stays off the CLI cold-start path.
    """
    from fastmcp import Client

    from a2kit.packages.mcp import build_mcp_server

    server = build_mcp_server(app, code_mode=True, code_mode_allow_destructive=allow_destructive)
    async with Client(server) as client:
        result = await client.call_tool("execute", {"code": code})
    return result.data if result.data is not None else result.content


def register_code(typer_app: Any, app: AppRuntime) -> None:
    """Register the global ``code`` subcommand — run Python in the sandbox.

    Delegates to :func:`run_code`. Registered only when the
    ``a2kit[code-mode]`` extra is installed (``find_spec`` checks without
    importing) — a lean install carries no sandbox dependency.
    """
    import asyncio
    import importlib.util
    import sys
    from pathlib import Path

    if importlib.util.find_spec("pydantic_monty") is None:
        return

    def code_cmd(
        source: Annotated[
            str | None,
            typer.Argument(help="Python source to run; omit to read from stdin."),
        ] = None,
        file: Annotated[str | None, typer.Option("--file", help="Read Python source from this file.")] = None,
        allow_destructive: Annotated[
            bool,
            typer.Option("--allow-destructive", help="Let the sandbox reach destructive tools."),
        ] = False,
    ) -> None:
        """Run Python in the code-execution sandbox.

        `call_tool(name, params)` is in scope and reaches every tool the
        capability gate permits. The answer is the value of the last line —
        a bare expression; never use a top-level `return`.
        """
        if file is not None:
            code = Path(file).read_text()
        elif source is not None:
            code = source
        else:
            code = sys.stdin.read()
        if not code.strip():
            raise typer.BadParameter("No code provided (argument, --file, or stdin).")
        try:
            result = asyncio.run(run_code(app, code, allow_destructive=allow_destructive))
        except Exception as exc:
            typer.echo(f"error: {exc}", err=True)
            if getattr(app, "debug", False):
                import traceback

                typer.echo(traceback.format_exc(), err=True)
            raise typer.Exit(1) from exc
        typer.echo(result)

    typer_app.command(name="code")(code_cmd)


__all__ = ["register_code", "register_serve", "run_code"]
