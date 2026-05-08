"""Entry point — composition root for the tracker MCP.

Six-line `main()`. `a2kit.App` absorbs FastMCP server creation, the
ConnectionStore wiring, the RouterRegistry, the runner, and the unified
CLI dispatch. The author surface is `connect()` / `use()` / `run()`.

Run options (from `app.run()` parsing argv):

    serve [--http [host:port]] [--select EXPR] [--scope NAME] [--register BLOCK]
    login KEY field=val [field=val ...]
    logout KEY
    connections {list,show,delete}
    <tool-name> [key=value ...]            # one subcommand per registered tool

No subcommand → prints help with all options.
"""

from __future__ import annotations

import a2kit

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter


def main() -> None:
    app = a2kit.App("tracker-mcp")
    app.connect(TrackerConn)
    app.use(ProjectsRouter)
    app.use(TasksRouter)
    app.run()


if __name__ == "__main__":  # pragma: no cover
    main()
