"""Capability: render-stage readers see the same prose + envelope that
``ErrorEnvelopeStage`` produced. Per ``error-envelope-side-channel``.
"""

from __future__ import annotations

import pytest
from a2effect import AppError

from a2kit.packages.dispatch._render_state import (
    close_render_state,
    get_rendered_error,
    open_render_state,
)
from a2kit.packages.dispatch.envelope import (
    ErrorEnvelopeStage,
    format_error_prose,
)


class _Boom(AppError):
    kind = "infra"


async def test_get_rendered_error_matches_format_error_prose_and_envelope() -> None:
    """The reader retrieves a RenderedError matching the writer's output."""
    stage = ErrorEnvelopeStage()

    async def body() -> None:
        raise _Boom("db down")

    wrapped = stage.wrap(body, spec=None)
    token = open_render_state()
    try:
        with pytest.raises(_Boom) as info:
            await wrapped()
        exc = info.value
        rendered = get_rendered_error(exc)
        assert rendered is not None
        assert rendered.prose == format_error_prose(exc)
        assert rendered.envelope == exc.to_envelope_dict()
    finally:
        close_render_state(token)
