"""End-to-end: type-driven format routing via the CLI builder."""

from __future__ import annotations

import json

from click.testing import CliRunner
from pydantic import BaseModel

import a2kit
from a2kit.packages.cli.builder import build_full_cli
from a2kit.packages.formatter.response import Page


class Task(BaseModel):
    id: str
    title: str


class TaskWithLabels(BaseModel):
    id: str
    labels: list[str]


def _runner() -> CliRunner:
    return CliRunner()


class TestAutoRouting:
    def test_list_of_scalar_only_model_outputs_tsv(self):
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.list_("id", "title")
            async def list_x(self) -> list[Task]:
                return [Task(id="a", title="x"), Task(id="b", title="y")]
            tools = (list_x,)

        app = a2kit.App("t").add_router(TR())
        result = _runner().invoke(build_full_cli(app), ["tr", "list_x"])
        assert result.exit_code == 0, result.output
        # TSV header + 2 rows
        lines = result.output.strip().splitlines()
        assert lines[0] == "id\ttitle"
        assert lines[1] == "a\tx"
        assert lines[2] == "b\ty"

    def test_list_of_model_with_list_field_outputs_json(self):
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.list_("id")
            async def list_x(self) -> list[TaskWithLabels]:
                return [TaskWithLabels(id="a", labels=["x", "y"])]
            tools = (list_x,)

        app = a2kit.App("t").add_router(TR())
        result = _runner().invoke(build_full_cli(app), ["tr", "list_x"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output.strip())
        assert parsed == [{"id": "a", "labels": ["x", "y"]}]

    def test_page_of_scalar_only_outputs_hybrid(self):
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.read()
            async def page_x(self) -> Page[Task]:
                return Page[Task](items=[Task(id="a", title="x")], next_cursor="c")
            tools = (page_x,)

        app = a2kit.App("t").add_router(TR())
        result = _runner().invoke(build_full_cli(app), ["tr", "page_x"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output.strip())
        assert parsed["_items_format"] == "tsv"
        assert parsed["next_cursor"] == "c"

    def test_single_basemodel_outputs_json(self):
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.read()
            async def get(self, *, id: str = "a") -> Task:
                return Task(id=id, title="x")
            tools = (get,)

        app = a2kit.App("t").add_router(TR())
        result = _runner().invoke(build_full_cli(app), ["tr", "get"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output.strip())
        assert parsed == {"id": "a", "title": "x"}


class TestExplicitOverride:
    def test_explicit_json_overrides_tsv_default(self):
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.list_("id")
            async def list_x(self) -> list[Task]:
                return [Task(id="a", title="x")]
            tools = (list_x,)

        app = a2kit.App("t").add_router(TR())
        result = _runner().invoke(build_full_cli(app), ["tr", "list_x", "--format", "json"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output.strip())
        assert parsed == [{"id": "a", "title": "x"}]

    def test_toon_format_no_longer_offered(self):
        class TR(a2kit.Router):
            slug = "tr"
            name = "tr"

            @a2kit.read()
            async def get(self, *, id: str = "a") -> Task:
                return Task(id=id, title="x")
            tools = (get,)

        app = a2kit.App("t").add_router(TR())
        # click.Choice rejects the value at parse time
        result = _runner().invoke(build_full_cli(app), ["tr", "get", "--format", "toon"])
        assert result.exit_code != 0
        assert "toon" in (result.output + (result.stderr or "")).lower()
