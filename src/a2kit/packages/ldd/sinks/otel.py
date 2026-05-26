"""OTel operator sink — one span per ``*Ended`` event.

Drain-on-missing-SDK invariant: when ``opentelemetry`` is not
importable (or no tracer provider is configured), :func:`otel_sink`
silently consumes every emission without raising. This keeps the
operator-fan-out contract intact in deployments where OTel is not
desired.

Ported from a2web ``src/a2web/events/sinks.py`` per
``reshape-ldd-operator-wire-fanout`` (2026-05-27).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from a2kit.packages.ldd.sinks._core import LddEmission

_LOG = logging.getLogger("a2kit.ldd.otel")


def _get_tracer() -> Any | None:
    """Return an OTel tracer or ``None`` if the SDK is unavailable."""
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    try:
        return trace.get_tracer("a2kit.ldd")
    except Exception:  # noqa: BLE001 -- defensive against SDK init quirks
        return None


async def otel_sink(emission: LddEmission, /) -> None:
    """Emit one OTel span per ``*Ended`` event; silently drain others.

    The naming convention matches a2web: events ending in ``Ended``
    materialise as completed spans; ``*Started`` events and heartbeats
    are drained (the ``Started`` half is implicit in the span's start
    time, which equals ``now() - elapsed_ms``).
    """
    if not emission.name.endswith("Ended"):
        return
    tracer = _get_tracer()
    if tracer is None:
        return
    try:
        with tracer.start_as_current_span(emission.name) as span:
            span.set_attribute("a2kit.kind", emission.kind)
            if emission.tool_name:
                span.set_attribute("a2kit.tool", emission.tool_name)
            span.set_attribute("a2kit.elapsed_ms", emission.elapsed_ms)
            for k, v in emission.payload.items():
                if isinstance(v, str | int | float | bool):
                    span.set_attribute(f"a2kit.{k}", v)
    except Exception as exc:  # noqa: BLE001 -- defensive: never raise from a sink
        _LOG.debug("otel_sink failed for %s: %s", emission.name, exc)


__all__ = ["otel_sink"]
