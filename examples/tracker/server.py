from __future__ import annotations

import a2kit

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter

app = a2kit.App("tracker-mcp")
app.connect(TrackerConn)
app.use(ProjectsRouter())
app.use(TasksRouter())


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
