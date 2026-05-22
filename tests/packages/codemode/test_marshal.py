"""BDD specs — dict→dataclass marshalling for the code-mode sandbox.

`call_tool` results cross the monty boundary as dataclasses so sandbox
code reads `page.items[0].title` (consumer-aware-format-routing §4).
"""

from __future__ import annotations

import dataclasses

from pydantic import BaseModel

from a2kit.packages.codemode.marshal import dataclass_mirror, marshal_result, unwrap_tool_result
from a2kit.packages.formatter import Page


class Task(BaseModel):
    id: int
    title: str


class TestDataclassMarshalling:
    """Requirement: call_tool marshals results into the sandbox as dataclasses."""

    def test_single_model_marshals_to_dataclass(self):
        marshalled = marshal_result({"id": 1, "title": "solo"}, Task)
        # attribute access, not subscript
        assert marshalled.title == "solo"
        assert marshalled.id == 1
        assert dataclasses.is_dataclass(marshalled)

    def test_nested_page_yields_attribute_access_all_the_way_down(self):
        # GIVEN a tool annotated -> Page[Task]
        payload = {
            "items": [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}],
            "next_cursor": "c1",
        }
        page = marshal_result(payload, Page[Task])
        # THEN page.items[0].title and page.next_cursor are valid
        assert page.items[0].title == "a"
        assert page.items[1].title == "b"
        assert page.next_cursor == "c1"

    def test_scalar_passes_through(self):
        assert marshal_result(7, int) == 7
        assert marshal_result(None, Task) is None

    def test_mirror_is_stable_per_model(self):
        assert dataclass_mirror(Task) is dataclass_mirror(Task)

    def test_marshals_a_list_of_models(self):
        out = marshal_result([{"id": 1, "title": "a"}, {"id": 2, "title": "b"}], list[Task])
        assert [t.title for t in out] == ["a", "b"]

    def test_marshals_an_optional_model_field(self):
        marshalled = marshal_result({"id": 3, "title": "z"}, Task | None)
        assert marshalled.title == "z"

    def test_non_dict_value_for_a_model_annotation_passes_through(self):
        assert marshal_result("not a dict", Task) == "not a dict"


class _FakeResult:
    def __init__(self, *, structured_content=None, content=None, meta=None):
        self.structured_content = structured_content
        self.content = content
        self.meta = meta


class TestUnwrapToolResult:
    """unwrap_tool_result extracts the sandbox-facing payload."""

    def test_prefers_structured_content(self):
        assert unwrap_tool_result(_FakeResult(structured_content={"a": 1})) == {"a": 1}

    def test_unwraps_a_wrapped_result(self):
        result = _FakeResult(
            structured_content={"result": [1, 2]},
            meta={"fastmcp": {"wrap_result": True}},
        )
        assert unwrap_tool_result(result) == [1, 2]

    def test_falls_back_to_text_content(self):
        class _Block:
            text = "hello"

        result = _FakeResult(structured_content=None, content=[_Block()])
        assert unwrap_tool_result(result) == "hello"
