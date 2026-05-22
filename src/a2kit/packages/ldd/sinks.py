"""In-process LDD sink types — the :class:`LddEmission` payload + :class:`LddSink` protocol.

Sinks are registered via ``app.ldd.add_sink(...)``. After each wire emit,
:func:`event` / :func:`report` / :func:`log` fan the structured
:class:`LddEmission` out to every sink sequentially. Sink exceptions are
caught and logged on ``a2kit.ldd.sinks`` so one bad sink never breaks tool
dispatch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal, Protocol

#: Logger for sink-fan-out failures. Sinks that raise are caught here so a
#: bad sink can't break tool dispatch (see :func:`_dispatch_sinks`).
_SINK_LOGGER = logging.getLogger("a2kit.ldd.sinks")


@dataclass(frozen=True, slots=True)
class LddEmission:
    """Structured payload delivered to in-process LDD sinks.

    Built by :func:`event` / :func:`report` after their wire emit, then
    fan-out to each sink registered on ``app.ldd.add_sink(...)``.
    """

    kind: Literal["event", "report", "log"]
    name: str
    payload: dict[str, Any]
    elapsed_ms: int
    tool_name: str | None
    ctx: Any


class LddSink(Protocol):
    """Async callable that observes :class:`LddEmission` payloads.

    Registered via ``app.ldd.add_sink(sink)``. Invoked sequentially after
    each wire emit, in registration order. Sink exceptions are caught
    and logged on ``a2kit.ldd.sinks``; one bad sink never breaks tool
    dispatch.

    Sinks SHOULD return quickly — fan-out is sequential, so a slow sink
    delays the next emit. For heavy work (network export, batched writes),
    push to a queue from the sink and process out-of-band.
    """

    async def __call__(self, emission: LddEmission, /) -> None: ...


async def _dispatch_sinks(emission: LddEmission, sinks: tuple[LddSink, ...]) -> None:
    """Fan ``emission`` out to ``sinks`` sequentially; isolate exceptions."""
    for sink in sinks:
        try:
            await sink(emission)
        except Exception:
            _SINK_LOGGER.exception(
                "LDD sink %r raised; continuing",
                getattr(sink, "__name__", repr(sink)),
            )
