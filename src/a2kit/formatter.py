"""Output-format primitives — TOON / JSON heuristic + recursive truncation.

Promoted to a primitive at n=2 (a SQL-wrapping MCP ships TSV+JSON, a
Jira/Confluence-wrapping MCP ships TOON+JSON).
Both also recursively truncate string fields beyond a fixed cap. The two MCPs
disagree on the wire format (TSV vs TOON) but the *shape of the decision tree*
is identical: list-of-uniform-rows -> tabular, single entity / nested -> JSON.

This module ships the decision tree once. The vendored TOON encoder is ≤ 30 LOC
(no external dep). Truncation is recursive on dict/list and applies to strings only.

Public API:

- `truncate(value, max_chars=2000, marker="…[truncated]")` — recursive on
  dicts/lists, identity on non-string scalars.
- `toon_or_json(data)` — returns `(format, payload)` where `format` is `"toon"`
  or `"json"`. Heuristic: list-of-dicts with uniform keys → TOON; everything else
  → JSON-compact.
- `Response` — typed Pydantic model returned by `format_response`. Fields:
  `format` ("toon"|"json"), `data` (string), `truncated` (bool), `next_cursor`
  (str | None — reserved for v0.9 pagination).
- `format_response(data, *, truncate_at=2000)` — packages truncation + format
  routing into a `Response`.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

DEFAULT_MAX_CHARS = 2000
DEFAULT_MARKER = "…[truncated]"


def truncate(value: Any, max_chars: int = DEFAULT_MAX_CHARS, marker: str = DEFAULT_MARKER) -> Any:
    """Truncate string fields recursively. Returns a new value; never mutates input.

    - `str` longer than `max_chars` → truncated to `max_chars` + `marker`.
    - `dict` → recurse on values (keys untouched).
    - `list` / `tuple` → recurse on items (returns a list, not tuple, for JSON safety).
    - Anything else → returned unchanged.
    """
    if isinstance(value, str):
        if len(value) > max_chars:
            return value[:max_chars] + marker
        return value
    if isinstance(value, dict):
        return {k: truncate(v, max_chars, marker) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [truncate(item, max_chars, marker) for item in value]
    return value


def _is_uniform_row_list(data: Any) -> bool:
    """True iff `data` is a non-empty list of dicts with identical key sets."""
    if not isinstance(data, list) or not data:
        return False
    if not all(isinstance(item, dict) for item in data):
        return False
    first_keys = set(data[0].keys())
    return all(set(item.keys()) == first_keys for item in data[1:])


def _toon_encode(rows: list[dict[str, Any]]) -> str:
    """Header row + tab-separated values. Vendored — ≤ 20 LOC.

    The encoder is deliberately minimal: assumes uniform keys (caller's
    responsibility, enforced via `_is_uniform_row_list`), stringifies values via
    `str()`, and uses tab as the column separator and newline as the row
    separator. This matches the TSV / TOON encoders shipped by the two
    upstream reference MCPs.
    """
    # Caller responsible for non-empty (`_is_uniform_row_list` excludes empty).
    keys = list(rows[0].keys())
    header = "\t".join(keys)
    body = "\n".join("\t".join("" if r.get(k) is None else str(r.get(k)) for k in keys) for r in rows)
    return f"{header}\n{body}"


def toon_or_json(data: Any) -> tuple[Literal["toon", "json"], str]:
    """Pick the wire format. Returns `(format_name, payload)`.

    - List-of-dicts with uniform keys → `("toon", "<encoded-string>")`.
    - Single dict / scalar / heterogeneous list → `("json", "<compact-json-string>")`.

    Heuristic kept tight: anything that doesn't fit the uniform-row shape goes
    JSON. This is the same call both reference MCPs make, just collapsed.
    """
    if _is_uniform_row_list(data):
        return "toon", _toon_encode(data)
    return "json", json.dumps(data, separators=(",", ":"), default=str, ensure_ascii=False)


class Response(BaseModel):
    """Typed envelope returned by `format_response` (v0.8).

    Attributes:
      format: ``"toon"`` or ``"json"`` — the wire format of `data`.
      data: the encoded payload as a string.
      truncated: True iff at least one string field was clipped past `truncate_at`.
      next_cursor: reserved for v0.9 pagination; always None today.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["toon", "json"]
    data: str
    truncated: bool
    next_cursor: str | None = None


def format_response(
    data: Any,
    *,
    filter: str = "",  # noqa: A002 — public API kwarg name is part of the contract
    fields: list[str] | None = None,
    truncate_at: int = DEFAULT_MAX_CHARS,
    marker: str = DEFAULT_MARKER,
) -> Response:
    """Run filter (CEL) → projection → truncation → format routing.

    Returns a `Response` with `.format`, `.data`, `.truncated`, `.next_cursor`.

    - `filter` — optional CEL boolean expression, applied only when `data` is a
      list of dicts. Uses `a2kit.projection.filter_records`.
    - `fields` — optional list of keys to keep per record (list-of-dicts only).
    - `truncate_at` — max char length per string before truncation.

    `.truncated == True` iff at least one string field was longer than `truncate_at`.
    """
    processed = _apply_filter_and_fields(data, filter_expr=filter, fields=fields)
    truncated_value = truncate(processed, truncate_at, marker)
    fmt, payload = toon_or_json(truncated_value)
    return Response(format=fmt, data=payload, truncated=marker in payload)


def _apply_filter_and_fields(data: Any, *, filter_expr: str, fields: list[str] | None) -> Any:
    """Apply CEL filter then field projection, but only on list-of-dicts shapes."""
    if not (filter_expr or fields):
        return data
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        return data
    from a2kit import projection  # noqa: PLC0415 — keep CEL import lazy

    rows: list[dict[str, Any]] = data
    if filter_expr:
        rows = projection.filter_records(rows, expr=filter_expr)
    if fields:
        rows = projection.project_fields(rows, fields=fields)
    return rows


__all__ = ["DEFAULT_MARKER", "DEFAULT_MAX_CHARS", "Response", "format_response", "toon_or_json", "truncate"]
