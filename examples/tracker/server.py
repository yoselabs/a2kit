"""Entry point — composition root for the tracker MCP.

Seven-line `main()`. `a2kit.App` absorbs FastMCP server creation, the
ConnectionStore wiring, the RouterRegistry, the runner, and the unified
CLI dispatch. The author surface is `connect()` / `use()` / `run()`.

The v0.15 idiom: connection injection happens via Annotated[Conn, Depends].
`get_conn_factory(app, ConnT)` returns the live factory; we forward it
into `routers.deps.set_get_conn` so the routers' captured `Depends(get_conn)`
references resolve through it at call time.

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
from a2kit.contrib.connections import get_conn_factory

from .connection import TrackerConn
from .deps import set_get_conn
from .routers import ProjectsRouter, TasksRouter


def main() -> None:
    app = a2kit.App("tracker-mcp")
    app.connect(TrackerConn)
    set_get_conn(get_conn_factory(app, TrackerConn))
    app.use(ProjectsRouter)
    app.use(TasksRouter)
    app.run()


if __name__ == "__main__":  # pragma: no cover
    main()
