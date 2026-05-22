"""Payload-size cap for formatter output — a hard character limit with marker."""

from __future__ import annotations

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
