"""Tests for a2kit.testing — schema snapshot harness."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from a2kit import SchemaSnapshotMismatch
from a2kit.testing import assert_schemas_match, snapshot_schemas

if TYPE_CHECKING:
    from pathlib import Path


class Out(BaseModel):
    """Module-scoped output model so FastMCP can evaluate the annotation."""

    x: int


def _make_server() -> FastMCP:
    s = FastMCP("test")

    @s.tool()
    def get_widget(widget_id: int) -> dict:
        """Fetch a widget."""
        return {"id": widget_id}

    @s.tool()
    def list_widgets(limit: int = 50) -> dict:
        """List widgets."""
        return {"items": []}

    return s


def test_snapshot_schemas_writes_one_file_per_tool(tmp_path: Path) -> None:
    server = _make_server()
    out = snapshot_schemas(server, tmp_path / "snap")
    assert set(out.keys()) == {"get_widget", "list_widgets"}
    for path in out.values():
        assert path.exists()
        # compact JSON: no leading whitespace, no newlines
        text = path.read_text()
        assert "\n" not in text
        # parses
        data = json.loads(text)
        assert "input_schema" in data


def test_snapshot_includes_output_schema_when_present(tmp_path: Path) -> None:
    s = FastMCP("t")

    @s.tool()
    def typed_tool(a: int) -> Out:
        return Out(x=a)

    out = snapshot_schemas(s, tmp_path)
    data = json.loads(out["typed_tool"].read_text())
    assert "output_schema" in data


def test_assert_schemas_match_passes_after_snapshot(tmp_path: Path) -> None:
    server = _make_server()
    snapshot_schemas(server, tmp_path)
    assert_schemas_match(server, tmp_path)


def test_assert_raises_when_directory_missing(tmp_path: Path) -> None:
    server = _make_server()
    with pytest.raises(SchemaSnapshotMismatch, match="does not exist"):
        assert_schemas_match(server, tmp_path / "nope")


def test_assert_detects_added_tool(tmp_path: Path) -> None:
    server = _make_server()
    snapshot_schemas(server, tmp_path)

    @server.tool()
    def new_tool(x: int) -> dict:
        return {}

    with pytest.raises(SchemaSnapshotMismatch, match="New tool"):
        assert_schemas_match(server, tmp_path)


def test_assert_detects_removed_tool(tmp_path: Path) -> None:
    server = _make_server()
    snapshot_schemas(server, tmp_path)
    server._tool_manager._tools.pop("get_widget")  # noqa: SLF001
    with pytest.raises(SchemaSnapshotMismatch, match="removed"):
        assert_schemas_match(server, tmp_path)


def test_assert_detects_changed_schema(tmp_path: Path) -> None:
    server = _make_server()
    snapshot_schemas(server, tmp_path)

    s2 = FastMCP("test")

    @s2.tool()
    def get_widget(widget_id: str) -> dict:  # type changed int -> str
        """Fetch a widget."""
        return {"id": widget_id}

    @s2.tool()
    def list_widgets(limit: int = 50) -> dict:
        """List widgets."""
        return {"items": []}

    with pytest.raises(SchemaSnapshotMismatch) as exc_info:
        assert_schemas_match(s2, tmp_path)
    assert "diff" not in str(exc_info.value).lower() or "---" in str(exc_info.value)
