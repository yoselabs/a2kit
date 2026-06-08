"""End-to-end CLI invocation: byte-identical formatter output."""

from __future__ import annotations

import json

from click.testing import CliRunner

import a2kit
from a2kit.packages.cli.builder import build_full_cli
from a2kit.packages.formatter import format_response


def test_e2e_read_tool_output_matches_formatter(app):
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["tasks", "get_task", "--task-id", "5"])
    assert result.exit_code == 0, result.output

    expected = format_response({"id": 5, "title": "task-5"}, format_hint="auto").data
    assert result.output.strip() == expected


def test_e2e_list_tool_with_default(app):
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["tasks", "list_tasks", "--limit", "3"])
    assert result.exit_code == 0, result.output

    raw = [{"id": i, "title": f"task-{i}"} for i in range(3)]
    expected = format_response(raw, format_hint="auto").data
    assert result.output.strip() == expected


def test_e2e_write_tool_with_bool_flag(app):
    cli = build_full_cli(app)
    result = CliRunner().invoke(
        cli,
        ["tasks", "create_task", "--title", "buy-milk", "--done"],
    )
    assert result.exit_code == 0, result.output

    expected = format_response({"title": "buy-milk", "done": True}, format_hint="auto").data
    assert result.output.strip() == expected


def test_e2e_force_json_format(app):
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["tasks", "get_task", "--task-id", "1", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload == {"id": 1, "title": "task-1"}


def test_e2e_per_tool_schema_flag(app):
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["tasks", "get_task", "--schema", "--format", "json"])
    assert result.exit_code == 0, result.output
    schema = json.loads(result.output.strip())
    assert schema["name"] == "tasks_get_task"
    assert "inputSchema" in schema


def test_e2e_required_param_missing_errors(app):
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["tasks", "get_task"])
    assert result.exit_code != 0


def test_e2e_complex_param_decoded_as_json():
    class R(a2kit.Router):
        slug = "demo"
        name = "demo"

        @a2kit.read()
        def echo_dict(self, *, payload: dict) -> dict:
            return {"got": payload}

    a = a2kit.App("demo").add_router(R())
    cli = build_full_cli(a)

    result = CliRunner().invoke(cli, ["demo", "echo_dict", "--payload", '{"a":1}', "--format", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output.strip()) == {"got": {"a": 1}}
