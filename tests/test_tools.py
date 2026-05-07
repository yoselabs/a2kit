"""Tests for a2kit.tools — decorator + preserve_return_annotation."""

from __future__ import annotations

import asyncio

import pytest

from a2kit import InvalidToolReturnTypeError
from a2kit.tools import preserve_return_annotation, tool


def test_rejects_string_return_at_decoration_time() -> None:
    def my_tool(x: int) -> str:
        return str(x)

    with pytest.raises(InvalidToolReturnTypeError, match="my_tool"):
        tool()(my_tool)


def test_rejects_string_return_when_annotation_is_actual_string_value() -> None:
    """Catch the case where eval'd PEP-563 string is the literal "str"."""

    def my_tool(x: int):  # noqa: ANN201
        return str(x)

    my_tool.__annotations__ = {"return": "str"}
    with pytest.raises(InvalidToolReturnTypeError):
        tool()(my_tool)


def test_no_annotation_does_not_raise() -> None:
    def my_tool(x: int):  # noqa: ANN201
        return {"x": x}

    wrapped = tool()(my_tool)
    assert wrapped(1) == {"x": 1}


def test_sync_passes_through_when_no_enricher() -> None:
    def my_tool(x: int) -> dict:
        if x < 0:
            raise ValueError("neg")
        return {"x": x}

    wrapped = tool()(my_tool)
    assert wrapped(2) == {"x": 2}
    with pytest.raises(ValueError, match="neg"):
        wrapped(-1)


def test_sync_routes_exceptions_through_enricher() -> None:
    def enrich(exc: Exception, tool_name: str | None = None) -> Exception:
        return RuntimeError(f"enriched:{tool_name}:{exc}")

    def my_tool(x: int) -> dict:
        raise ValueError("boom")

    wrapped = tool(enricher=enrich)(my_tool)
    with pytest.raises(RuntimeError, match="enriched:my_tool:boom"):
        wrapped(1)


def test_async_passes_through_and_routes_through_enricher() -> None:
    def enrich(exc: Exception, tool_name: str | None = None) -> Exception:
        return RuntimeError("enriched-async")

    async def ok_tool(x: int) -> dict:
        return {"x": x}

    async def bad_tool(x: int) -> dict:
        raise ValueError("oops")

    ok_wrapped = tool(enricher=enrich)(ok_tool)
    bad_wrapped = tool(enricher=enrich)(bad_tool)

    assert asyncio.run(ok_wrapped(3)) == {"x": 3}
    with pytest.raises(RuntimeError, match="enriched-async"):
        asyncio.run(bad_wrapped(0))


def test_async_passes_through_when_no_enricher() -> None:
    async def bad(x: int) -> dict:
        raise ValueError("raw")

    wrapped = tool()(bad)
    with pytest.raises(ValueError, match="raw"):
        asyncio.run(wrapped(0))


def test_return_annotation_mirrored_on_wrapper_and_wrapped() -> None:
    def my_tool(x: int) -> dict:
        return {"x": x}

    wrapped = tool()(my_tool)
    # under `from __future__ import annotations`, annotations are strings
    assert wrapped.__annotations__["return"] == my_tool.__annotations__["return"]
    assert wrapped.__annotations__["return"] in (dict, "dict")


def test_preserve_return_annotation_no_op_without_annotation() -> None:
    def fn():  # noqa: ANN201
        return 1

    out = preserve_return_annotation(fn)
    assert out is fn


def test_preserve_return_annotation_idempotent() -> None:
    def fn() -> dict:
        return {}

    preserve_return_annotation(fn)
    assert fn.__annotations__["return"] in (dict, "dict")
