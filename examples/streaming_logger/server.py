"""LDD example — composition root.

Run as a CLI::

    python -m examples.streaming_logger.server tasks import_csv --file /tmp/x.csv

Or as an MCP server::

    python -m examples.streaming_logger.server serve
"""

from __future__ import annotations

import a2kit

from .routers import TasksRouter

builder = a2kit.AppBuilder("streaming-logger")
builder.add_router(TasksRouter())
app = builder.build()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
