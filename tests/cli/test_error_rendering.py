"""CLI surface: typed-error prose to stderr + kind-mapped exit codes (Group 16).

Implements `cli-response-encoding`:
- Default: prose to stderr, exit code from `AppError.cli_exit_code`
  (default by kind: input=2, auth=77, policy=77, infra=75, bug=70).
- `--json`: envelope JSON to stdout; stderr silent.
"""

from __future__ import annotations

from typing import Annotated

from click.testing import CliRunner

import a2kit
from a2effect import AppError, Raises
from a2effect.errors import InfrastructureError
from a2kit.packages.cli.builder import build_full_cli


class _NotFound(AppError):
    kind = "input"
    cli_exit_code = 2
    hint = "verify the id from list_memories"


def test_input_error_prose_to_stderr_exit_2() -> None:
    class R(a2kit.Router):
        slug = "mem"

        @a2kit.read()
        async def fetch(self, *, id: str) -> Annotated[dict, Raises(_NotFound)]:
            raise _NotFound(f"memory id {id!r} does not exist")

        tools = (fetch,)

    cli = build_full_cli(a2kit.App("t").add_router(R()))
    result = CliRunner().invoke(cli, ["mem", "fetch", "--id", "abc"])
    assert result.exit_code == 2
    assert "Input error (_NotFound):" in result.output
    assert "memory id 'abc' does not exist" in result.output
    assert "Hint: verify the id from list_memories" in result.output


def test_infra_error_exits_75() -> None:
    class R(a2kit.Router):
        slug = "svc"

        @a2kit.read()
        async def call(self) -> Annotated[dict, Raises(InfrastructureError)]:
            raise InfrastructureError("downstream gone")

        tools = (call,)

    cli = build_full_cli(a2kit.App("t").add_router(R()))
    result = CliRunner().invoke(cli, ["svc", "call"])
    assert result.exit_code == 75


def test_non_app_error_quarantined_exits_70() -> None:
    class R(a2kit.Router):
        slug = "broken"

        @a2kit.read()
        async def boom(self) -> dict:
            raise KeyError("missing")

        tools = (boom,)

    cli = build_full_cli(a2kit.App("t").add_router(R()))
    result = CliRunner().invoke(cli, ["broken", "boom"])
    assert result.exit_code == 70
    assert "Internal error (UnexpectedDefect):" in result.output
