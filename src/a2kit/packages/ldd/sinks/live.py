"""Live operator sink — one stdout line per event + configurable heartbeat.

Generalised from a2web's ``LiveSink`` (``bench-live-sink-v1``) per
``reshape-ldd-operator-wire-fanout`` (2026-05-27): the event-name
filter is parametric (``event_prefixes``, default ``("",)``) so any
``*Started`` / ``*Ended`` pair drives the live progress feed. Heartbeat
period is configurable; default 30s.

An :class:`asyncio.Lock` guards each stdout write so concurrent
emissions don't character-interleave.
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from a2kit.packages.ldd.sinks._core import LddEmission, LddSink


class _LiveSinkState:
    """Per-sink mutable state: lock, counters, last-write timestamp."""

    __slots__ = ("_event_prefixes", "_heartbeat_seconds", "_heartbeat_task", "_lock", "done", "last_emit_monotonic", "running")

    def __init__(self, *, event_prefixes: tuple[str, ...], heartbeat_seconds: float) -> None:
        self._lock = asyncio.Lock()
        self._event_prefixes = event_prefixes
        self._heartbeat_seconds = heartbeat_seconds
        self._heartbeat_task: asyncio.Task[None] | None = None
        self.running = 0
        self.done = 0
        self.last_emit_monotonic = time.monotonic()

    def matches(self, name: str) -> bool:
        return any(name.startswith(p) for p in self._event_prefixes)

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    @property
    def heartbeat_seconds(self) -> float:
        return self._heartbeat_seconds

    async def write_line(self, line: str) -> None:
        async with self._lock:
            print(line, file=sys.stdout, flush=True)  # noqa: T201
            self.last_emit_monotonic = time.monotonic()

    def ensure_heartbeat(self) -> None:
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            return
        if self._heartbeat_seconds <= 0:
            return
        loop = asyncio.get_running_loop()
        self._heartbeat_task = loop.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        try:
            while self.running > 0:
                await asyncio.sleep(self._heartbeat_seconds)
                if self.running == 0:
                    break
                now = time.monotonic()
                if now - self.last_emit_monotonic < self._heartbeat_seconds:
                    continue
                await self.write_line(f"[heartbeat] running: {self.running}, done: {self.done}")
        except asyncio.CancelledError:
            return


def make_live_sink(
    *,
    event_prefixes: tuple[str, ...] = ("",),
    heartbeat_seconds: float = 30.0,
) -> LddSink:
    """Construct a live-feed sink with the given filter + heartbeat.

    Returns an async callable suitable for ``app.ldd.add_sink(...)``.
    The default ``event_prefixes=("",)`` matches every event name; pass
    e.g. ``("Cell",)`` to scope to a specific event family.
    """
    state = _LiveSinkState(event_prefixes=event_prefixes, heartbeat_seconds=heartbeat_seconds)

    async def _sink(emission: LddEmission, /) -> None:
        if not state.matches(emission.name):
            return
        secs = emission.elapsed_ms / 1000.0
        if emission.name.endswith("Started"):
            state.running += 1
            await state.write_line(f"[+{secs:>6.3f}s] {emission.name} running={state.running}")
            state.ensure_heartbeat()
        elif emission.name.endswith("Ended"):
            state.running = max(0, state.running - 1)
            state.done += 1
            await state.write_line(f"[+{secs:>6.3f}s] {emission.name} done={state.done}")
        else:
            await state.write_line(f"[+{secs:>6.3f}s] {emission.name}")

    _sink.__name__ = "live_sink"
    return _sink


#: Default live sink with the default filter + 30s heartbeat.
live_sink = make_live_sink()


__all__ = ["live_sink", "make_live_sink"]
