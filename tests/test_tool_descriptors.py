"""``App.tools()`` — typed introspection surface."""

from __future__ import annotations

from pydantic import BaseModel

import a2kit
from a2kit.packages.formatter.response import Page


class FlatTask(BaseModel):
    id: str
    title: str


class TaskWithList(BaseModel):
    id: str
    labels: list[str]


class TestDescriptorBasics:
    def test_typed_list_tool_gets_tsv_hint(self):
        class TasksRouter(a2kit.Router):
            slug = "tasks"

            @a2kit.list_("id", "title")
            async def list_tasks(self, *, q: str = "") -> list[FlatTask]:  # noqa: ARG002
                return []

            tools = (list_tasks,)

        app = a2kit.App("t").add_router(TasksRouter())
        descriptors = app.tools()
        assert len(descriptors) == 1
        d = descriptors[0]
        assert d.name == "list_tasks"
        assert d.format_hint == "tsv"
        # Resolved type, not a string
        assert d.return_type is not None
        assert d.return_type == list[FlatTask]

    def test_list_with_list_field_gets_json_hint(self):
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.list_("id")
            async def list_x(self) -> list[TaskWithList]:
                return []

            tools = (list_x,)

        app = a2kit.App("t").add_router(TR())
        d = app.tools()[0]
        assert d.format_hint == "json"

    def test_page_of_scalar_only_gets_page_tsv(self):
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.read()
            async def page_x(self) -> Page[FlatTask]:
                return Page[FlatTask]()

            tools = (page_x,)

        app = a2kit.App("t").add_router(TR())
        d = app.tools()[0]
        assert d.format_hint == "page-tsv"

    def test_single_basemodel_gets_json(self):
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.read()
            async def get(self, *, id: str) -> FlatTask:  # noqa: A002, ARG002
                return FlatTask(id=id, title="x")

            tools = (get,)

        app = a2kit.App("t").add_router(TR())
        d = app.tools()[0]
        assert d.format_hint == "json"


class TestDescriptorAccessors:
    def test_tools_still_returns_callables(self):
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.read()
            async def get(self, *, id: str) -> FlatTask:  # noqa: A002, ARG002
                return FlatTask(id=id, title="x")

            tools = (get,)

        app = a2kit.App("t").add_router(TR())
        tools = app.tools()
        assert len(tools) == 1
        # v0.33: app.tools() returns ToolDescriptor; callable lives on .fn
        assert callable(tools[0].fn)

    def test_descriptor_count_matches_tool_count(self):
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.read()
            async def a(self) -> FlatTask:
                return FlatTask(id="a", title="x")

            @a2kit.read()
            async def b(self) -> FlatTask:
                return FlatTask(id="b", title="y")

            tools = (
                a,
                b,
            )

        app = a2kit.App("t").add_router(TR())
        assert len(app.tools()) == len(app.tools()) == 2

    def test_descriptors_returned_as_copy(self):
        # Mutating the returned list must not affect internal state.
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.read()
            async def a(self) -> FlatTask:
                return FlatTask(id="a", title="x")

            tools = (a,)

        app = a2kit.App("t").add_router(TR())
        first = app.tools()
        first.clear()
        assert len(app.tools()) == 1
