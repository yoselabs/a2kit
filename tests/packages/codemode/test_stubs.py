"""BDD specs — monty type-stub generation from tool descriptors.

a2kit generates dataclass mirrors + one `Literal` overload of `call_tool`
per tool so the type-checker can validate sandbox code (spike F5).
"""

from __future__ import annotations

from pydantic import BaseModel

from a2kit.packages.codemode.marshal import dataclass_mirror
from a2kit.packages.codemode.stubs import generate_stubs
from a2kit.packages.formatter import Page


class Task(BaseModel):
    id: int
    title: str


class TestStubGeneration:
    """Requirement: a2kit generates monty type-stubs from tool descriptors."""

    def test_stubs_include_a_dataclass_mirror_per_return_type(self):
        # GIVEN a tool annotated -> Page[Task]
        stubs = generate_stubs([("list_tasks", Page[Task])])
        # THEN they declare dataclass mirrors of Page and Task
        task_name = dataclass_mirror(Task).__name__
        page_name = dataclass_mirror(Page[Task]).__name__
        assert f"class {task_name}:" in stubs
        assert f"class {page_name}:" in stubs
        assert "id: int" in stubs
        assert "title: str" in stubs
        assert f"items: list[{task_name}]" in stubs

    def test_stubs_include_one_literal_overload_per_tool(self):
        stubs = generate_stubs([("list_tasks", Page[Task]), ("count_tasks", int)])
        assert stubs.count("@overload") == 2
        assert "Literal['list_tasks']" in stubs
        assert "Literal['count_tasks']" in stubs
        # the general fallback overload implementation is present
        assert "async def call_tool(name: str, params: dict) -> Any: ..." in stubs
