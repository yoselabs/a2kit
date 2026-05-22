"""Response envelope + list-view types for the v1 thin-core formatter.

``Response`` is a frozen ``dataclass`` carrying the encoded wire payload + the
chosen format name. ``Page`` is a generic pydantic ``BaseModel`` (``Page[T]``)
so type-driven format routing can inspect the parameter and pick the right
encoder — scalar-only ``T`` routes ``Page[T]`` to the hybrid ``page-tsv``
wire format (JSON envelope, embedded TSV string for ``items``); anything else
falls back to JSON. ``ListViewMode`` stays a ``StrEnum`` with module-level
``Local`` / ``Passthrough`` aliases.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Generic, TypeVar

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .formats import FormatName


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
      data: encoded payload as a string (JSON or TSV text).
      format: ``"json"`` or ``"tsv"`` — wire format of ``data``. Hybrid
        ``page-tsv`` encoding sets ``format="json"`` because the outer
        envelope is JSON; the embedded TSV is signaled via ``_items_format``.
    """

    data: str
    format: FormatName


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Typed paginated result — the contract a tool returns when it owns
    pagination (``pagination=Passthrough`` on the decorator).

    The kit reads ``next_cursor`` (an opaque agent-only string — the kit never
    parses or interprets it; tools mint it, agents echo it back) and threads it
    through to the next call. ``items`` is the page payload.

    Annotate paginated tools as ``-> Page[Task]`` to opt the items into the
    hybrid ``page-tsv`` encoding (JSON envelope, embedded TSV string for
    ``items``) when ``Task``'s fields are all scalar after ``model_dump``.
    Bare ``Page`` (no parameter) routes to JSON.
    """

    items: list[T] = Field(default_factory=list)
    next_cursor: str | None = None


__all__ = [
    "ListViewMode",
    "Local",
    "Page",
    "Passthrough",
    "Response",
]
