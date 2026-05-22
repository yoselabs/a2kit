"""Body-model CLI UX — JSON-string flag decoded via ``model_validate_json``.

Locks in the breaking shape introduced by ``replace-cli-builder-with-typer``:
a tool parameter typed as ``body: SomeBaseModel`` is exposed on the CLI
as a single ``--body '<json>'`` flag rather than per-field flattened flags.
"""

from __future__ import annotations

from click.testing import CliRunner
from pydantic import BaseModel, Field

import a2kit
from a2kit.packages.cli.builder import build_full_cli


class _Item(BaseModel):
    name: str
    qty: int = Field(default=1)


class _BodyRouter(a2kit.Router):
    slug = "items"
    name = "items"

    @a2kit.write()
    async def create_item(self, *, body: _Item) -> dict:
        return {"name": body.name, "qty": body.qty}

    tools = (create_item,)


def _app():
    return a2kit.App("bodyapp").add_router(_BodyRouter())


def test_body_model_decodes_from_json_string() -> None:
    """``--body '{"name": "x", "qty": 3}'`` decodes into the BaseModel and reaches the tool."""
    app = _app()
    result = CliRunner().invoke(
        build_full_cli(app),
        ["items", "create_item", "--body", '{"name": "widget", "qty": 3}'],
    )
    assert result.exit_code == 0, result.output
    assert "widget" in result.output
    assert "3" in result.output


def test_body_model_missing_raises_missing_required() -> None:
    """Omitting ``--body`` surfaces a clean missing-required-option error."""
    app = _app()
    result = CliRunner().invoke(build_full_cli(app), ["items", "create_item"])
    assert result.exit_code != 0
    assert "--body" in result.output


def test_body_model_malformed_json_raises_bad_parameter() -> None:
    """A non-JSON ``--body`` value produces a clean BadParameter, not a Rich-formatted traceback."""
    app = _app()
    result = CliRunner().invoke(
        build_full_cli(app),
        ["items", "create_item", "--body", "not json"],
    )
    assert result.exit_code != 0
    # The error message should reference the param and the model.
    assert "--body" in result.output
    assert "_Item" in result.output


def test_body_model_validation_error_surfaces_pydantic_message() -> None:
    """Missing required field inside the JSON surfaces pydantic's validation error."""
    app = _app()
    result = CliRunner().invoke(
        build_full_cli(app),
        ["items", "create_item", "--body", '{"qty": 2}'],
    )
    assert result.exit_code != 0
    # pydantic mentions the missing field.
    assert "name" in result.output


def test_pretty_exceptions_disabled_plain_text_traceback() -> None:
    """``pretty_exceptions_enable=False`` — unenriched exceptions print plain text, no Rich panel."""

    class _BoomRouter(a2kit.Router):
        slug = "boom"
        name = "boom"

        @a2kit.read()
        async def explode(self) -> dict:
            raise RuntimeError("kaboom")

        tools = (explode,)

    app = a2kit.App("boomapp").add_router(_BoomRouter())
    result = CliRunner().invoke(build_full_cli(app), ["boom", "explode"])
    assert result.exit_code != 0
    # Plain message reaches stderr; no Rich box characters.
    out = result.output
    assert "kaboom" in out
    # Rich panels use box-drawing characters; assert they are absent.
    for ch in "╭╮╰╯│─":
        assert ch not in out, f"unexpected Rich panel character {ch!r} in CLI output"
