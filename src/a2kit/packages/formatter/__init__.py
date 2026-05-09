"""Output formatting primitives for the v1 thin core.

Public API:
  - :func:`format_response` — orchestrates encoding (auto / json / tsv /
    page-tsv) and returns a :class:`Response` envelope.
  - :func:`truncate` — hard char-cap with a trailing marker.
  - :class:`Response`, :class:`Page`, :class:`Local`, :class:`Passthrough`,
    :class:`ListViewMode` — re-exported types.

Wire formats: ``"json"`` and ``"tsv"``. The hybrid ``"page-tsv"`` hint emits
a JSON envelope with an embedded TSV string for ``items``; the top-level wire
format is ``"json"`` and an ``_items_format`` discriminator marks the embedded
TSV. TOON was dropped after the R122 token-cost benchmark showed it is
dominated everywhere by TSV / JSON.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel

from .response import ListViewMode, Local, Page, Passthrough, Response


def _normalize_for_encoding(value: Any) -> Any:
    """Convert pydantic ``BaseModel`` instances to plain JSON-mode dicts so the
    JSON encoder sees only primitives + standard containers.

    Recurses through ``list``, ``tuple``, and ``dict`` containers; rewrites any
    ``BaseModel`` it finds via ``model_dump(mode="json")``. Other values
    (including strings, bytes, scalars, and arbitrary non-pydantic objects)
    pass through unchanged so non-pydantic inputs remain byte-identical.
    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: _normalize_for_encoding(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_for_encoding(v) for v in value]
    return value


FormatHint = Literal["auto", "json", "tsv", "page-tsv"]
FormatName = Literal["json", "tsv"]

DEFAULT_MAX_CHARS = 50_000
TRUNCATION_MARKER = "... (truncated)"


def truncate(payload: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Hard cap a payload string at ``max_chars`` characters.

    If ``payload`` is already within the cap, return it unchanged. Otherwise
    slice to ``max_chars`` and append ``"... (truncated)"``.

    This is a string-level truncation — callers wanting per-field clipping on
    structured data should do that before encoding.
    """
    if len(payload) <= max_chars:
        return payload
    return payload[:max_chars] + TRUNCATION_MARKER


def _encode_json(raw: Any) -> str:
    """Compact JSON encoding — same separators the legacy formatter used."""
    return json.dumps(raw, separators=(",", ":"), default=str, ensure_ascii=False)


def _derive_columns(rows: list[Any]) -> list[str]:
    if not rows:
        return []
    first = rows[0]
    if isinstance(first, BaseModel):
        return list(type(first).model_fields.keys())
    if isinstance(first, dict):
        return [str(k) for k in first]
    return []


def format_response(
    raw: Any,
    *,
    format_hint: FormatHint = "auto",
) -> Response:
    """Encode ``raw`` per ``format_hint`` and return a :class:`Response`.

    - ``format_hint="auto"``: defaults to compact JSON when called outside the
      tool-dispatch context. The CLI runtime passes the descriptor's cached
      hint directly, so ``"auto"`` here is a fallback for direct callers.
    - ``format_hint="json"`` / ``"tsv"``: force the named encoder.
    - ``format_hint="page-tsv"``: hybrid encoder for ``Page[T]`` envelopes —
      JSON outer, embedded TSV string for ``items``. Top-level wire format is
      ``"json"``; the ``_items_format`` discriminator inside the JSON tells
      consumers to parse ``items`` as TSV.

    Passing ``format_hint="toon"`` raises ``ValueError`` — TOON was removed
    after R122 showed it's dominated in token cost everywhere.
    """
    if format_hint == "toon":
        msg = (
            "format_hint='toon' is no longer supported. TOON was removed; "
            "use 'tsv', 'json', or 'page-tsv' (or leave 'auto' for the "
            "type-driven default)."
        )
        raise ValueError(msg)

    if format_hint == "tsv":
        from .tsv import encode_tsv as _encode_tsv

        rows = list(raw) if isinstance(raw, (list, tuple)) else []
        columns = _derive_columns(rows)
        return Response(data=_encode_tsv(rows, columns=columns), format="tsv")

    if format_hint == "page-tsv":
        from .page import encode_page_tsv as _encode_page_tsv

        if not isinstance(raw, Page):
            msg = (
                f"format_hint='page-tsv' requires a Page instance, got "
                f"{type(raw).__name__}"
            )
            raise TypeError(msg)
        return Response(data=_encode_page_tsv(raw), format="json")

    # "auto" and "json" both fall through to JSON when called outside a tool
    # dispatch context (no descriptor hint in scope).
    normalized = _normalize_for_encoding(raw)
    return Response(data=_encode_json(normalized), format="json")


__all__ = [
    "DEFAULT_MAX_CHARS",
    "TRUNCATION_MARKER",
    "FormatHint",
    "FormatName",
    "ListViewMode",
    "Local",
    "Page",
    "Passthrough",
    "Response",
    "format_response",
    "truncate",
]
