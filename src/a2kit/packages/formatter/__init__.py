"""Output formatting primitives for the v1 thin core — the ``render`` seam, ``format_response``, and the wire encoders."""

from __future__ import annotations

from typing import Any

from .formats import FormatHint, FormatName
from .inference import EncodingPlan, build_encoding_plan, infer_format_hint
from .render import Consumer, Rendered, render, render_execute, render_plain
from .response import Page, Response

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


def _plan_for_hint(format_hint: FormatHint) -> EncodingPlan:
    """Map the legacy ``format_hint`` vocabulary to an :class:`EncodingPlan`."""
    if format_hint == "tsv":
        return EncodingPlan("tsv")
    if format_hint == "page-tsv":
        return EncodingPlan("page-tsv")
    # "auto" and "json" both encode JSON when called outside a tool dispatch.
    return EncodingPlan("json")


def format_response(
    raw: Any,
    *,
    format_hint: FormatHint = "auto",
) -> Response:
    """Encode ``raw`` per ``format_hint`` and return a :class:`Response` — a
    thin ``format_hint``-shaped adapter over :func:`render` for callers that
    still speak the hint vocabulary (``auto`` / ``json`` / ``tsv`` / ``page-tsv``).
    """
    if format_hint == "page-tsv" and not isinstance(raw, Page):
        msg = f"format_hint='page-tsv' requires a Page instance, got {type(raw).__name__}"
        raise TypeError(msg)

    rendered = render(raw, "llm", plan=_plan_for_hint(format_hint))
    return Response(data=rendered.text, format=rendered.format)


__all__ = [
    "DEFAULT_MAX_CHARS",
    "TRUNCATION_MARKER",
    "Consumer",
    "EncodingPlan",
    "FormatHint",
    "FormatName",
    "Page",
    "Rendered",
    "Response",
    "build_encoding_plan",
    "format_response",
    "infer_format_hint",
    "render",
    "render_execute",
    "render_plain",
    "truncate",
]
