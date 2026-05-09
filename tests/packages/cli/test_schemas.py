"""``schema`` Click command — TOON default, JSON opt-in, JSONL mode."""

from __future__ import annotations

import json

from click.testing import CliRunner

from a2kit.packages.cli.schemas import build_schema_command


def _run(app, args):
    return CliRunner().invoke(build_schema_command(app), args)


def test_schema_all_default_is_toon(app):
    result = _run(app, [])
    assert result.exit_code == 0, result.output
    # Three tools registered on the test router, names appear in output.
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
    assert "Unknown tool" in (result.output + (result.stderr or ""))


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
    """schema_command pipes through formatter.truncate; large outputs are capped."""
    import a2kit
    from a2kit.packages.formatter import DEFAULT_MAX_CHARS

    class Big(a2kit.Router):
        name = "big"

    # Build many tools so combined schema dict definitely exceeds the cap.
    for i in range(200):

        async def _tool(self, *, x: str = "x" * 600) -> dict:  # noqa: ARG001
            return {}

        _tool.__name__ = f"tool_{i:03d}"
        a2kit.read(_tool.__name__)(_tool)
        setattr(Big, _tool.__name__, _tool)

    app = a2kit.App("big").add_router(Big())
    result = CliRunner().invoke(build_schema_command(app), ["--format=toon"])

    assert result.exit_code == 0
    # Either the marker is present, or the output stayed under the cap.
    assert "(truncated)" in result.output or len(result.output) <= DEFAULT_MAX_CHARS + 100
