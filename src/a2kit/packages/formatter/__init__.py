"""Output formatting primitives for the v1 thin core.

Public API:
  - :func:`format_response` — orchestrates encoding (auto / toon / json) and
    returns a :class:`Response` envelope.
  - :func:`truncate` — hard char-cap with a trailing marker.
  - :func:`toon_or_json` — the auto heuristic, exposed for callers that want to
    inspect the decision without encoding.
  - :class:`Response`, :class:`Page`, :class:`Local`, :class:`Passthrough`,
    :class:`ListViewMode` — re-exported types.

Wire formats: ``"toon"`` and ``"json"`` only. The legacy
"TSV-with-JSON-cells" encoder is gone (task 2.3.3) — TOON from the real
``toon-format`` library replaces it.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from .response import ListViewMode, Local, Page, Passthrough, Response
from .toon import encode_toon

FormatHint = Literal["auto", "toon", "json"]
FormatName = Literal["toon", "json"]

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


def toon_or_json(raw: Any) -> FormatName:
    """Pick TOON or JSON for ``raw`` using the auto heuristic.

    Rule: structured nested data (a list of dicts, OR any dict / list whose
    nesting depth is at least 2) → ``"toon"``; flat dicts, scalars, and
    strings → ``"json"``.

    Concretely:
      - ``list[dict]`` → toon (uniform-row case the LLM benefits from).
      - ``dict`` containing a dict / list value → toon.
      - ``list`` containing a list / dict → toon.
      - flat ``dict`` (only scalar values) → json.
      - any non-collection (str / int / float / bool / None) → json.
      - empty ``list`` / ``dict`` → json (TOON has no meaningful gain).
    """
    if isinstance(raw, list):
        if not raw:
            return "json"
        if all(isinstance(item, dict) for item in raw):
            return "toon"
        if any(isinstance(item, (list, dict)) for item in raw):
            return "toon"
        return "json"
    if isinstance(raw, dict):
        if not raw:
            return "json"
        if any(isinstance(v, (list, dict)) for v in raw.values()):
            return "toon"
        return "json"
    return "json"


def _encode_json(raw: Any) -> str:
    """Compact JSON encoding — same separators the legacy formatter used."""
    return json.dumps(raw, separators=(",", ":"), default=str, ensure_ascii=False)


def format_response(
    raw: Any,
    *,
    format_hint: FormatHint = "auto",
) -> Response:
    """Encode ``raw`` per ``format_hint`` and return a :class:`Response`.

    - ``format_hint="auto"`` (default): uses :func:`toon_or_json` to choose.
    - ``format_hint="toon"``: forces TOON via :func:`encode_toon`.
    - ``format_hint="json"``: forces compact JSON.

    Byte-identical guarantee: when the chosen format is ``"toon"``, the
    returned ``data`` equals ``toon_format.encode(raw)`` exactly.
    """
    if format_hint == "json":
        return Response(data=_encode_json(raw), format="json")
    if format_hint == "toon":
        return Response(data=encode_toon(raw), format="toon")
    # auto
    chosen = toon_or_json(raw)
    if chosen == "toon":
        return Response(data=encode_toon(raw), format="toon")
    return Response(data=_encode_json(raw), format="json")


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
    "toon_or_json",
    "truncate",
]
