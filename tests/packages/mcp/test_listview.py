"""``ListViewMiddleware`` projects fields and paginates list-of-dict results.

These tests poke the internal ``_apply`` helper directly (purely functional)
plus an end-to-end check via ``build_mcp_server`` to confirm settings are
read out of ``tool.meta["a2kit"]["list_view"]``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import a2kit
from a2kit.packages.mcp import build_mcp_server
from a2kit.packages.mcp.listview import _apply


def test_apply_projects_default_fields() -> None:
    items: list[dict[str, Any]] = [
        {"id": 1, "name": "a", "extra": "x"},
        {"id": 2, "name": "b", "extra": "y"},
    ]
    out = _apply(items, {"default_fields": ("id", "name")})
    assert out == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]


def test_apply_paginates() -> None:
    items = [{"id": i} for i in range(5)]
    out = _apply(items, {"page_size": 2})
    assert out == [{"id": 0}, {"id": 1}]


def test_apply_combined() -> None:
    items = [
        {"id": 1, "name": "a", "extra": "x"},
        {"id": 2, "name": "b", "extra": "y"},
        {"id": 3, "name": "c", "extra": "z"},
    ]
    out = _apply(items, {"default_fields": ("id",), "page_size": 2})
    assert out == [{"id": 1}, {"id": 2}]


def test_apply_passes_through_non_list() -> None:
    assert _apply({"single": True}, {"default_fields": ("single",)}) == {"single": True}
    assert _apply(42, {"page_size": 10}) == 42


def test_apply_no_settings_passthrough() -> None:
    items = [{"id": 1}]
    assert _apply(items, {}) == items


def test_listview_settings_serialized_into_tool_meta() -> None:
    """Round-trip check: settings on the decorator surface as a dict on
    ``tool.meta["a2kit"]["list_view"]`` so the middleware can read them."""

    class R(a2kit.Router):
        slug = "rows"
        name = "rows"

        @a2kit.list_("id", page_size=3)
        async def rows(self) -> list[dict[str, Any]]:
            return [{"id": i, "extra": "drop"} for i in range(10)]

        tools = (rows,)

    app = a2kit.App("a").add_router(R())
    server = build_mcp_server(app)

    async def _check() -> None:
        tools = {t.name: t for t in await server.list_tools()}
        rows = tools["rows"]
        a2kit_meta = (rows.meta or {})["a2kit"]
        lv = a2kit_meta["extras"]["list_view"]
        # asdict turns the tuple into a list (or keeps tuple — both fine).
        assert list(lv["default_fields"]) == ["id"]
        assert lv["page_size"] == 3

    asyncio.run(_check())
