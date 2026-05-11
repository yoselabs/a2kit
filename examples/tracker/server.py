from __future__ import annotations

import a2kit
from a2kit.packages.connections import connections, connections_cli

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

# Canonical imperative composition. `connections(TrackerConn)` installs the
# typed provider via Router; `connections_cli(TrackerConn)` adds the CLI
# subcommands. Two explicit verbs, no hidden marker.
app = a2kit.App("tracker-mcp")
app.add_router(ProjectsRouter())
app.add_router(TasksRouter())
app.add_router(connections(TrackerConn))
cli = connections_cli(TrackerConn)
cli._a2kit_connections_types = None  # opt out of deprecated auto-install marker
app.add_cli(cli)
app.provide(TrackerStore)


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
