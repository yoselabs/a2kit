"""Unit tests for the per-call render-state side channel."""

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


def test_rendered_error_is_a_frozen_dataclass() -> None:
    rendered = RenderedError(prose="p", envelope={"k": "v"})
    assert rendered.prose == "p"
    assert rendered.envelope == {"k": "v"}


def test_set_and_get_round_trip_within_slot() -> None:
    exc = _Boom("x")
    token = open_render_state()
    try:
        set_rendered_error(exc, RenderedError(prose="P", envelope={"a": 1}))
        rendered = get_rendered_error(exc)
        assert rendered is not None
        assert rendered.prose == "P"
        assert rendered.envelope == {"a": 1}
    finally:
        close_render_state(token)


def test_get_returns_none_for_unknown_exc() -> None:
    exc_a = _Boom("a")
    exc_b = _Boom("b")
    token = open_render_state()
    try:
        set_rendered_error(exc_a, RenderedError(prose="P", envelope={}))
        assert get_rendered_error(exc_b) is None
    finally:
        close_render_state(token)


def test_close_clears_state() -> None:
    exc = _Boom("x")
    token = open_render_state()
    set_rendered_error(exc, RenderedError(prose="P", envelope={}))
    close_render_state(token)
    assert get_rendered_error(exc) is None


def test_set_without_open_is_noop() -> None:
    exc = _Boom("x")
    # No slot — set is a defensive no-op; get returns None.
    set_rendered_error(exc, RenderedError(prose="P", envelope={}))
    assert get_rendered_error(exc) is None
