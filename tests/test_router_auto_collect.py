"""Router auto-collects @a2kit-marked methods — no `tools=` tuple (ADR 0028 Wave 2).

The `tools = (...)` tuple is gone: `Router.__init_subclass__` collects
every method carrying verb-decorator metadata (the `_a2kit` marker), and
nothing else. This is marker-collection, NOT a `dir()` walk — plain
helper methods are never collected.
"""

from __future__ import annotations

from typing import cast

import a2kit

from tests._typed_records import Named


def test_router_without_tools_tuple_auto_collects() -> None:
    class R(a2kit.Router):
        slug = "r"

        @a2kit.read()
        def get_thing(self, *, id: int) -> dict:
            return {"id": id}

        @a2kit.write()
        def make_thing(self, *, name: str) -> dict:
            return {"name": name}

    names = {cast("Named", fn).__name__ for fn in R().bound_tools()}
    assert names == {"get_thing", "make_thing"}


def test_helper_methods_are_not_collected() -> None:
    class R(a2kit.Router):
        slug = "r"

        @a2kit.read()
        def get_thing(self, *, id: int) -> dict:
            return self._format(id)

        def _format(self, id: int) -> dict:  # plain helper — no marker
            return {"id": id}

    names = {cast("Named", fn).__name__ for fn in R().bound_tools()}
    assert names == {"get_thing"}


def test_collection_preserves_definition_order() -> None:
    class R(a2kit.Router):
        slug = "r"

        @a2kit.read()
        def alpha(self) -> dict:
            return {}

        @a2kit.read()
        def beta(self) -> dict:
            return {}

        @a2kit.read()
        def gamma(self) -> dict:
            return {}

    assert [cast("Named", fn).__name__ for fn in R().bound_tools()] == ["alpha", "beta", "gamma"]


def test_router_slug_and_surfaces_still_stamped() -> None:
    from a2kit.metadata import _get_meta

    class R(a2kit.Router):
        slug = "memo"

        @a2kit.read(surfaces=("cli",))
        def fetch(self) -> dict:
            return {}

    fn = R().bound_tools()[0]
    meta = _get_meta(fn)
    assert meta is not None
    assert meta.extras.router_slug == "memo"
    assert meta.extras.surfaces == {"mcp": "absent", "api": "absent", "cli": "listed"}
