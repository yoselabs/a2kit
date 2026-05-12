from __future__ import annotations

import a2kit
from a2kit.packages.connections import connections_cli, install_connections

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

# v0.30 composition: two explicit verbs for the connections plugin.
# `install_connections(app, TrackerConn)` registers the connection dispatch
# hook + wire scope on the container. `connections_cli(TrackerConn)` adds
# the CLI subcommands (login/logout/list/show/delete). No hidden marker on
# the Router class — the discovery surface stays slug/tools/providers/lifespan.
app = a2kit.App("tracker-mcp")
app.add_router(ProjectsRouter())
app.add_router(TasksRouter())
install_connections(app, TrackerConn)
app.add_cli(connections_cli(TrackerConn))
app.provide(TrackerStore)


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
