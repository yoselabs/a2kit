"""Response envelope + list-view types for the v1 thin-core formatter.

The legacy ``a2kit.formatter`` exposed Pydantic-based ``Response`` / ``Page`` /
``ListViewMode``. The thin-core variant keeps the public surface minimal: plain
``dataclass`` for ``Response`` / ``Page`` and a ``StrEnum`` for ``ListViewMode``
with module-level ``Local`` / ``Passthrough`` aliases (matches the pattern the
decorator scanner already uses).

Format Literal drops ``"tsv"`` — the v1 wire formats are ``"toon"`` and
``"json"`` only. The legacy "TSV-with-JSON-cells" encoder is replaced by the
real ``toon_format`` library (wired in ``toon.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ListViewMode(StrEnum):
    """Execution mode for a list-view concern (filter / fields / pagination).

    - ``AUTO``: future-reserved sentinel for "let the runtime decide" (decorator
      defaults pick a mode based on the param shape). Currently unused by the
      decorator but present so external callers can spell the default.
    - ``LOCAL``: kit handles the concern post-call (CEL filter / projection /
      slicing on the returned data).
    - ``PASSTHROUGH``: kit declares the param to FastMCP / CLI and threads it to
      the tool body unchanged. Tool compiles it to whatever upstream protocol it
      speaks (JQL, SQL ``WHERE``, REST query, cursor-token, …).
    """

    AUTO = "auto"
    LOCAL = "local"
    PASSTHROUGH = "passthrough"


# Convenience aliases — the decorator API spells these as bare names.
Local = ListViewMode.LOCAL
Passthrough = ListViewMode.PASSTHROUGH


@dataclass(frozen=True)
class Response:
    """Encoded envelope returned by ``format_response``.

    Attributes:
      data: encoded payload as a string (TOON or JSON text).
      format: ``"toon"`` or ``"json"`` — wire format of ``data``.
    """

    data: str
    format: str  # "toon" | "json"


@dataclass(frozen=True)
class Page:
    """Typed paginated result — the contract a tool returns when it owns
    pagination (``pagination=Passthrough`` on the decorator).

    The kit reads ``next_cursor`` (an opaque agent-only string — the kit never
    parses or interprets it; tools mint it, agents echo it back) and threads it
    through to the next call. ``items`` is the page payload.
    """

    items: list[Any] = field(default_factory=list)
    next_cursor: str | None = None


__all__ = [
    "ListViewMode",
    "Local",
    "Page",
    "Passthrough",
    "Response",
]
