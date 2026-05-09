from __future__ import annotations

import a2kit
from a2kit.packages.connections import Connections

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter

app = a2kit.App("tracker-mcp")
app.use(Connections())  # CLI commands + DI resolvers for conn classes
app.use(TrackerConn)  # claimed by Connections plugin
app.use(ProjectsRouter())
app.use(TasksRouter())


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
