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
import types
import typing
from enum import Enum
from typing import Any, Generic, Literal, TypeVar, get_args, get_origin

from pydantic import BaseModel, ConfigDict

FormatName = Literal["tsv", "toon", "json"]

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


def _has_nested_values(rows: list[dict[str, Any]]) -> bool:
    """True if any cell in `rows` is a dict / list / tuple (i.e. not flat)."""
    return any(isinstance(v, (dict, list, tuple)) for r in rows for v in r.values())


def _encode_row_cell(value: Any) -> str:
    """Encode one cell. Nested values become compact JSON; scalars use `str()`."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"), default=str, ensure_ascii=False)
    return str(value)


def _tabular_encode(rows: list[dict[str, Any]]) -> str:
    """Header row + tab-separated rows. Cells with nested data get compact JSON.

    Used by both TSV (flat-row case) and TOON (nested-row case). The wire
    format is identical; the *label* on `Response.format` differs so the
    consuming agent knows whether to expect plain scalars or to JSON-parse
    individual cells before reasoning about them.
    """
    keys = list(rows[0].keys())
    header = "\t".join(keys)
    body = "\n".join("\t".join(_encode_row_cell(r.get(k)) for k in keys) for r in rows)
    return f"{header}\n{body}"


def _flat_pydantic_fields(model_cls: type[BaseModel]) -> bool | None:  # noqa: C901 — flat field decision is irreducibly branchy (single-arm/multi-arm/Any/nested)
    """Inspect a Pydantic model class — True if all fields are flat scalars,
    False if at least one is structurally nested (list/dict/BaseModel).

    Returns ``None`` if the field-type set is ambiguous (e.g. `Any`) — caller
    should fall back to runtime detection.

    v0.17: ``Optional[Union[A, B]]`` (and other multi-arm unions) are now
    handled — every non-None arm is examined; if any arm is structurally
    nested the field is non-flat, otherwise the field is flat.
    """
    saw_any = False
    for field in model_cls.model_fields.values():
        anno = field.annotation
        origin = get_origin(anno)
        # Optional[T] / Union[..., None] / `T | None` — strip None.
        if origin is typing.Union or origin is types.UnionType:
            non_none = [a for a in get_args(anno) if a is not type(None)]
            if len(non_none) == 1:
                anno = non_none[0]
                origin = get_origin(anno)
            elif len(non_none) > 1:  # pragma: no branch — `Union[None]` (zero non-None arms) is degenerate
                # Multi-arm union — examine each arm. Any nested arm makes the
                # field non-flat. Any `Any` arm forces ambiguity.
                arm_results = [_classify_arm(arm) for arm in non_none]
                if any(r is False for r in arm_results):
                    return False
                if any(r is None for r in arm_results):
                    saw_any = True
                continue
        if anno is Any:
            saw_any = True
            continue
        if origin in (list, tuple, set, dict, frozenset):
            return False
        if isinstance(anno, type) and issubclass(anno, BaseModel):
            return False
    if saw_any:
        return None
    return True


def _classify_arm(anno: Any) -> bool | None:
    """Classify one union arm as flat (True), nested (False), or ambiguous (None)."""
    if anno is Any:
        return None
    origin = get_origin(anno)
    if origin in (list, tuple, set, dict, frozenset):
        return False
    return not (isinstance(anno, type) and issubclass(anno, BaseModel))


def format_from_annotation(anno: Any) -> FormatName | None:  # noqa: PLR0911, C901 — decision tree spans 6 distinct shape categories
    """Precompute the wire format from a return type annotation, if possible.

    Returns:
      - ``"tsv"``: list of Pydantic models with all-flat fields, or ``Page[T]`` of same.
      - ``"toon"``: list of Pydantic models with at least one nested field, or ``Page[T]`` of same.
      - ``"json"``: scalar / single dict / single Pydantic / non-list shapes.
      - ``None``: insufficient info to lock (untyped `list`, `list[dict]`, ``Any``).

    v0.17 additions:
      - ``Awaitable[T]`` / ``Coroutine[..., ..., T]`` are unwrapped to ``T``
        before classification — async tools no longer lose precomputation.
      - Bare ``dict``, ``Mapping[...]``, ``TypedDict`` subclasses → ``"json"``.
    """
    if anno is None or anno is type(None):
        return "json"

    # Unwrap Awaitable[T] / Coroutine[Y, S, T] before classifying.
    anno = _unwrap_awaitable(anno)

    # Pydantic generics (Page[T] etc.) report themselves via metadata, not
    # the typing.get_origin/get_args path. Inspect first so Page[T] → tsv/toon.
    pyd_meta = getattr(anno, "__pydantic_generic_metadata__", None)
    if pyd_meta is not None:
        pyd_origin = pyd_meta.get("origin")
        pyd_args = pyd_meta.get("args", ())
        if pyd_origin is Page:
            return _list_format_from_item(pyd_args[0]) if pyd_args else None
        if pyd_origin is None and isinstance(anno, type) and issubclass(anno, Page):
            # Bare `Page` (unparametrised) — can't lock format.
            return None

    origin = get_origin(anno)
    args = get_args(anno)

    if origin in (list, tuple):
        if not args:  # pragma: no cover — get_origin returns None for bare list/tuple, so origin-in-list-tuple implies args were given
            return None
        return _list_format_from_item(args[0])

    # Single dict / Pydantic / scalar → JSON envelope.
    if origin is dict or _is_mapping_origin(origin):
        return "json"
    if anno is dict:
        return "json"
    if _is_typed_dict(anno):
        return "json"
    if isinstance(anno, type) and issubclass(anno, BaseModel):
        return "json"
    if isinstance(anno, type) and anno in (str, int, float, bool, bytes):
        return "json"
    return None


def _unwrap_awaitable(anno: Any) -> Any:
    """If `anno` is `Awaitable[T]` / `Coroutine[Y, S, T]`, return `T`. Else `anno`."""
    import collections.abc as _cabc  # noqa: PLC0415 — narrow scope, avoid module-top churn
    import typing as _t  # noqa: PLC0415

    origin = get_origin(anno)
    if origin in (_cabc.Awaitable, _t.Awaitable):
        args = get_args(anno)
        if args:  # pragma: no branch — get_origin returns None for bare Awaitable, so origin-match implies args
            return args[0]
    if origin in (_cabc.Coroutine, _t.Coroutine):
        args = get_args(anno)
        if len(args) == 3:  # pragma: no branch
            return args[2]
    return anno


def _is_mapping_origin(origin: Any) -> bool:
    """True if `origin` is a Mapping / MutableMapping origin from typing or collections.abc."""
    import collections.abc as _cabc  # noqa: PLC0415

    return origin in (_cabc.Mapping, _cabc.MutableMapping)


def _is_typed_dict(anno: Any) -> bool:
    """True if `anno` is a TypedDict subclass."""
    if not isinstance(anno, type):
        return False
    return (
        getattr(anno, "__total__", None) is not None
        and hasattr(anno, "__annotations__")
        and getattr(anno, "__required_keys__", None) is not None
    )


def _list_format_from_item(item_anno: Any) -> FormatName | None:
    """Decide tsv/toon for a list whose item annotation is `item_anno`.

    Pydantic item with all-flat fields → tsv; with nested → toon.
    `dict` items or `Any` → None (runtime).
    """
    if isinstance(item_anno, type) and issubclass(item_anno, BaseModel):
        flat = _flat_pydantic_fields(item_anno)
        if flat is True:
            return "tsv"
        if flat is False:
            return "toon"
        return None
    return None


def _dump_items(items: list[Any]) -> list[dict[str, Any]]:
    """Normalize a list of Pydantic-or-dict to a list of dicts.

    Used before tabular encoding so `Page[Pydantic]` and `list[Pydantic]` go
    through the same TSV/TOON path as raw `list[dict]`.

    Raises ``TypeError`` if any item is neither a Pydantic ``BaseModel`` nor a
    ``dict``. The pre-v0.17 behaviour silently dropped such items, which
    turned ``[1, 2, 3]`` into ``[]`` — a bug class that was easy to miss in
    tools whose row type drifted away from the kit's expectations.
    """
    out: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if isinstance(item, BaseModel):
            out.append(item.model_dump(mode="python"))
        elif isinstance(item, dict):
            out.append(item)
        else:
            raise TypeError(
                f"_dump_items expected dict or BaseModel rows; got {type(item).__name__} "
                f"at index {index}. Tabular encoding (TSV/TOON) requires uniform row shapes — "
                "wrap scalar/heterogeneous results so they go through the JSON path instead."
            )
    return out


def toon_or_json(data: Any) -> tuple[FormatName, str]:
    """Pick the wire format. Returns `(format_name, payload)`.

    Decision tree:
      - List-of-dicts with uniform keys, **all values flat** → ``"tsv"``.
        Pure tab-separated values; agent reads each cell as a scalar.
      - List-of-dicts with uniform keys, **at least one nested value** →
        ``"toon"``. Same TSV shape, but cells holding dicts/lists are
        compact-JSON-encoded inline. Agent JSON-parses those cells when needed.
      - Single dict / scalar / heterogeneous list → ``"json"`` (compact).

    Heuristic stays tight — anything that doesn't fit the uniform-row shape
    goes JSON.
    """
    if _is_uniform_row_list(data):
        if _has_nested_values(data):
            return "toon", _tabular_encode(data)
        return "tsv", _tabular_encode(data)
    return "json", json.dumps(data, separators=(",", ":"), default=str, ensure_ascii=False)


class Response(BaseModel):
    """Typed envelope returned by `format_response`.

    Attributes:
      format: ``"toon"`` or ``"json"`` — the wire format of `data`.
      data: the encoded payload as a string.
      truncated: True iff at least one string field was clipped past `truncate_at`.
      next_cursor: opaque cursor for the next page (v0.9). None when pagination
        is not in use or the result is the last page.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["tsv", "toon", "json"]
    data: str
    truncated: bool
    next_cursor: str | None = None


T = TypeVar("T")
"""Page item type. `_dump_items` flattens `BaseModel` instances and `dict`s
(other shapes degrade to runtime resolution); we leave `T` unbounded
because Pydantic v2 generic-bound interplay with `Page[dict[...]]` is fragile,
and a doc-only constraint is cheaper than the runtime cost."""


class Page(BaseModel, Generic[T]):
    """Typed paginated result — the contract a tool returns when it owns
    pagination (`pagination=Passthrough` on the decorator).

    The kit reads `next_cursor` (an opaque agent-only string — the kit never
    parses or interprets it; tools mint it, agents echo it back) and threads
    it through to the next call. `items` is the page payload; downstream
    Local filter/fields apply within the page.

    Convention: `T` is `BaseModel` (preferred — gives tsv/toon precompute)
    or `dict[str, Any]` (ad-hoc rows; format resolved at runtime). Other
    shapes (str/int/list/...) have no row interpretation and will surface
    as a JSON dump or a runtime error from `_dump_items`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[T]
    next_cursor: str | None = None


class ListViewMode(Enum):
    """Execution mode for a list-view concern (filter / fields / pagination).

    - ``Local``: the kit handles the concern post-call. The tool's function
      doesn't see the param; the kit applies CEL / projection / slicing on
      the returned data.
    - ``Passthrough``: the kit declares the param to FastMCP / the agent and
      threads it to the tool body unchanged. The tool compiles the param to
      whatever upstream protocol it speaks (JQL, SQL `WHERE`, REST query,
      cursor-token, …).

    Aliases ``Local`` and ``Passthrough`` are exported at module top-level for
    convenience.
    """

    LOCAL = "local"
    PASSTHROUGH = "passthrough"


Local = ListViewMode.LOCAL
Passthrough = ListViewMode.PASSTHROUGH


def format_response(
    data: Any,
    *,
    filter: str = "",  # noqa: A002 — public API kwarg name is part of the contract
    fields: list[str] | None = None,
    truncate_at: int = DEFAULT_MAX_CHARS,
    marker: str = DEFAULT_MARKER,
    format_hint: FormatName | None = None,
) -> Response:
    """Run filter (CEL) → projection → truncation → format routing.

    Returns a `Response` with `.format`, `.data`, `.truncated`, `.next_cursor`.

    - `filter` — optional CEL boolean expression, applied only when `data` is a
      list of dicts. Uses `a2kit.projection.filter_records`.
    - `fields` — optional list of keys to keep per record (list-of-dicts only).
    - `truncate_at` — max char length per string before truncation.
    - `format_hint` — pre-computed format from a return-type annotation. When
      set, skips the runtime list-of-dicts walk; the hint is trusted unless
      `data` is plainly incompatible (e.g. hint says ``"tsv"`` but `data` is
      a single dict).

    `.truncated == True` iff at least one string field was longer than `truncate_at`.
    """
    if isinstance(data, list) and data and isinstance(data[0], (BaseModel, dict)):
        # Only normalize when the list looks like rows. Heterogeneous /
        # scalar lists fall through to the JSON path; `_dump_items` would
        # otherwise raise on them.
        data = _dump_items(data)
    processed = _apply_filter_and_fields(data, filter_expr=filter, fields=fields)
    truncated_value = truncate(processed, truncate_at, marker)
    fmt, payload = _encode(truncated_value, format_hint)
    return Response(format=fmt, data=payload, truncated=marker in payload)


def _encode(data: Any, hint: FormatName | None) -> tuple[FormatName, str]:
    """Encode `data` honouring the format hint when shape-compatible."""
    if hint in ("tsv", "toon") and _is_uniform_row_list(data):
        return hint, _tabular_encode(data)
    if hint == "json":
        return "json", json.dumps(data, separators=(",", ":"), default=str, ensure_ascii=False)
    return toon_or_json(data)


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


__all__ = [
    "DEFAULT_MARKER",
    "DEFAULT_MAX_CHARS",
    "FormatName",
    "ListViewMode",
    "Local",
    "Page",
    "Passthrough",
    "Response",
    "format_from_annotation",
    "format_response",
    "toon_or_json",
    "truncate",
]
