"""Construction + invariants for Response / Page types."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from a2kit.packages.formatter import Page, Response


class Task(BaseModel):
    id: str
    title: str = ""


class TestResponse:
    def test_basic_construction(self):
        r = Response(data="hello", format="json")
        assert r.data == "hello"
        assert r.format == "json"

    def test_frozen(self):
        r = Response(data="x", format="json")
        with pytest.raises(Exception):  # FrozenInstanceError
            r.data = "y"  # type: ignore[misc]  # ty: ignore[invalid-assignment]  # why: test mutates a frozen/read-only property to set up a forced-error scenario

    def test_format_values(self):
        # Both wire formats are valid `FormatName` values.
        assert Response(data="a\tb", format="tsv").format == "tsv"
        assert Response(data="{}", format="json").format == "json"


class TestPage:
    def test_default_construction(self):
        p = Page()
        assert p.items == []
        assert p.next_cursor is None

    def test_with_items(self):
        p = Page(items=[{"id": 1}, {"id": 2}], next_cursor="abc")
        assert p.items == [{"id": 1}, {"id": 2}]
        assert p.next_cursor == "abc"

    def test_default_factory_isolated(self):
        # Each Page() must get its own list — factory, not shared default.
        p1 = Page()
        p2 = Page()
        assert p1.items is not p2.items


class TestPageGeneric:
    """Page is a generic pydantic model: ``Page[T]`` parameterizes ``items``."""

    def test_parameterized_validates(self):
        p = Page[Task](items=[Task(id="a"), Task(id="b")], next_cursor="c1")
        assert isinstance(p.items[0], Task)
        assert p.items[0].id == "a"
        assert p.next_cursor == "c1"

    def test_field_order_matches_declaration(self):
        # TSV header order is read off this; pydantic preserves declared order.
        assert list(Page.model_fields.keys()) == ["items", "next_cursor"]

    def test_subclass_can_add_fields(self):
        class SearchPage(Page[Task]):
            total: int = 0

        sp = SearchPage(items=[Task(id="a")], total=42)
        assert sp.total == 42
        assert sp.items[0].id == "a"

    def test_bare_construction_with_dicts_still_works(self):
        # Back-compat: legacy callers passed plain dicts as items.
        p = Page(items=[{"id": 1}], next_cursor=None)
        assert p.items == [{"id": 1}]
