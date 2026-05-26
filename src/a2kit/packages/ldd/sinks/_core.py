"""LDD sink types — :class:`LddEmission` payload + :class:`LddSink` protocol + parallel fan-out.

Sinks are registered via ``app.ldd.add_sink(...)``. After each wire
emit, :func:`event` / :func:`report` / :func:`log` fan the structured
:class:`LddEmission` out to every operator sink **in parallel** via
``asyncio.gather(..., return_exceptions=True)``. Per-sink failures are
logged at WARN under ``a2kit.ldd.sink_failed`` and dropped — isolating
the producer, every other operator sink, and the wire path.

Per ``reshape-ldd-operator-wire-fanout`` (2026-05-27): operator-sink
fan-out and the wire path are independent channels both gated by the
single level threshold.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal, Protocol

_SINK_LOGGER = logging.getLogger("a2kit.ldd.sink_failed")


@dataclass(frozen=True, slots=True)
class LddEmission:
    """Structured payload delivered to in-process LDD sinks."""

    kind: Literal["event", "report", "log"]
    name: str
    payload: dict[str, Any]
    elapsed_ms: int
    tool_name: str | None
    ctx: Any


class LddSink(Protocol):
    """Async callable observing :class:`LddEmission` payloads."""

    async def __call__(self, emission: LddEmission, /) -> None: ...


async def _dispatch_sinks(emission: LddEmission, sinks: tuple[LddSink, ...]) -> None:
    """Fan ``emission`` out to ``sinks`` in parallel; isolate exceptions.

    Uses ``asyncio.gather(..., return_exceptions=True)`` so a slow or
    failing sink cannot block its siblings or the producer's next
    emission. Each exception is logged at WARN with the sink name +
    emission name + kind, then dropped.
    """
    if not sinks:
        return
    results = await asyncio.gather(*(sink(emission) for sink in sinks), return_exceptions=True)
    for sink, result in zip(sinks, results, strict=True):
        if isinstance(result, BaseException):
            _SINK_LOGGER.warning(
                "LDD sink %r failed on %s/%s: %s: %s",
                getattr(sink, "__name__", repr(sink)),
                emission.kind,
                emission.name,
                type(result).__name__,
                result,
            )
