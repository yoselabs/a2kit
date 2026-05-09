"""Construction + invariants for Response / Page / Local / Passthrough types."""

from __future__ import annotations

import pytest

from a2kit.packages.formatter import (
    ListViewMode,
    Local,
    Page,
    Passthrough,
    Response,
)


class TestResponse:
    def test_basic_construction(self):
        r = Response(data="hello", format="json")
        assert r.data == "hello"
        assert r.format == "json"

    def test_frozen(self):
        r = Response(data="x", format="toon")
        with pytest.raises(Exception):  # FrozenInstanceError
            r.data = "y"  # type: ignore[misc]

    def test_format_values(self):
        # The dataclass doesn't enforce the literal at runtime — that's the
        # type-checker's job — but the contract supports both wire formats.
        assert Response(data="a:1", format="toon").format == "toon"
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


class TestListViewMode:
    def test_enum_values(self):
        assert ListViewMode.AUTO.value == "auto"
        assert ListViewMode.LOCAL.value == "local"
        assert ListViewMode.PASSTHROUGH.value == "passthrough"

    def test_aliases(self):
        assert Local is ListViewMode.LOCAL
        assert Passthrough is ListViewMode.PASSTHROUGH

    def test_str_enum_behavior(self):
        # StrEnum members compare equal to their string value — important for
        # the decorator scanner that accepts either Mode.LOCAL or "local".
        assert ListViewMode.LOCAL == "local"
        assert ListViewMode.PASSTHROUGH == "passthrough"
