"""CLI top-level ``list-tools`` + per-tool ``--help`` shows Raises (Group 16)."""

from __future__ import annotations

from typing import Annotated

from click.testing import CliRunner

import a2kit
from a2effect import AppError, Raises
from a2kit.packages.cli.builder import build_full_cli
from a2kit.testing import app_of


class _NotFound(AppError):
    kind = "input"
    cli_exit_code = 2
    hint = "verify the id from list_memories"


def _build_demo() -> a2kit.App:
    class R(a2kit.Router):
        slug = "mem"

        @a2kit.read()
        async def fetch(self, *, id: str) -> Annotated[dict, Raises(_NotFound)]:
            """Fetch a memory by id."""
            raise _NotFound(f"memory id {id!r} does not exist")

        @a2kit.read()
        async def ping(self) -> dict:
            """Liveness check."""
            return {"ok": True}

    return app_of("demo", R())


def test_list_tools_emits_table_with_every_tool() -> None:
    cli = build_full_cli(_build_demo())
    result = CliRunner().invoke(cli, ["list-tools"])
    assert result.exit_code == 0, result.output
    assert "mem.fetch" in result.output or "fetch" in result.output
    assert "mem.ping" in result.output or "ping" in result.output


def test_list_tools_json_emits_machine_form() -> None:
    cli = build_full_cli(_build_demo())
    result = CliRunner().invoke(cli, ["list-tools", "--json"])
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads(result.output)
    assert isinstance(payload, list)
    names = {t["name"] for t in payload}
    assert any(n.endswith("fetch") for n in names)
    assert any(n.endswith("ping") for n in names)


def test_tool_help_documents_raises_with_kind_and_exit() -> None:
    cli = build_full_cli(_build_demo())
    result = CliRunner().invoke(cli, ["mem", "fetch", "--help"])
    assert result.exit_code == 0, result.output
    out = result.output
    # The Errors block enumerates declared raises with kind + exit code + hint.
    assert "Errors:" in out or "Raises:" in out
    assert "_NotFound" in out
    assert "input" in out
    assert "exit 2" in out or "code 2" in out or "exit code: 2" in out
    # Click wraps help text across lines; collapse whitespace before matching.
    collapsed = " ".join(out.split())
    assert "verify the id from list_memories" in collapsed


def test_tool_help_omits_errors_block_when_no_raises() -> None:
    cli = build_full_cli(_build_demo())
    result = CliRunner().invoke(cli, ["mem", "ping", "--help"])
    assert result.exit_code == 0, result.output
    # ping has no Raises annotation; the Errors block is absent.
    assert "Errors:" not in result.output
    assert "Raises:" not in result.output
