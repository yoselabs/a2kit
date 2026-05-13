"""`@a2kit.list_` parameter parity with read/write/tool (Q3 of audit).

Locks the semantic-flag kwargs (`idempotent`, `open_world`, `title`)
on `@a2kit.list_` to match the other three verb decorators. The
`destructive` constraint mirrors `@a2kit.read`: list is read-shaped.
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


def test_list_idempotent_flag_propagates() -> None:
    @a2kit.list_("id", idempotent=True)
    async def f() -> list[dict[str, int]]:
        return [{"id": 1}]

    meta = get_meta(f)
    assert meta is not None
    ann = meta.annotations_as_dict()
    assert ann.get("idempotentHint") is True
    assert ann.get("readOnlyHint") is True


def test_list_open_world_flag_propagates() -> None:
    @a2kit.list_("id", open_world=True)
    async def f() -> list[dict[str, int]]:
        return [{"id": 1}]

    meta = get_meta(f)
    assert meta is not None
    ann = meta.annotations_as_dict()
    assert ann.get("openWorldHint") is True


def test_list_destructive_true_raises() -> None:
    """`destructive=True` on list raises (list is read-shaped, same as @read)."""
    with pytest.raises(TypeError, match="destructive"):

        @a2kit.list_("id", destructive=True)
        async def f() -> list[dict[str, int]]:
            return [{"id": 1}]


def test_list_combined_flags() -> None:
    @a2kit.list_("id", "name", title="Items", idempotent=True, open_world=True, page_size=20)
    async def f() -> list[dict[str, int]]:
        return [{"id": 1, "name": 2}]

    meta = get_meta(f)
    assert meta is not None
    ann = meta.annotations_as_dict()
    assert ann.get("title") == "Items"
    assert ann.get("idempotentHint") is True
    assert ann.get("openWorldHint") is True
    assert ann.get("readOnlyHint") is True
    assert meta.extras.list_view is not None
    assert meta.extras.list_view.page_size == 20
