"""Output-format primitives — TOON / JSON heuristic + recursive truncation.

Promoted to a primitive at n=2 (a2db ships TSV+JSON, a2atlassian ships TOON+JSON).
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
- `format_response(data, *, truncate_at=2000)` — packages truncation + format
  routing into the canonical envelope: `{"format": ..., "data": ..., "truncated": bool}`.
"""

from __future__ import annotations

import json
from typing import Any

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
    separator. This matches both a2db `formatter._format_tsv` and a2atlassian
    `formatter._toon_encode`.
    """
    # Caller responsible for non-empty (`_is_uniform_row_list` excludes empty).
    keys = list(rows[0].keys())
    header = "\t".join(keys)
    body = "\n".join("\t".join("" if r.get(k) is None else str(r.get(k)) for k in keys) for r in rows)
    return f"{header}\n{body}"


def toon_or_json(data: Any) -> tuple[str, Any]:
    """Pick the wire format. Returns `(format_name, payload)`.

    - List-of-dicts with uniform keys → `("toon", "<encoded-string>")`.
    - Single dict / scalar / heterogeneous list → `("json", "<compact-json-string>")`.

    Heuristic kept tight: anything that doesn't fit the uniform-row shape goes
    JSON. This is the same call both reference MCPs make, just collapsed.
    """
    if _is_uniform_row_list(data):
        return "toon", _toon_encode(data)
    return "json", json.dumps(data, separators=(",", ":"), default=str, ensure_ascii=False)


def format_response(data: Any, *, truncate_at: int = DEFAULT_MAX_CHARS, marker: str = DEFAULT_MARKER) -> dict[str, Any]:
    """Run truncation, then format routing. Returns the canonical envelope.

    Envelope: `{"format": "toon"|"json", "data": <string>, "truncated": bool}`.

    `truncated=True` iff at least one string field was longer than `truncate_at`.
    Detection compares marker presence in the post-truncate string; cheaper than
    deep-walking twice.
    """
    truncated_value = truncate(data, truncate_at, marker)
    fmt, payload = toon_or_json(truncated_value)
    return {"format": fmt, "data": payload, "truncated": marker in payload}


__all__ = ["DEFAULT_MARKER", "DEFAULT_MAX_CHARS", "format_response", "toon_or_json", "truncate"]
