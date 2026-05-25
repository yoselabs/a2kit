"""BDD scenarios for typed-error-contract / UnexpectedDefect quarantine."""

import asyncio

import pytest

from a2effect import AppError, UnexpectedDefect
from a2effect.defect import quarantine


def test_unexpected_defect_is_app_error_subclass_with_bug_kind() -> None:
    assert issubclass(UnexpectedDefect, AppError)
    assert UnexpectedDefect.kind == "bug"
    assert UnexpectedDefect.retryable is False


def test_unexpected_defect_envelope_does_not_leak_original_type_at_top_level() -> None:
    original = KeyError("foo")
    defect = quarantine(original)
    env = defect.to_envelope()
    assert env.type == "UnexpectedDefect"
    assert env.kind == "bug"
    assert env.retryable is False
    # Original type appears only inside cause.type, never as envelope.type
    assert "KeyError" in env.cause["type"]
    assert env.cause["message"] == "'foo'" or "foo" in env.cause["message"]


def test_quarantine_preserves_original_on_cause() -> None:
    original = KeyError("missing")
    defect = quarantine(original)
    assert defect.__cause__ is original


def test_quarantine_wraps_cancelled_error_as_defect() -> None:
    cancelled = asyncio.CancelledError()
    defect = quarantine(cancelled)
    env = defect.to_envelope()
    assert env.type == "UnexpectedDefect"
    assert env.kind == "bug"
    assert "CancelledError" in env.cause["type"]


def test_quarantine_wraps_keyboard_interrupt() -> None:
    defect = quarantine(KeyboardInterrupt())
    env = defect.to_envelope()
    assert env.type == "UnexpectedDefect"
    assert "KeyboardInterrupt" in env.cause["type"]


def test_unexpected_defect_cannot_be_subclassed() -> None:
    with pytest.raises(TypeError, match="final"):

        class _Subclass(UnexpectedDefect):  # type: ignore[misc]
            pass


def test_quarantine_idempotent_on_app_error() -> None:
    class _NotFound(AppError):
        kind = "input"

    original = _NotFound("x")
    result = quarantine(original)
    assert result is original
