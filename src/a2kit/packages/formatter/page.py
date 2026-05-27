"""Hybrid ``page-tsv`` encoder for ``Page[T]`` envelopes.

Output is JSON-shaped: envelope metadata stays structured, ``items`` is a
single TSV string, and ``_items_format = "tsv"`` discriminates from a plain
JSON page where ``items`` would be a list. Top-level wire format remains
``"json"``; agents that don't know about ``_items_format`` still get a parseable
JSON object with a string ``items`` value (and can fall back to splitting on
``\\n`` if they want to inspect rows).
"""

from __future__ import annotations

import json
from typing import Any

from .response import Page  # noqa: TC001 — runtime use (isinstance, getattr)
from .tsv import encode_tsv


def _item_columns(page: Page) -> list[str]:
    """Pull the TSV header columns from the resolved item type's
    ``model_fields``. Falls back to the keys of the first item's dump when the
    type isn't statically resolvable (rare under the type-driven dispatch).
    """
    items_field = type(page).model_fields.get("items")
    if items_field is not None:
        from typing import get_args, get_origin

        ann = items_field.annotation
        if get_origin(ann) is list:
            args = get_args(ann)
            if len(args) == 1 and isinstance(args[0], type):
                item_cls = args[0]
                fields = getattr(item_cls, "model_fields", None)
                if fields is not None:
                    return list(fields.keys())

    # Fallback: read the first item's dump keys.
    if page.items:
        first = page.items[0]
        if hasattr(first, "model_dump"):
            return list(first.model_dump(mode="json").keys())
        if isinstance(first, dict):
            return [str(k) for k in first]
    return []


def assemble_page_envelope(envelope_no_items: dict[str, Any], rows: list[Any], columns: list[str]) -> str:
    """Shared envelope serializer: take a page-shaped dict (with ``items`` already
    excluded), the row list, and the resolved TSV columns; return the wire JSON
    string with ``items`` replaced by a TSV blob and the ``_items_format``
    discriminator set.
    """
    envelope: dict[str, Any] = dict(envelope_no_items)
    envelope["items"] = encode_tsv(rows, columns=columns)
    envelope["_items_format"] = "tsv"
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)


def encode_page_tsv(page: Page) -> str:
    """Encode a ``Page[T]`` as a JSON envelope with an embedded TSV string for
    ``items`` and a ``_items_format = "tsv"`` discriminator.
    """
    return assemble_page_envelope(
        page.model_dump(mode="json", exclude={"items"}),
        list(page.items),
        _item_columns(page),
    )
