"""CLI :class:`a2kit.runtime.ToolContext` impl — compact stderr text."""

from __future__ import annotations

import sys
import time
from typing import Any

from a2kit.exceptions import ReportTypeMismatch, ReportTypeNotDeclared


def _format_kv(fields: dict[str, Any]) -> str:
    if not fields:
        return ""
    return " ".join(f"{k}={v!r}" if isinstance(v, str) else f"{k}={v}" for k, v in fields.items())


class StderrToolContext:
    """ToolContext that emits ``[ +s.mmm LEVEL] msg key=val`` lines to stderr."""

    __slots__ = (
        "_events_enabled",
        "_report_type",
        "_reports_enabled",
        "_start_ts",
        "_tool_name",
    )

    def __init__(
        self,
        *,
        report_type: type | None = None,
        tool_name: str | None = None,
        reports_enabled: bool = True,
        events_enabled: bool = True,
    ) -> None:
        self._start_ts = time.monotonic()
        self._report_type = report_type
        self._tool_name = tool_name
        self._reports_enabled = reports_enabled
        self._events_enabled = events_enabled

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
        self._emit("progress", "", {"current": current, "total": total})

    async def event(self, name: str, **payload: Any) -> None:
        if not self._events_enabled:
            return
        self._emit("event", name, payload)

    async def report(self, payload: Any) -> None:
        # why: type-validate even when reports are disabled — keeps tests
        # deterministic regardless of A2KIT_LDD env state.
        if self._report_type is None:
            raise ReportTypeNotDeclared(self._tool_name)
        if not isinstance(payload, self._report_type):
            raise ReportTypeMismatch(self._report_type, type(payload), self._tool_name)
        if not self._reports_enabled:
            return
        body = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        self._emit("report", type(payload).__name__, body)

    def _emit(self, level: str, msg: str, fields: dict[str, Any]) -> None:
        elapsed = time.monotonic() - self._start_ts
        kv = _format_kv(fields)
        head = f"[ +{elapsed:6.3f} {level:<8}]"
        body = f" {msg}" if msg else ""
        tail = f" {kv}" if kv else ""
        print(head + body + tail, file=sys.stderr, flush=True)  # noqa: T201


__all__ = ["StderrToolContext"]
