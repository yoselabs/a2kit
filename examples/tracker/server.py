from __future__ import annotations

import a2kit
from a2kit.packages.connections import ConnectionStore, connections_cli

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

_conn_store = ConnectionStore(TrackerConn)


async def get_store(connection: str) -> TrackerStore:
    conn = await _conn_store.load((connection,))
    return TrackerStore(conn)


app = a2kit.App("tracker-mcp")
app.add_router(ProjectsRouter(get_store))
app.add_router(TasksRouter(get_store))
app.add_cli(connections_cli(TrackerConn))


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
