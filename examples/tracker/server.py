from __future__ import annotations

import a2kit
from a2kit.packages.connections import install_connections

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

# Single-call wiring: `install_connections(app, TrackerConn)` installs
# the dispatch hook, registers the wire scope, AND adds the `connections`
# Click subcommand group (login/logout/list/show/delete).
app = a2kit.App("tracker-mcp")
app.add_router(ProjectsRouter())
app.add_router(TasksRouter())
install_connections(app, TrackerConn)
app.provide(TrackerStore, per_call=True)


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
