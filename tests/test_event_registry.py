"""Section 9b: ``EventRegistry`` + LDD wire-format invariants.

- ``format_ldd_line`` byte-equivalent across CLI ``_emit`` and a direct call.
- ``elapsed_ms`` integer increases monotonically across emissions.
- Text portion capped at :data:`a2kit.packages.ldd.TEXT_CAP` chars with ``…``.
- ``EventRegistry.emit_typed`` calls ``model_dump(mode="json")``, then
  :func:`event`, then ``ctx.report_progress`` if a callback is registered.
- Re-registration is last-write-wins (no warning).
- ``model_dump(mode="json")`` coerces datetime → ISO string.
"""

from __future__ import annotations

import asyncio
import io
import re
import sys
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

import a2kit
from a2kit.ldd import EventRegistry, event, format_ldd_line, ldd_state_for_call
from a2kit.packages.cli.context import StderrToolContext
from a2kit.packages.ldd import TEXT_CAP


def _capture_stderr(call: Any) -> str:
    buf = io.StringIO()
    saved = sys.stderr
    sys.stderr = buf
    try:
        result = call()
        if asyncio.iscoroutine(result):
            asyncio.run(result)
    finally:
        sys.stderr = saved
    return buf.getvalue()


# --- format_ldd_line shape --- #


def test_format_ldd_line_includes_prefix_msg_and_kv() -> None:
    line = format_ldd_line("INFO", "hello", {"k": 1, "name": "x"}, elapsed_ms=42)
    assert line.startswith("[ +")
    assert "+ 0.042 INFO" in line
    assert " hello" in line
    assert "k=1" in line
    assert "name='x'" in line


def test_format_ldd_line_caps_long_text() -> None:
    very_long = "x" * (TEXT_CAP + 50)
    line = format_ldd_line("INFO", very_long, {}, elapsed_ms=0)
    # Body portion only; everything after `INFO]` is " <msg>".
    body = line.split("] ", 1)[1]
    assert body.endswith("…")
    assert len(body) == TEXT_CAP


def test_format_ldd_line_short_msg_unchanged() -> None:
    line = format_ldd_line("INFO", "short", {}, elapsed_ms=0)
    assert line.endswith(" short")
    assert "…" not in line


def test_format_ldd_line_no_msg_no_body() -> None:
    line = format_ldd_line("progress", "", {"current": 1, "total": 10}, elapsed_ms=5)
    # progress lines have empty msg; the kv tail still present.
    assert "current=1" in line
    assert "total=10" in line


# --- _emit consistency with format_ldd_line --- #


def test_stub_emit_byte_equal_to_format_ldd_line() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr(lambda: ctx._emit("INFO", "hi", {"k": 1}, elapsed_ms=100))  # noqa: SLF001
    expected = format_ldd_line("INFO", "hi", {"k": 1}, elapsed_ms=100) + "\n"
    assert out == expected


# --- elapsed_ms monotonicity --- #


def test_elapsed_ms_increases_across_events() -> None:
    ctx = StderrToolContext()
    elapsed_seen: list[int] = []

    async def go() -> None:
        with ldd_state_for_call(ctx=ctx):
            await event("first")
            await asyncio.sleep(0.02)
            await event("second")
            await asyncio.sleep(0.02)
            await event("third")

    out = _capture_stderr(go)
    for line in out.strip().splitlines():
        m = re.search(r"\+\s*(\d+\.\d+)", line)
        assert m
        elapsed_seen.append(int(float(m.group(1)) * 1000))
    assert elapsed_seen == sorted(elapsed_seen)
    assert elapsed_seen[-1] >= 30  # roughly 40ms total sleep


# --- EventRegistry --- #


class ProgressEvent(BaseModel):
    name: str
    done: int
    total: int


class TimedEvent(BaseModel):
    when: datetime
    label: str


def test_emit_typed_renders_event_with_dumped_payload() -> None:
    reg = EventRegistry()
    reg.register(ProgressEvent)
    ctx = StderrToolContext()

    async def go() -> None:
        with ldd_state_for_call(ctx=ctx):
            await reg.emit_typed(ProgressEvent(name="batch", done=3, total=10))

    out = _capture_stderr(go)
    assert "ProgressEvent" in out
    assert "name='batch'" in out
    assert "done=3" in out


def test_emit_typed_calls_progress_callback() -> None:
    reg = EventRegistry()
    reg.register(ProgressEvent, progress=lambda e: (e.done, e.total))
    ctx = StderrToolContext()

    async def go() -> None:
        with ldd_state_for_call(ctx=ctx):
            await reg.emit_typed(ProgressEvent(name="b", done=7, total=10))

    out = _capture_stderr(go)
    assert "ProgressEvent" in out
    # progress line uses level 'progress' with current=/total=
    assert "current=7" in out
    assert "total=10" in out


def test_register_last_write_wins() -> None:
    reg = EventRegistry()
    reg.register(ProgressEvent, progress=lambda e: (e.done, e.total))
    reg.register(ProgressEvent, progress=None)  # second wins → no progress
    ctx = StderrToolContext()

    async def go() -> None:
        with ldd_state_for_call(ctx=ctx):
            await reg.emit_typed(ProgressEvent(name="b", done=1, total=2))

    out = _capture_stderr(go)
    # Only one line expected (the event itself), no progress line.
    assert out.count("\n") == 1


def test_emit_typed_dumps_datetime_as_iso() -> None:
    reg = EventRegistry()
    reg.register(TimedEvent)
    ctx = StderrToolContext()

    when = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)

    async def go() -> None:
        with ldd_state_for_call(ctx=ctx):
            await reg.emit_typed(TimedEvent(when=when, label="start"))

    out = _capture_stderr(go)
    assert "TimedEvent" in out
    assert "2026-05-10T12:00:00" in out  # ISO-formatted datetime
    assert "label='start'" in out


def test_app_mounts_ldd_events_registry() -> None:
    app = a2kit.App("demo")
    assert isinstance(app.ldd.events, EventRegistry)
    app.ldd.events.register(ProgressEvent)
    assert app.ldd.events.is_registered(ProgressEvent)
