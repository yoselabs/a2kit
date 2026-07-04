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
        code_mode: Annotated[
            bool | None,
            typer.Option(
                "--code-mode/--no-code-mode",
                help=(
                    "Override the bundled code-execution surface for this run. "
                    "--code-mode forces it on, --no-code-mode forces it off; "
                    "absolute, not relative to config. Omit to defer to "
                    "config.mcp.code_mode (env A2KIT_MCP__CODE_MODE), then the "
                    "built-in default (on)."
                ),
            ),
        ] = None,
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
        select: Annotated[
            list[str] | None,
            typer.Option(
                "--select",
                help=(
                    "Narrow the served surface (repeatable). Syntax "
                    "'category=values' (verb|name|surface); e.g. "
                    "--select 'surface=mcp' serves MCP alone, "
                    "--select 'surface=api' serves the REST surface alone. "
                    "Multiple --select flags AND together."
                ),
            ),
        ] = None,
        internal_uds: Annotated[
            str | None,
            typer.Option(
                "--internal-uds",
                help=(
                    "Path for a co-resident internal spoke: a private "
                    "Unix-domain-socket listener (0600) for first-party jobs "
                    "to call verbs back into this process, authed via "
                    "TokenAuth. Runs in parallel with the public listener, "
                    "sharing one runtime. Off-host unreachable."
                ),
            ),
        ] = None,
    ) -> None:
        """Run the a2kit server.

        ``--transport=http`` runs the multiplex parent: MCP under ``/mcp``
        and the REST surface under ``/api`` (narrow with ``--select``).
        ``stdio`` (default) serves MCP only — a pipe carries one protocol.
        ``--internal-uds PATH`` adds a private spoke listener in parallel,
        in either transport mode.
        """
        from a2kit.packages.select import SelectorError, compile_selector
        from a2kit.packages.serve import serve_process
        from a2kit.runtime import apply_selection, build

        select_list = list(select or ())
        for expr in select_list:
            try:
                compile_selector(expr)
            except SelectorError as exc:
                raise typer.BadParameter(f"--select expression invalid: {exc}") from exc

        # ``app`` is already an AppRuntime (built by ``run()`` before the CLI
        # parsed ``--select``). ``build(runtime, select=...)`` would raise, so
        # narrow the runtime directly — this re-derives descriptors + surfaces
        # exactly as build(app, select=...) would. ``build(app)`` is a no-op
        # idempotent pass that also accepts a source App for programmatic callers.
        runtime = apply_selection(build(app), select_list or None)
        mcp_options = {
            "code_mode": code_mode,
            "code_mode_allow_destructive": code_mode_allow_destructive,
            "compact": compact,
            "tool_selection": tools,
        }
        serve_process(
            runtime,
            transport=transport,
            host=host,
            port=port,
            internal_uds=internal_uds,
            mcp_options=mcp_options,
        )

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
