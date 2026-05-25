from __future__ import annotations

import a2kit
from a2kit.packages.connections import install_connections

from .connection import TrackerConn
from .enrichers import tracker_404_enricher
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

# Single-call wiring: `install_connections(app, TrackerConn)` installs
# the dispatch hook, registers the wire scope, AND adds the `connections`
# Click subcommand group (login/logout/list/show/delete).
app = a2kit.App("tracker-mcp")
projects = ProjectsRouter()
tasks = TasksRouter()
projects.enricher(tracker_404_enricher)
tasks.enricher(tracker_404_enricher)
app.add_router(projects)
app.add_router(tasks)
install_connections(app, TrackerConn)
app.provide(TrackerStore, per_call=True)


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
