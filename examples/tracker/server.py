from __future__ import annotations

import a2kit
from a2kit.packages.connections import get_conn_factory

from .connection import TrackerConn
from .deps import get_conn
from .routers import ProjectsRouter, TasksRouter

app = a2kit.App("tracker-mcp")
app.connect(TrackerConn)
app.use_factory(get_conn_factory(app, TrackerConn), as_=get_conn)
app.use(ProjectsRouter())
app.use(TasksRouter())


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
