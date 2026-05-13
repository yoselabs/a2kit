"""Unit tests for ``find_context_param`` Optional-ctx rejection
(fix-mcp-dispatch-strips-ctx).

The dispatcher always binds ``ctx`` when declared; the
``Context | None`` / ``Optional[Context]`` annotation form has no
runtime path producing ``None`` and is rejected at decoration time.
"""

from __future__ import annotations

from typing import Optional, Union

import pytest

import a2kit
from a2kit.exceptions import A2KitInvalidContextAnnotation
from a2kit.signature import find_context_param


def test_mirror_stub_present() -> None:
    """Sentinel — proves the mirror file exists with a ``def test_*`` function."""


def test_plain_tool_context_accepted() -> None:
    async def fn(*, msg: str, ctx: a2kit.ToolContext) -> None:
        return None

    assert find_context_param(fn) == "ctx"


def test_no_ctx_declared_returns_none() -> None:
    async def fn(*, msg: str) -> None:
        return None

    assert find_context_param(fn) is None


def test_pep604_optional_ctx_rejected() -> None:
    async def fn(*, msg: str, ctx: a2kit.ToolContext | None = None) -> None:
        return None

    with pytest.raises(A2KitInvalidContextAnnotation) as excinfo:
        find_context_param(fn)
    assert "ctx" in excinfo.value.param_name
    assert "always bound" in excinfo.value.hint


def test_typing_optional_ctx_rejected() -> None:
    async def fn(*, msg: str, ctx: Optional[a2kit.ToolContext] = None) -> None:  # noqa: UP045
        return None

    with pytest.raises(A2KitInvalidContextAnnotation):
        find_context_param(fn)


def test_typing_union_ctx_none_rejected() -> None:
    async def fn(
        *,
        msg: str,
        ctx: Union[a2kit.ToolContext, None] = None,  # noqa: UP007
    ) -> None:
        return None

    with pytest.raises(A2KitInvalidContextAnnotation):
        find_context_param(fn)
