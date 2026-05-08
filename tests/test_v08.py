"""Tests for v0.9 list-view triad (filter/fields/pagination x Local/Passthrough).

Replaces v0.8's `projection=True` tests, which were removed in the clean v0.9
break. Also covers the Page[T] generic, Response.next_cursor, and the
ephemeral lift (still v0.8, kept here for continuity).
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from pydantic import ValidationError

import a2kit
from a2kit import Local, Page, Passthrough
from a2kit._context import _RouterContext


# Module-level ConnectionInfo subclasses — must NOT be inside test fns or
# `inspect.get_annotations(fn, eval_str=True)` can't resolve forward refs.
class WConnV09(a2kit.ConnectionInfo):
    url: str


class _InfoA(a2kit.ConnectionInfo):
    url: str


class _InfoB(a2kit.ConnectionInfo):
    url: str


def _ctx(name: str = "test") -> _RouterContext[Any]:
    return _RouterContext(router_name=name, fqn=f"tests.{name}")


# ---- Local mode (kit handles) ----------------------------------------------


def test_local_filter_injects_param_and_runs_cel() -> None:
    rows = [{"a": 1}, {"a": 5}]

    @a2kit.tool(filter=Local)
    def list_widgets() -> list[dict]:
        return rows

    sig = inspect.signature(list_widgets)
    assert "filter" in sig.parameters
    out = list_widgets(filter="a > 3")  # type: ignore[call-arg]
    assert isinstance(out, a2kit.Response)
    assert "5" in out.data and "1" not in out.data.split("\n")[1]


def test_local_fields_picks_keys() -> None:
    rows = [{"a": 1, "b": 2}]

    @a2kit.tool(fields=Local)
    def list_widgets() -> list[dict]:
        return rows

    out = list_widgets(fields=["a"])  # type: ignore[call-arg]
    assert "b" not in out.data


def test_local_pagination_slices_and_emits_cursor() -> None:
    rows = [{"i": i} for i in range(10)]

    @a2kit.tool(pagination=Local)
    def list_widgets() -> list[dict]:
        return rows

    page1 = list_widgets(limit=4)  # type: ignore[call-arg]
    assert isinstance(page1, a2kit.Response)
    assert page1.next_cursor is not None
    # second page via cursor
    page2 = list_widgets(limit=4, cursor=page1.next_cursor)  # type: ignore[call-arg]
    # page1 + page2 = 8 of 10; third page covers remainder, cursor goes None
    page3 = list_widgets(limit=4, cursor=page2.next_cursor)  # type: ignore[call-arg]
    assert page3.next_cursor is None


def test_local_pagination_invalid_cursor_resets_to_zero() -> None:
    rows = [{"i": i} for i in range(3)]

    @a2kit.tool(pagination=Local)
    def list_widgets() -> list[dict]:
        return rows

    out = list_widgets(cursor="not-base64-at-all!@#")  # type: ignore[call-arg]
    # Recovers gracefully — returns first page.
    assert isinstance(out, a2kit.Response)
    assert "i" in out.data


def test_local_all_three_combined() -> None:
    rows = [{"id": i, "status": "open" if i % 2 else "closed"} for i in range(10)]

    @a2kit.tool(filter=Local, fields=Local, pagination=Local)
    def list_issues() -> list[dict]:
        return rows

    out = list_issues(filter="status == 'open'", fields=["id"], limit=2)  # type: ignore[call-arg]
    assert "status" not in out.data
    assert out.next_cursor is not None  # 5 open rows, took first 2


def test_local_no_args_yields_full_paginated_default() -> None:
    rows = [{"a": 1}, {"a": 2}]

    @a2kit.tool(pagination=Local)
    def list_widgets() -> list[dict]:
        return rows

    out = list_widgets()  # type: ignore[call-arg]
    assert isinstance(out, a2kit.Response)
    assert out.next_cursor is None  # 2 rows < default limit 50


# ---- Passthrough mode (tool handles) ---------------------------------------


def test_passthrough_filter_threads_to_fn() -> None:
    seen: list[str] = []

    @a2kit.tool(filter=Passthrough)
    def list_issues(filter: str = "") -> list[dict]:  # noqa: A002
        seen.append(filter)
        return [{"id": 1}]

    out = list_issues(filter="status == 'open'")
    assert seen == ["status == 'open'"]
    # Response wrap because list-view mode is in play.
    assert isinstance(out, a2kit.Response)


def test_passthrough_pagination_unwraps_page_and_threads_cursor() -> None:
    @a2kit.tool(pagination=Passthrough)
    def list_issues(limit: int = 50, cursor: str | None = None) -> Page[dict]:
        return Page(items=[{"id": 1}, {"id": 2}], next_cursor="upstream-cursor-123")

    out = list_issues(limit=10)
    assert isinstance(out, a2kit.Response)
    assert out.next_cursor == "upstream-cursor-123"


def test_passthrough_missing_param_rejected_at_decoration() -> None:
    with pytest.raises(ValueError, match="filter"):

        @a2kit.tool(filter=Passthrough)
        def f() -> list[dict]:
            return []


def test_passthrough_pagination_missing_both_params_rejected() -> None:
    with pytest.raises(ValueError, match=r"limit.*cursor|cursor.*limit"):

        @a2kit.tool(pagination=Passthrough)
        def f() -> list[dict]:
            return []


# ---- Mixed modes ------------------------------------------------------------


def test_mixed_local_filter_passthrough_pagination() -> None:
    """Tool paginates upstream; kit filters within the page."""

    @a2kit.tool(filter=Local, pagination=Passthrough)
    def list_issues(limit: int = 50, cursor: str | None = None) -> Page[dict]:
        return Page(
            items=[{"id": 1, "status": "open"}, {"id": 2, "status": "closed"}],
            next_cursor="next-page",
        )

    out = list_issues(filter="status == 'open'", limit=10)  # type: ignore[call-arg]
    assert "open" in out.data and "closed" not in out.data
    assert out.next_cursor == "next-page"


# ---- Collision rejection ---------------------------------------------------


def test_local_collision_with_existing_filter_param_rejected() -> None:
    with pytest.raises(ValueError, match=r"\['filter'\]"):

        @a2kit.tool(filter=Local)
        def f(filter: str = "") -> list[dict]:  # noqa: A002
            return []


# ---- Defensive type handling -----------------------------------------------


def test_local_non_str_filter_silently_ignored() -> None:
    rows = [{"a": 1}]

    @a2kit.tool(filter=Local)
    def list_widgets() -> list[dict]:
        return rows

    out = list_widgets(filter=123)  # type: ignore[call-arg]
    # Bad type → empty filter → all rows pass.
    assert "1" in out.data


def test_local_non_list_fields_silently_ignored() -> None:
    rows = [{"a": 1}]

    @a2kit.tool(fields=Local)
    def list_widgets() -> list[dict]:
        return rows

    out = list_widgets(fields="nope")  # type: ignore[call-arg]
    # Bad type → no projection.
    assert "a" in out.data


def test_local_invalid_limit_falls_back_to_default() -> None:
    rows = [{"i": i} for i in range(3)]

    @a2kit.tool(pagination=Local)
    def list_widgets() -> list[dict]:
        return rows

    out = list_widgets(limit=-5)  # type: ignore[call-arg]
    # negative → fall back to 50 → all 3 fit, no cursor.
    assert out.next_cursor is None


# ---- Non-list result bypasses list-view processing -------------------------


def test_listview_bypasses_for_scalar_result() -> None:
    @a2kit.tool(filter=Local)
    def get_count() -> dict:
        return {"count": 5}

    out = get_count()  # type: ignore[call-arg]
    # Single dict isn't list-view-shaped → no Response wrap.
    assert out == {"count": 5}


# ---- Signature splicing accommodates VAR_KEYWORD ---------------------------


def test_local_params_inserted_before_var_keyword() -> None:
    @a2kit.tool(filter=Local)
    def f(**extra: Any) -> list[dict]:
        return []

    sig = inspect.signature(f)
    params = list(sig.parameters.values())
    assert params[-1].kind == inspect.Parameter.VAR_KEYWORD
    assert "filter" in sig.parameters


# ---- Page[T] model ---------------------------------------------------------


def test_page_model_frozen() -> None:
    p = Page(items=[{"a": 1}], next_cursor="x")
    with pytest.raises(ValidationError):
        p.items = []  # type: ignore[misc]


def test_page_default_next_cursor_none() -> None:
    p = Page(items=[])
    assert p.next_cursor is None


# ---- Response model ---------------------------------------------------------


def test_response_frozen() -> None:
    r = a2kit.format_response([{"a": 1}])
    with pytest.raises(ValidationError):
        r.format = "json"  # type: ignore[misc]


async def test_response_next_cursor_default_none() -> None:
    r = a2kit.format_response([{"a": 1}])
    assert r.next_cursor is None


# ---- Connection auto-inject + typed-info DI (v0.9) -------------------------


async def test_typed_info_param_auto_inject_connection(tmp_path: Any) -> None:
    store: a2kit.ConnectionStore[WConnV09] = a2kit.ConnectionStore(tmp_path / "c", WConnV09)
    await store.save(WConnV09(key=("prod",), url="https://api"))

    @a2kit.tool(store=store)
    def show(info: WConnV09) -> dict:
        return {"url": info.url}

    sig = inspect.signature(show)
    assert "connection" in sig.parameters
    assert "info" not in sig.parameters
    out = show(connection="prod")  # type: ignore[call-arg]
    assert out == {"url": "https://api"}


def test_async_listview_path() -> None:
    """Async + has_listview exercises the async wrapper's listview branch."""
    rows = [{"id": i} for i in range(3)]

    @a2kit.tool(filter=Local)
    async def list_async() -> list[dict]:
        return rows

    import asyncio

    out = asyncio.run(list_async(filter="id > 0"))  # type: ignore[call-arg]
    assert isinstance(out, a2kit.Response)
    assert "id" in out.data


def test_multi_info_target_rejected() -> None:
    with pytest.raises(ValueError, match="multiple ConnectionInfo"):

        @a2kit.tool()
        def f(a: _InfoA, b: _InfoB) -> dict:
            return {}


# ---- Ephemeral lift (v0.8 carry-over) --------------------------------------


async def test_ephemeral_aware_store_short_circuits() -> None:
    from a2kit.scaffold import _EphemeralAwareStore

    class _Conn(a2kit.ConnectionInfo):
        url: str

    eph = {("eph",): _Conn(key=("eph",), url="https://eph")}
    proxy = _EphemeralAwareStore(None, eph)
    info = await proxy.load(("eph",))
    assert info.url == "https://eph"


async def test_ephemeral_aware_store_falls_through_to_base() -> None:
    from a2kit.exceptions import ConnectionNotFound
    from a2kit.scaffold import _EphemeralAwareStore

    proxy = _EphemeralAwareStore(None, {})
    with pytest.raises(ConnectionNotFound):
        await proxy.load(("missing",))
