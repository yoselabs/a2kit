"""Output formatting primitives for the v1 thin core — the ``render`` seam, ``format_response``, and the wire encoders.

The implementation lives in named submodules: ``render`` (the
consumer-aware seam), ``inference`` (format inference), ``response`` (the
``Response`` / ``Page`` types), ``hint`` (the ``format_response`` adapter),
and ``truncation`` (the payload cap).
"""

from __future__ import annotations

from .formats import FormatHint, FormatName
from .hint import format_response
from .inference import EncodingPlan, build_encoding_plan, infer_format_hint, is_basemodel
from .prune import PruneEmpty
from .render import Consumer, Rendered, render, render_execute, render_plain
from .response import Page, Response
from .truncation import DEFAULT_MAX_CHARS, TRUNCATION_MARKER, truncate

__all__ = [
    "DEFAULT_MAX_CHARS",
    "TRUNCATION_MARKER",
    "Consumer",
    "EncodingPlan",
    "FormatHint",
    "FormatName",
    "Page",
    "PruneEmpty",
    "Rendered",
    "Response",
    "build_encoding_plan",
    "format_response",
    "infer_format_hint",
    "is_basemodel",
    "render",
    "render_execute",
    "render_plain",
    "truncate",
]
