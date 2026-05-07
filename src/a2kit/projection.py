"""CEL projection / filter primitive (v0.4).

Two primitives:

- `filter_records(records, expr)` — filter a list of dicts by a CEL boolean
  expression. Requires the optional `[projection]` extra (`celpy>=0.5`).
- `project_fields(records, fields)` — keep only the named keys per record.
  Pure-Python, no extra dep.

Composed inside `a2kit.format_response(data, *, filter, fields)`.

Lazy import of `celpy`: importing this module without celpy installed is fine,
but calling `filter_records(...)` raises `ProjectionUnavailable` until the
extra is installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.exceptions import InvalidFilterExpression, ProjectionUnavailable

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


def _load_celpy() -> Any:
    """Lazy-load celpy. Raises `ProjectionUnavailable` if missing."""
    try:
        import celpy  # noqa: PLC0415
    except ImportError as exc:
        raise ProjectionUnavailable from exc
    return celpy


def filter_records(records: Iterable[Mapping[str, Any]], *, expr: str) -> list[dict[str, Any]]:
    """Filter `records` by a CEL boolean expression.

    Each record is exposed under variable bindings matching its keys plus a
    catch-all `record` binding for the whole mapping. Empty `expr` is a no-op
    (returns the records unchanged as a list).
    """
    items = [dict(r) for r in records]
    if not expr or not expr.strip():
        return items
    celpy = _load_celpy()
    env = celpy.Environment()
    try:
        ast = env.compile(expr)
        program = env.program(ast)
    except Exception as exc:
        raise InvalidFilterExpression(expr, str(exc)) from exc

    out: list[dict[str, Any]] = []
    for rec in items:
        bindings = {k: _to_cel(v) for k, v in rec.items()}
        bindings["record"] = _to_cel(rec)
        try:
            result = program.evaluate(bindings)
        except Exception as exc:
            raise InvalidFilterExpression(expr, f"evaluation failed: {exc}") from exc
        if bool(result):
            out.append(rec)
    return out


def _to_cel(value: Any) -> Any:
    """Coerce a Python value into the CEL value space accepted by celpy.

    celpy.Environment().program() expects values pre-wrapped via
    `celpy.json_to_cel(...)` for nested structures; primitives pass through.
    """
    celpy = _load_celpy()
    return celpy.json_to_cel(value) if isinstance(value, (dict, list)) else value


def project_fields(records: Iterable[Mapping[str, Any]], *, fields: list[str]) -> list[dict[str, Any]]:
    """Keep only `fields` per record. Missing fields are silently dropped.

    No CEL — just key selection. Pure Python.
    """
    if not fields:
        return [dict(r) for r in records]
    fset = list(fields)
    return [{k: r[k] for k in fset if k in r} for r in records]


__all__ = ["filter_records", "project_fields"]
