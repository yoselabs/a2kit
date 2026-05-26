"""Capability: ``AppError`` stays a pure domain value after dispatch.

Per ``error-envelope-side-channel`` (2026-05-27): ``ErrorEnvelopeStage``
writes prose + envelope to the side channel, NOT to attributes on the
exception instance.
"""

from __future__ import annotations

import pytest
from a2effect import AppError

from a2kit.packages.dispatch._render_state import (
    close_render_state,
    get_rendered_error,
    open_render_state,
)
from a2kit.packages.dispatch.envelope import ErrorEnvelopeStage


class _Boom(AppError):
    kind = "infra"


async def test_app_error_instance_is_unmutated() -> None:
    """After the envelope stage runs, the AppError has no render attrs."""
    stage = ErrorEnvelopeStage()

    async def body() -> None:
        raise _Boom("db down")

    wrapped = stage.wrap(body, spec=None)
    token = open_render_state()
    try:
        with pytest.raises(_Boom) as info:
            await wrapped()
        exc = info.value
        assert hasattr(exc, "rendered_prose") is False
        assert hasattr(exc, "rendered_envelope_dict") is False
        rendered = get_rendered_error(exc)
        assert rendered is not None
        assert rendered.prose.startswith("Service unavailable (_Boom):")
    finally:
        close_render_state(token)
