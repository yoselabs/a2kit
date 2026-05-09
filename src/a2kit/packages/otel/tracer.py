"""Centralised OTel tracer / meter accessors.

Lazily imports ``opentelemetry-api`` so ``import a2kit.packages.otel`` does
not eagerly load the OTel runtime. Users wire exporters via the standard
OTel SDK; we just hand back tracer / meter handles bound to the global
provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.metrics import Meter
    from opentelemetry.trace import Tracer


_INSTALL_HINT = "a2kit.packages.otel requires the optional 'otel' extras. Install with: pip install 'a2kit[otel]'"


def _import_otel() -> tuple[Any, Any]:
    """Lazy-import the OTel API. Returns ``(trace, metrics)`` modules."""
    try:
        from opentelemetry import metrics, trace
    except ImportError as exc:  # pragma: no cover - exercised in install_missing test
        raise ImportError(_INSTALL_HINT) from exc
    return trace, metrics


def get_tracer(name: str = "a2kit") -> Tracer:
    """Return a tracer bound to the global OTel tracer provider."""
    trace, _ = _import_otel()
    return trace.get_tracer(name)


def get_meter(name: str = "a2kit") -> Meter:
    """Return a meter bound to the global OTel meter provider."""
    _, metrics = _import_otel()
    return metrics.get_meter(name)


__all__ = ["get_meter", "get_tracer"]
