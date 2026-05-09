"""CLI :class:`a2kit.runtime.ToolContext` impl — compact stderr text."""

from __future__ import annotations

import sys
from typing import Any


class StderrToolContext:
    """ToolContext that emits ``[LEVEL] msg key=val`` lines to stderr."""

    def info(self, msg: str, **fields: Any) -> None:
        self._emit("INFO", msg, fields)

    def warning(self, msg: str, **fields: Any) -> None:
        self._emit("WARN", msg, fields)

    def error(self, msg: str, **fields: Any) -> None:
        self._emit("ERROR", msg, fields)

    def debug(self, msg: str, **fields: Any) -> None:
        self._emit("DEBUG", msg, fields)

    async def report_progress(
        self,
        current: int | float,
        total: int | float | None = None,
    ) -> None:
        self._emit("INFO", "progress", {"current": current, "total": total})

    @staticmethod
    def _emit(level: str, msg: str, fields: dict[str, Any]) -> None:
        kv = " ".join(f"{k}={v!r}" if isinstance(v, str) else f"{k}={v}" for k, v in fields.items())
        line = f"[{level}] {msg}" + (f" {kv}" if kv else "")
        print(line, file=sys.stderr, flush=True)  # noqa: T201


__all__ = ["StderrToolContext"]
