"""Capability: two concurrent calls each get distinct render-state slots.
One call's render state never leaks to the other.
"""

from __future__ import annotations

import asyncio

from a2effect import AppError

from a2kit.packages.dispatch._render_state import (
    RenderedError,
    close_render_state,
    get_rendered_error,
    open_render_state,
)
from a2kit.packages.dispatch.envelope import ErrorEnvelopeStage


class _Boom(AppError):
    kind = "infra"


async def _one_call(msg: str) -> tuple[BaseException, RenderedError | None]:
    stage = ErrorEnvelopeStage()

    async def body() -> None:
        raise _Boom(msg)

    wrapped = stage.wrap(body, spec=None)
    token = open_render_state()
    try:
        try:
            await wrapped()
            raise AssertionError("body should have raised")
        except _Boom as exc:
            rendered = get_rendered_error(exc)
            return exc, rendered
    finally:
        close_render_state(token)


async def test_two_concurrent_calls_get_distinct_render_states() -> None:
    """asyncio.gather of two calls: each sees its own RenderedError."""
    result_a, result_b = await asyncio.gather(_one_call("first"), _one_call("second"))
    exc_a, rendered_a = result_a
    exc_b, rendered_b = result_b
    assert rendered_a is not None
    assert rendered_b is not None
    assert "first" in rendered_a.prose
    assert "second" in rendered_b.prose
    assert exc_a is not exc_b
    assert rendered_a is not rendered_b
