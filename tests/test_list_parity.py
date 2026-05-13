"""`@a2kit.list_` parameter parity with read/write — v0.33.

`list_` is read-shaped. Per MCP spec, `idempotentHint` and
`destructiveHint` are meaningful only when `readOnlyHint=false`, so
both kwargs are rejected at decoration time on `@list_` (same rule
as `@read`). `open_world` and `title` remain user-settable.
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.metadata import get_meta


def test_list_title_propagates_to_annotations() -> None:
    @a2kit.list_("id", title="Projects")
    async def f() -> list[dict[str, int]]:
        return [{"id": 1}]

    meta = get_meta(f)
    assert meta is not None
    ann = meta.annotations_as_dict()
    assert ann.get("title") == "Projects"
    assert ann.get("readOnlyHint") is True


def test_list_open_world_flag_propagates() -> None:
    @a2kit.list_("id", open_world=True)
    async def f() -> list[dict[str, int]]:
        return [{"id": 1}]

    meta = get_meta(f)
    assert meta is not None
    ann = meta.annotations_as_dict()
    assert ann.get("openWorldHint") is True


def test_list_idempotent_true_raises() -> None:
    """`idempotent=True` on list raises (list is read-shaped, idempotent by spec)."""
    with pytest.raises(TypeError, match="idempotent"):

        @a2kit.list_("id", idempotent=True)
        async def f() -> list[dict[str, int]]:
            return [{"id": 1}]


def test_list_destructive_true_raises() -> None:
    """`destructive=True` on list raises (list is read-shaped, same as @read)."""
    with pytest.raises(TypeError, match="destructive"):

        @a2kit.list_("id", destructive=True)
        async def f() -> list[dict[str, int]]:
            return [{"id": 1}]


def test_list_combined_valid_flags() -> None:
    @a2kit.list_("id", "name", title="Items", open_world=True, page_size=20)
    async def f() -> list[dict[str, int]]:
        return [{"id": 1, "name": 2}]

    meta = get_meta(f)
    assert meta is not None
    ann = meta.annotations_as_dict()
    assert ann.get("title") == "Items"
    assert ann.get("openWorldHint") is True
    assert ann.get("readOnlyHint") is True
    assert meta.extras.list_view is not None
    assert meta.extras.list_view.page_size == 20
