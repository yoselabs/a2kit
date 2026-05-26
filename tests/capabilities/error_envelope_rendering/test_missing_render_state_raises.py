"""Capability: when no render-state slot is open, the writer is a defensive
no-op and the reader returns None — the readers' explicit ``else``
branches handle this path. Per ``error-envelope-side-channel``.
"""

from __future__ import annotations

from a2effect import AppError

from a2kit.packages.dispatch._render_state import (
    RenderedError,
    get_rendered_error,
    set_rendered_error,
)


class _Boom(AppError):
    kind = "infra"


def test_set_is_noop_when_no_slot_open() -> None:
    """``set_rendered_error`` without an open slot does not raise."""
    exc = _Boom("x")
    # No slot opened — must NOT raise. The reader below returns None.
    set_rendered_error(exc, RenderedError(prose="p", envelope={}))
    assert get_rendered_error(exc) is None


def test_get_returns_none_when_no_slot_open() -> None:
    """``get_rendered_error`` without an open slot returns None."""
    exc = _Boom("x")
    assert get_rendered_error(exc) is None
