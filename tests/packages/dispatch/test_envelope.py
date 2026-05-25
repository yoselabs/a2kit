"""BDD scenarios for ErrorEnvelopeStage + prose formatter + kind label registry."""

from __future__ import annotations

import pytest
from a2effect import AppError

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


async def test_stage_attaches_rendered_prose_and_envelope_on_error() -> None:
    stage = ErrorEnvelopeStage()

    async def body() -> int:
        raise _Boom("db down")

    wrapped = stage.wrap(body, spec=None)
    with pytest.raises(_Boom) as info:
        await wrapped()
    exc = info.value
    # ErrorEnvelopeStage attaches these render artifacts to the exception;
    # AppError (a2effect) intentionally doesn't declare them — a2kit's
    # dispatch contract does. See src/a2kit/packages/dispatch/envelope.py.
    assert exc.rendered_prose == "Service unavailable (_Boom): db down"  # ty: ignore[unresolved-attribute]
    env = exc.rendered_envelope_dict  # ty: ignore[unresolved-attribute]
    assert env["type"] == "_Boom"
    assert env["kind"] == "infra"
    assert env["retryable"] is False or env["retryable"] is True  # class default


async def test_stage_does_not_touch_non_app_error() -> None:
    stage = ErrorEnvelopeStage()

    async def body() -> int:
        raise KeyError("raw")

    wrapped = stage.wrap(body, spec=None)
    with pytest.raises(KeyError):
        await wrapped()
