"""``<app> schema`` subcommand — JSON output, JSONL mode (Typer-backed)."""

from __future__ import annotations

import json

from click.testing import CliRunner

from a2kit.packages.cli.builder import build_full_cli


def _run(app, args):
    return CliRunner().invoke(build_full_cli(app), ["schema", *args])


def test_schema_all_default_lists_all_tools(app):
    result = _run(app, [])
    assert result.exit_code == 0, result.output
    assert "get_task" in result.output
    assert "list_tasks" in result.output
    assert "create_task" in result.output


def test_schema_specific_tool_returns_only_that(app):
    result = _run(app, ["get_task", "--format", "json"])
    assert result.exit_code == 0, result.output
    schema = json.loads(result.output.strip())
    assert schema["name"] == "get_task"
    assert "inputSchema" in schema


def test_schema_unknown_tool_errors(app):
    result = _run(app, ["does_not_exist", "--format", "json"])
    assert result.exit_code != 0


def test_schema_jsonl_mode(app):
    result = _run(app, ["--format", "json", "--jsonl"])
    assert result.exit_code == 0, result.output
    lines = [ln for ln in result.output.strip().splitlines() if ln]
    assert len(lines) == 3
    for ln in lines:
        parsed = json.loads(ln)
        assert "name" in parsed


def test_schema_jsonl_requires_json_format(app):
    result = _run(app, ["--jsonl"])
    assert result.exit_code != 0


def test_per_tool_schema_format_json(app):
    result = _run(app, ["list_tasks", "--format", "json"])
    assert result.exit_code == 0
    schema = json.loads(result.output.strip())
    assert schema["meta"]["verb"] == "list"
    assert schema["meta"]["router"] == "tasks"


def test_schema_output_respects_truncation_cap(monkeypatch):
    """schema subcommand pipes through formatter.truncate; large outputs are capped."""
    import a2kit
    from a2kit.packages.formatter import DEFAULT_MAX_CHARS

    class Big(a2kit.Router):
        tools = ()
        slug = "big"
        name = "big"

    generated = []
    for i in range(200):

        async def _tool(self, *, x: str = "x" * 600) -> dict:  # noqa: ARG001
            return {}

        _tool.__name__ = f"tool_{i:03d}"
        a2kit.read()(_tool)
        setattr(Big, _tool.__name__, _tool)
        generated.append(_tool)
    # Populate the tools tuple — required post
    # ``app-time-tools-tuple-validation``; programmatically generated
    # tools must still be listed.
    Big.tools = tuple(generated)

    app = a2kit.App("big").add_router(Big())
    result = CliRunner().invoke(build_full_cli(app), ["schema", "--format=json"])

    assert result.exit_code == 0
    assert "(truncated)" in result.output or len(result.output) <= DEFAULT_MAX_CHARS + 100
