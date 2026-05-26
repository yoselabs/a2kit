"""App-boot helper to register the built-in LDD operator sinks.

Lives at the runtime layer (alongside ``app.py``) so it can import
``LddConfig`` (kernel) and the LDD front door (L0) without inverting
the layer DAG. Per ``reshape-ldd-operator-wire-fanout`` (2026-05-27).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from a2kit.config import LddConfig
    from a2kit.packages.ldd import _AppLdd


def register_builtin_ldd_sinks(app_ldd: _AppLdd, ldd_config: LddConfig) -> None:
    """Register configured built-in operator sinks on ``app_ldd``.

    Order: stderr (if enabled) → otel (if enabled) → live (if enabled).
    User-added sinks via ``app.ldd.add_sink(...)`` run after these in
    registration order.
    """
    from a2kit.packages.ldd import (
        make_live_sink,
        otel_sink,
        stderr_json_sink,
        stderr_pretty_sink,
    )

    if ldd_config.stderr_sink == "pretty":
        app_ldd.add_sink(stderr_pretty_sink)
    elif ldd_config.stderr_sink == "json":
        app_ldd.add_sink(stderr_json_sink)
    if should_register_otel_sink(ldd_config.otel_sink):
        app_ldd.add_sink(otel_sink)
    if ldd_config.live_sink == "on":
        app_ldd.add_sink(
            make_live_sink(
                event_prefixes=ldd_config.live_event_prefixes,
                heartbeat_seconds=ldd_config.live_heartbeat_seconds,
            )
        )


def should_register_otel_sink(mode: str) -> bool:
    """Decide whether to register the OTel sink given the config mode.

    ``on`` → always; ``off`` → never; ``auto`` → iff the OTel SDK is
    importable AND at least one ``OTEL_EXPORTER_*`` env var is set.
    The auto heuristic avoids the surprise of "I imported OTel for
    an unrelated reason and now my LDD output goes nowhere."
    """
    if mode == "off":
        return False
    if mode == "on":
        return True
    try:
        import opentelemetry  # noqa: F401
    except ImportError:
        return False
    return any(key.startswith("OTEL_EXPORTER_") for key in os.environ)


__all__ = ["register_builtin_ldd_sinks", "should_register_otel_sink"]
