"""Built-in health probe — `_meta.health` tool + `@app.health_check` decorator.

The implementation lives in :mod:`a2kit.packages.health.probe`: the
``HealthRegistry`` check store, ``HealthResult`` outcome, the ``run_checks``
aggregator, and the ``app_version`` helper.
"""

from __future__ import annotations

from a2kit.packages.health.probe import (
    HEALTH_TOOL_NAME,
    META_NAMESPACE_PREFIX,
    HealthRegistry,
    HealthResult,
    app_version,
    run_checks,
)

__all__ = [
    "HEALTH_TOOL_NAME",
    "META_NAMESPACE_PREFIX",
    "HealthRegistry",
    "HealthResult",
    "app_version",
    "run_checks",
]
