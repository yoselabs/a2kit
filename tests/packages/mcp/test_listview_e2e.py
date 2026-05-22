"""End-to-end + envelope-shape tests for ``ListViewMiddleware``.

Exercises the actual middleware path via ``server.call_tool`` so the
``on_call_tool`` hook executes and rewrites ``ToolResult.structured_content``.
Also covers the helper ``_apply`` against pathological/empty shapes the
existing ``test_listview.py`` doesn't.
"""

from __future__ import annotations

import asyncio
from typing import Any

import a2kit
from a2kit.packages.mcp import build_mcp_server
from a2kit.packages.mcp.listview import _apply, _apply_to_items, _list_view_settings, _project_row

# --------------------------- module-level tools (no `self` binding issues) --------------------------- #


@a2kit.list_("id", "name", page_size=2)
async def list_things() -> list[dict[str, Any]]:
    return [
        {"id": 1, "name": "a", "extra": "drop"},
        {"id": 2, "name": "b", "extra": "drop"},
        {"id": 3, "name": "c", "extra": "drop"},
        {"id": 4, "name": "d", "extra": "drop"},
    ]


@a2kit.list_()
async def plain_things() -> list[dict[str, Any]]:
    return [{"id": 1, "extra": "keep"}]


@a2kit.read()
async def scalar_thing() -> dict[str, int]:
    return {"value": 42}


def _build_app() -> a2kit.App:
    class R(a2kit.Router):
        tools = ()
        slug = "things"
        name = "things"

    r = R()
    r._tools.extend([list_things, plain_things, scalar_thing])
    return a2kit.AppBuilder("e2e").add_router(r).build()


# --------------------------- end-to-end --------------------------- #


def test_listview_e2e_projects_default_fields_and_paginates() -> None:
    server = build_mcp_server(_build_app())

    async def _check() -> None:
        result = await server.call_tool("list_things", {})
        structured = result.structured_content
        assert isinstance(structured, dict)
        rows = structured["result"]
        assert rows == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]

    asyncio.run(_check())


def test_listview_e2e_passthrough_when_no_list_view_settings() -> None:
    server = build_mcp_server(_build_app())

    async def _check() -> None:
        result = await server.call_tool("plain_things", {})
        structured = result.structured_content
        assert isinstance(structured, dict)
        assert structured["result"] == [{"id": 1, "extra": "keep"}]

    asyncio.run(_check())


def test_listview_e2e_passthrough_for_non_list_dict_result() -> None:
    """Read-tool returning a dict — `_apply` returns it untouched."""
    server = build_mcp_server(_build_app())

    async def _check() -> None:
        result = await server.call_tool("scalar_thing", {})
        # Either structured_content is the dict itself, or wrapped in {"result": ...}.
        # Either way the middleware doesn't strip the "value" key.
        if isinstance(result.structured_content, dict):
            payload = result.structured_content
            if "result" in payload and isinstance(payload["result"], dict):
                payload = payload["result"]
            assert payload.get("value") == 42

    asyncio.run(_check())


# --------------------------- helper unit tests --------------------------- #


def test_list_view_settings_returns_none_for_missing_key() -> None:
    assert _list_view_settings({}) is None
    assert _list_view_settings({"extras": {"list_view": None}}) is None


def test_list_view_settings_returns_none_for_non_dict() -> None:
    assert _list_view_settings({"extras": {"list_view": "garbage"}}) is None


def test_list_view_settings_returns_dict_when_present() -> None:
    payload = {"default_fields": ("id",), "page_size": 5}
    assert _list_view_settings({"extras": {"list_view": payload}}) == payload


def test_project_row_passes_through_non_dict() -> None:
    assert _project_row(42, ("id",)) == 42
    assert _project_row("string", ("id",)) == "string"
    assert _project_row([1, 2], ("id",)) == [1, 2]


def test_project_row_drops_missing_fields() -> None:
    assert _project_row({"id": 1}, ("id", "missing")) == {"id": 1}


def test_apply_to_items_no_settings() -> None:
    items = [{"id": 1}, {"id": 2}]
    assert _apply_to_items(items, {}) == items


def test_apply_to_items_zero_page_size_ignored() -> None:
    items = [{"id": 1}, {"id": 2}]
    assert _apply_to_items(items, {"page_size": 0}) == items


def test_apply_to_items_negative_page_size_ignored() -> None:
    items = [{"id": 1}, {"id": 2}]
    assert _apply_to_items(items, {"page_size": -1}) == items


def test_apply_to_items_non_int_page_size_ignored() -> None:
    items = [{"id": 1}, {"id": 2}]
    assert _apply_to_items(items, {"page_size": "two"}) == items


def test_apply_empty_list() -> None:
    assert _apply([], {"default_fields": ("id",), "page_size": 10}) == []


def test_apply_list_of_non_dicts_passes_each_through() -> None:
    items: list[Any] = [42, "string", {"id": 1, "drop": "x"}]
    out = _apply(items, {"default_fields": ("id",)})
    assert out == [42, "string", {"id": 1}]


def test_apply_passes_through_dict_result() -> None:
    res = {"a": 1, "b": 2}
    assert _apply(res, {"default_fields": ("a",), "page_size": 1}) == res


def test_apply_passes_through_scalar_result() -> None:
    assert _apply(None, {"default_fields": ("id",)}) is None
    assert _apply(42, {"default_fields": ("id",)}) == 42
    assert _apply("hello", {"default_fields": ("id",)}) == "hello"


# --------------------------- middleware short-circuits --------------------------- #


def test_listview_middleware_passthrough_when_meta_missing() -> None:
    """A FastMCP tool registered without a2kit metadata must pass through
    the listview middleware unchanged — no `tool.meta["a2kit"]`."""
    from fastmcp import FastMCP

    from a2kit.packages.mcp.listview import ListViewMiddleware

    server = FastMCP(name="raw")
    server.add_middleware(ListViewMiddleware())

    @server.tool
    def raw_list() -> list[dict[str, int]]:
        return [{"id": 1, "extra": 99}, {"id": 2, "extra": 99}]

    async def _check() -> None:
        result = await server.call_tool("raw_list", {})
        structured = result.structured_content
        assert isinstance(structured, dict)
        rows = structured["result"]
        # No projection → `extra` survives.
        assert rows == [{"id": 1, "extra": 99}, {"id": 2, "extra": 99}]

    asyncio.run(_check())
