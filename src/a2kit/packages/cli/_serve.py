"""CLI ``serve`` and ``code`` subcommand registration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

import typer

if TYPE_CHECKING:
    from a2kit.app import App


def register_serve(typer_app: Any, app: App) -> None:
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
    ) -> None:
        """Run as an MCP server (stdio or HTTP)."""
        from a2kit.packages.mcp.server import build_mcp_server

        server = build_mcp_server(
            app,
            code_mode=not code_mode_off,
            code_mode_allow_destructive=code_mode_allow_destructive,
            compact=compact,
        )
        if transport == "stdio":
            server.run(transport="stdio")
        else:
            server.run(transport="http", host=host, port=port)

    typer_app.command(name="serve")(serve_cmd)


def register_code(typer_app: Any, app: App) -> None:
    """Register the global ``code`` subcommand — run Python in the sandbox.

    Shares the sandbox and capability gate with the MCP ``execute`` tool
    via ``a2kit.packages.codemode.run_code``. Registered only when the
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
        from a2kit.packages.codemode import run_code

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


__all__ = ["register_code", "register_serve"]
