"""Section 3 of `a2web-feedback-round-2`: MCP `ToolAnnotations` kwargs on verb decorators.

Gherkin:
  Scenario: read with annotations
    GIVEN @a2kit.read(idempotent=True, open_world=True, title="Fetch")
    WHEN the tool is stamped
    THEN meta.annotations carries readOnlyHint=True, idempotentHint=True,
         destructiveHint=False, openWorldHint=True, title="Fetch"

  Scenario: destructive on read raises
    GIVEN @a2kit.read(destructive=True)
    THEN TypeError at decoration time

  Scenario: write with destructive override
    GIVEN @a2kit.write(destructive=False, idempotent=True)
    THEN destructiveHint=False, idempotentHint=True

  Scenario: defaults are conservative
    GIVEN @a2kit.read() with no annotation kwargs
    THEN openWorldHint=False, idempotentHint=False
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.metadata import get_meta


def _meta_for(fn):
    return get_meta(fn)


def test_read_with_annotations() -> None:
    @a2kit.read(idempotent=True, open_world=True, title="Fetch Web Page")
    async def fetch() -> dict:
        return {}

    ann = _meta_for(fetch).annotations
    assert ann.readOnlyHint is True
    assert ann.idempotentHint is True
    assert ann.destructiveHint is False
    assert ann.openWorldHint is True
    assert ann.title == "Fetch Web Page"


def test_read_destructive_raises() -> None:
    with pytest.raises(TypeError, match="destructive"):

        @a2kit.read(destructive=True)
        async def boom() -> dict:
            return {}


def test_write_destructive_override() -> None:
    @a2kit.write(destructive=False, idempotent=True, title="Mark Complete")
    async def mark_complete() -> dict:
        return {}

    ann = _meta_for(mark_complete).annotations
    assert ann.readOnlyHint is False
    assert ann.destructiveHint is False
    assert ann.idempotentHint is True
    assert ann.title == "Mark Complete"


def test_write_default_destructive_true() -> None:
    @a2kit.write()
    async def delete_thing() -> dict:
        return {}

    ann = _meta_for(delete_thing).annotations
    assert ann.destructiveHint is True
    assert ann.openWorldHint is False
    assert ann.idempotentHint is False


def test_read_defaults_conservative() -> None:
    @a2kit.read()
    async def get_thing() -> dict:
        return {}

    ann = _meta_for(get_thing).annotations
    assert ann.readOnlyHint is True
    assert ann.idempotentHint is False
    assert ann.openWorldHint is False
    assert ann.destructiveHint is False
    assert ann.title is None


def test_tool_with_annotations() -> None:
    from a2kit.tool import tool as tool_decorator

    @tool_decorator(idempotent=True, open_world=True, destructive=False)
    async def neutral_op() -> dict:
        return {}

    ann = _meta_for(neutral_op).annotations
    assert ann.idempotentHint is True
    assert ann.openWorldHint is True
    assert ann.destructiveHint is False


def test_explicit_annotations_kwarg_wins() -> None:
    """``annotations=ToolAnnotations(...)`` is the escape hatch — overrides everything."""
    from mcp.types import ToolAnnotations

    explicit = ToolAnnotations(readOnlyHint=False, idempotentHint=True, title="Custom")

    from a2kit.tool import tool as tool_decorator

    @tool_decorator(annotations=explicit, idempotent=False)  # idempotent ignored
    async def custom() -> dict:
        return {}

    ann = _meta_for(custom).annotations
    assert ann is explicit
