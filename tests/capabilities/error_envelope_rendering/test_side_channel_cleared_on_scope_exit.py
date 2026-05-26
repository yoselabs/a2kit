"""Capability: the render-state slot is cleared on close. No leak across
calls within one process.
"""

from __future__ import annotations

from a2effect import AppError

from a2kit.packages.dispatch._render_state import (
    RenderedError,
    close_render_state,
    get_rendered_error,
    open_render_state,
    set_rendered_error,
)


class _Boom(AppError):
    kind = "infra"


def test_slot_is_cleared_after_close() -> None:
    """After close, get_rendered_error returns None for the prior exc."""
    exc = _Boom("x")
    token = open_render_state()
    try:
        set_rendered_error(exc, RenderedError(prose="p", envelope={"k": "v"}))
        assert get_rendered_error(exc) is not None
    finally:
        close_render_state(token)
    # After close, no slot — lookup returns None.
    assert get_rendered_error(exc) is None


def test_subsequent_open_starts_empty() -> None:
    """A fresh open does not carry entries from the previous scope."""
    exc1 = _Boom("a")
    token1 = open_render_state()
    set_rendered_error(exc1, RenderedError(prose="p", envelope={}))
    close_render_state(token1)

    exc2 = _Boom("b")
    token2 = open_render_state()
    try:
        # Fresh slot — exc1's entry MUST NOT be present.
        assert get_rendered_error(exc1) is None
        assert get_rendered_error(exc2) is None
    finally:
        close_render_state(token2)
