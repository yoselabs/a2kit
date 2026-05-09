from __future__ import annotations

import a2kit
from a2kit.packages.connections import connections_cli

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

app = (
    a2kit.App("tracker-mcp")
    .add_router(ProjectsRouter())
    .add_router(TasksRouter())
    # `add_cli(connections_cli(TrackerConn))` auto-registers a typed provider
    # for `TrackerConn` (factory: `connection: str → TrackerConn`). With the
    # `TrackerStore` provider below, the chain is:
    #     wire `connection` → TrackerConn → TrackerStore (class-as-factory).
    .add_cli(connections_cli(TrackerConn))
    .provide(TrackerStore)
)


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
