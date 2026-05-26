"""LDD operator sinks — built-ins + the :class:`LddSink` protocol.

Re-exports the core types (:class:`LddEmission`, :class:`LddSink`,
``_dispatch_sinks``) and the four bundled operator sinks:

- :func:`stderr_pretty_sink` — one human-readable line per emission.
- :func:`stderr_json_sink` — one JSON-line per emission.
- :func:`otel_sink` — emits OTel spans; drains silently when SDK absent.
- :func:`live_sink` — heartbeat + per-event lines under an asyncio.Lock.

Per ``reshape-ldd-operator-wire-fanout`` (2026-05-27).
"""

from __future__ import annotations

from a2kit.packages.ldd.sinks._core import LddEmission, LddSink
from a2kit.packages.ldd.sinks.live import live_sink, make_live_sink
from a2kit.packages.ldd.sinks.otel import otel_sink
from a2kit.packages.ldd.sinks.stderr_json import stderr_json_sink
from a2kit.packages.ldd.sinks.stderr_pretty import stderr_pretty_sink

__all__ = (
    "LddEmission",
    "LddSink",
    "live_sink",
    "make_live_sink",
    "otel_sink",
    "stderr_json_sink",
    "stderr_pretty_sink",
)
