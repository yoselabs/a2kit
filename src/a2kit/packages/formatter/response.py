"""Response envelope + list-view types for the v1 thin-core formatter.

``Response`` is a frozen ``dataclass`` carrying the encoded wire payload + the
chosen format name. ``Page`` is a generic pydantic ``BaseModel`` (``Page[T]``)
so type-driven format routing can inspect the parameter and pick the right
encoder — scalar-only ``T`` routes ``Page[T]`` to the hybrid ``page-tsv``
wire format (JSON envelope, embedded TSV string for ``items``); anything else
falls back to JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .formats import FormatName


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
    pagination.

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
    "Page",
    "Response",
]
