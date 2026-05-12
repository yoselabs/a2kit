"""Stacked ``@reports(ReportT)`` decorator.

Replaces the ``report=`` kwarg on the core verb decorator. Computes the
pydantic JSON schema at decoration time and stamps two typed-extras
attributes on ``A2KitMeta.extras``:

- ``report_type``   — the type itself (consumed at runtime by ctx.report)
- ``report_schema`` — JSON-serializable schema (consumed by adapters
  that surface it on the wire / in ``--schema`` output).

Pydantic is imported here, not in core, so ``import a2kit`` stays cold.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from a2kit.metadata import stage_extra

F = TypeVar("F", bound=Callable[..., Any])


def _compute_schema(report_type: type) -> dict[str, Any] | None:
    try:
        from pydantic import TypeAdapter
    except ImportError:
        return None
    return TypeAdapter(report_type).json_schema()


def reports(report_type: type) -> Callable[[F], F]:
    """Declare the typed report payload for a tool that calls ``ctx.report(...)``."""
    schema = _compute_schema(report_type)

    def deco(fn: F) -> F:
        stage_extra(fn, "report_type", report_type)
        if schema is not None:
            stage_extra(fn, "report_schema", schema)
        return fn

    return deco


__all__ = ["reports"]
