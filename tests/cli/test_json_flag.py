"""BDD — CLI `--json` flag (cli-response-encoding capability).

Success → model_dump JSON to stdout. Error → typed envelope JSON to stdout.
Stderr stays empty in both. Exit code kind-mapped. Mutually exclusive with
`--format`.
"""

from __future__ import annotations

import json
from typing import Annotated

from click.testing import CliRunner
from pydantic import BaseModel

import a2kit
from a2effect import AppError, Raises
from a2kit.packages.cli.builder import build_full_cli


class _Memory(BaseModel):
    id: str
    text: str


class _NotFound(AppError):
    kind = "input"
    cli_exit_code = 2
    hint = "verify the id from list_memories"


def _build() -> a2kit.App:
    class R(a2kit.Router):
        slug = "mem"

        @a2kit.read()
        async def fetch(self, *, id: str) -> Annotated[_Memory, Raises(_NotFound)]:
            if id == "missing":
                raise _NotFound(f"memory {id!r} not found")
            return _Memory(id=id, text="hello")

        @a2kit.read()
        async def list_simple(self) -> list[_Memory]:
            return [_Memory(id="a", text="A"), _Memory(id="b", text="B")]

        tools = (fetch, list_simple)

    return a2kit.App("demo").add_router(R())


def test_json_success_emits_model_dump_to_stdout() -> None:
    cli = build_full_cli(_build())
    result = CliRunner().invoke(cli, ["mem", "fetch", "--id=x", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {"id": "x", "text": "hello"}


def test_json_success_list_emits_array_of_dumps() -> None:
    cli = build_full_cli(_build())
    result = CliRunner().invoke(cli, ["mem", "list_simple", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == [
        {"id": "a", "text": "A"},
        {"id": "b", "text": "B"},
    ]


def test_json_error_emits_envelope_to_stdout() -> None:
    cli = build_full_cli(_build())
    result = CliRunner().invoke(cli, ["mem", "fetch", "--id=missing", "--json"])
    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert "error" in payload
    env = payload["error"]
    assert env["type"] == "_NotFound"
    assert env["kind"] == "input"
    assert env["retryable"] is False
    assert env["hint"] == "verify the id from list_memories"


def test_json_and_format_are_mutually_exclusive() -> None:
    cli = build_full_cli(_build())
    result = CliRunner().invoke(cli, ["mem", "fetch", "--id=x", "--json", "--format=json"])
    assert result.exit_code != 0
    assert "--json" in result.output
    assert "--format" in result.output


def test_default_mode_unchanged_when_json_absent() -> None:
    """Sanity: omitting --json keeps the previous prose-on-error behaviour."""
    cli = build_full_cli(_build())
    result = CliRunner().invoke(cli, ["mem", "fetch", "--id=missing"])
    assert result.exit_code == 2
    # Prose error, not JSON envelope
    out = " ".join(result.output.split())
    assert "_NotFound" in out or "Input error" in out
    # Stdout shouldn't have a JSON `error` key
    try:
        json.loads(result.output.strip().split("\n", 1)[0])
        json_parsed = True
    except (json.JSONDecodeError, IndexError):
        json_parsed = False
    assert not json_parsed, "default mode should not emit JSON"
