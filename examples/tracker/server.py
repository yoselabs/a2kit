from __future__ import annotations

import a2kit
from a2kit.packages.connections import connections, connections_cli

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

# v0.27 composition: two explicit verbs for the connections plugin.
# `connections(TrackerConn)` registers the connection dispatch hook + wire
# scope on the container. `connections_cli(TrackerConn)` adds the CLI
# subcommands (login/logout/list/show/delete). No hidden auto-install marker.
app = a2kit.App("tracker-mcp")
app.add_router(ProjectsRouter())
app.add_router(TasksRouter())
app.add_router(connections(TrackerConn))
app.add_cli(connections_cli(TrackerConn))
app.provide(TrackerStore)


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
