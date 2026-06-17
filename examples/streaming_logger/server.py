"""log example — composition root.

Run as a CLI::

    python -m examples.streaming_logger.server tasks import_csv --file /tmp/x.csv

Or as an MCP server::

    python -m examples.streaming_logger.server serve
"""

from __future__ import annotations

import a2kit
from a2kit.config import A2kitConfig, LogConfig

from .routers import TasksRouter


# Stream a2kit.log emissions to stderr as condensed lines so the CLI demo
# shows live, mid-call logging (the built-in stderr handler is opt-in).
class StreamingLoggerApp(a2kit.App):
    name = "streaming-logger"
    routers = (TasksRouter,)
    config = A2kitConfig(log=LogConfig(stderr_sink="pretty"))


app = StreamingLoggerApp()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
