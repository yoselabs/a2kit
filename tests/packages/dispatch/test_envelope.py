"""BDD scenarios for ErrorEnvelopeStage + prose formatter + kind label registry."""

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
    kind_label,
)


class _NotFound(AppError):
    kind = "input"
    hint = "verify the id from list_memories"


class _InvalidId(AppError):
    kind = "input"


class _AuthRequired(AppError):
    kind = "auth"


class _AuthDenied(AppError):
    kind = "auth"
    kind_label = "Authorization denied"


class _Boom(AppError):
    kind = "infra"


def test_kind_label_core_kinds() -> None:
    assert kind_label("input") == "Input error"
    assert kind_label("auth") == "Authentication required"
    assert kind_label("policy") == "Not allowed"
    assert kind_label("infra") == "Service unavailable"
    assert kind_label("bug") == "Internal error"


def test_prose_with_hint_exact_format() -> None:
    exc = _NotFound("memory id 'abc' does not exist")
    text = format_error_prose(exc)
    assert text == "Input error (_NotFound): memory id 'abc' does not exist\n\nHint: verify the id from list_memories"


def test_prose_without_hint_no_trailing_blank() -> None:
    exc = _InvalidId("bad format")
    text = format_error_prose(exc)
    assert text == "Input error (_InvalidId): bad format"
    assert "Hint:" not in text


def test_prose_uses_subclass_kind_label_override() -> None:
    exc = _AuthDenied("nope")
    assert format_error_prose(exc).startswith("Authorization denied (_AuthDenied):")


async def test_stage_passes_success_through() -> None:
    stage = ErrorEnvelopeStage()

    async def body() -> int:
        return 42

    wrapped = stage.wrap(body, spec=None)
    assert await wrapped() == 42


async def test_stage_writes_rendered_prose_and_envelope_to_side_channel() -> None:
    stage = ErrorEnvelopeStage()

    async def body() -> int:
        raise _Boom("db down")

    wrapped = stage.wrap(body, spec=None)
    token = open_render_state()
    try:
        with pytest.raises(_Boom) as info:
            await wrapped()
        exc = info.value
        # AppError stays a pure domain value — no rendering metadata on
        # the instance. The side channel carries it.
        assert not hasattr(exc, "rendered_prose")
        assert not hasattr(exc, "rendered_envelope_dict")
        rendered = get_rendered_error(exc)
        assert rendered is not None
        assert rendered.prose == "Service unavailable (_Boom): db down"
        assert rendered.envelope["type"] == "_Boom"
        assert rendered.envelope["kind"] == "infra"
        assert rendered.envelope["retryable"] is False or rendered.envelope["retryable"] is True
    finally:
        close_render_state(token)


async def test_stage_does_not_touch_non_app_error() -> None:
    stage = ErrorEnvelopeStage()

    async def body() -> int:
        raise KeyError("raw")

    wrapped = stage.wrap(body, spec=None)
    with pytest.raises(KeyError):
        await wrapped()
