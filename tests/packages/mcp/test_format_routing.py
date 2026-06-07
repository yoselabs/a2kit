"""BDD specs — MCP surface format routing (consumer-aware-format-routing).

A tabular MCP tool emits TSV / page-tsv in the ``content`` channel and the
equivalent JSON in ``structuredContent``; ``code_mode`` selects the consumer
regime at ``build_mcp_server`` time.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel

import a2kit
from a2kit.runtime import build
from a2kit.packages.formatter import Page
from a2kit.packages.mcp import build_mcp_server


class Task(BaseModel):
    id: int
    title: str


class FormatRouterRouter(a2kit.Router):
    slug = "fr"

    @a2kit.read()
    async def rows(self) -> list[Task]:
        """Tabular — a flat list of scalar-only records."""
        return [Task(id=1, title="a"), Task(id=2, title="b")]

    @a2kit.read()
    async def one(self) -> Task:
        """Non-tabular — a single record."""
        return Task(id=7, title="solo")

    @a2kit.read()
    async def paged(self) -> Page[Task]:
        """A paginated result."""
        return Page[Task](items=[Task(id=1, title="a")], next_cursor="next")


@pytest.fixture
def app() -> a2kit.App:
    return a2kit.App("format-routing-test").add_router(FormatRouterRouter())


def _text(result: Any) -> str:
    return "\n".join(getattr(block, "text", "") for block in result.content)


class TestMcpFormatRouting:
    """Requirement: Format routing applies on the MCP surface."""

    @pytest.mark.anyio
    async def test_tabular_tool_emits_compressed_content(self, app: a2kit.App) -> None:
        # GIVEN an MCP server built with code_mode=False
        runtime = build(app)
        server = build_mcp_server(runtime, code_mode=False)
        async with runtime:
            # WHEN the tabular tool is called over MCP
            result = await server.call_tool("rows", {})
        # THEN content carries TSV, not raw JSON
        text = _text(result)
        assert text.splitlines()[0] == "id\ttitle"
        assert text.splitlines()[1] == "1\ta"
        # AND structuredContent carries the equivalent JSON
        assert result.structured_content == {
            "result": [
                {"id": 1, "title": "a"},
                {"id": 2, "title": "b"},
            ]
        }

    @pytest.mark.anyio
    async def test_non_tabular_tool_emits_json(self, app: a2kit.App) -> None:
        runtime = build(app)
        server = build_mcp_server(runtime, code_mode=False)
        async with runtime:
            result = await server.call_tool("one", {})
        # a single record is JSON, not TSV
        assert json.loads(_text(result)) == {"id": 7, "title": "solo"}

    @pytest.mark.anyio
    async def test_page_tool_emits_page_tsv(self, app: a2kit.App) -> None:
        runtime = build(app)
        server = build_mcp_server(runtime, code_mode=False)
        async with runtime:
            result = await server.call_tool("paged", {})
        envelope = json.loads(_text(result))
        assert envelope["_items_format"] == "tsv"
        assert envelope["next_cursor"] == "next"
        assert envelope["items"].splitlines()[0] == "id\ttitle"


class TestCompactToggle:
    """The --compact operator toggle drops the structuredContent channel."""

    @pytest.mark.anyio
    async def test_compact_drops_structured_content(self, app: a2kit.App) -> None:
        runtime = build(app)
        server = build_mcp_server(runtime, code_mode=False, compact=True)
        async with runtime:
            result = await server.call_tool("rows", {})
        # content still carries the compressed TSV
        assert _text(result).splitlines()[0] == "id\ttitle"
        # but structuredContent is dropped for non-conformant clients
        assert result.structured_content is None

    @pytest.mark.anyio
    async def test_compact_drops_structured_content_for_json_tool(self, app: a2kit.App) -> None:
        runtime = build(app)
        server = build_mcp_server(runtime, code_mode=False, compact=True)
        async with runtime:
            result = await server.call_tool("one", {})
        assert json.loads(_text(result)) == {"id": 7, "title": "solo"}
        assert result.structured_content is None


class TestCodeModeRegime:
    """Requirement: The code_mode flag selects the consumer regime."""

    @pytest.mark.anyio
    async def test_code_mode_off_renders_real_tool_for_llm(self, app: a2kit.App) -> None:
        # WHEN build_mcp_server(app, code_mode=False) is used
        runtime = build(app)
        server = build_mcp_server(runtime, code_mode=False)
        async with runtime:
            result = await server.call_tool("rows", {})
        # THEN a real tool called directly is llm-rendered (compressed)
        assert _text(result).splitlines()[0] == "id\ttitle"

    @pytest.mark.anyio
    async def test_code_mode_on_renders_real_tool_for_code(self, app: a2kit.App) -> None:
        # WHEN build_mcp_server(app, code_mode=True) is used
        runtime = build(app)
        server = build_mcp_server(runtime, code_mode=True)
        async with runtime:
            # a real tool stays callable by name; its result reaching the
            # sandbox is code-rendered — structured, never compressed
            result = await server.call_tool("rows", {})
        # content is NOT TSV-compressed under the code regime — it stays JSON
        assert json.loads(_text(result)) == [
            {"id": 1, "title": "a"},
            {"id": 2, "title": "b"},
        ]
        # the structured channel is the wrapped JSON the sandbox unwraps
        assert result.structured_content == {
            "result": [
                {"id": 1, "title": "a"},
                {"id": 2, "title": "b"},
            ]
        }
