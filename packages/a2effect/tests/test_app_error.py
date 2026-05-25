"""BDD scenarios for typed-error-contract / AppError sealed hierarchy."""

import pytest

from a2effect import AppError, register_error_kind


def test_subclass_with_core_kind_is_created() -> None:
    class NotFound(AppError):
        kind = "input"

    err = NotFound("x")
    assert err.kind == "input"
    assert err.base_kind == "input"
    assert err.retryable is False
    assert err.hint is None
    assert err.http_status is None
    assert err.cli_exit_code is None


def test_subclass_without_kind_raises_type_error() -> None:
    with pytest.raises(TypeError, match="kind"):

        class Bad(AppError):
            pass


def test_per_instance_override_of_retryable() -> None:
    class InfrastructureError(AppError):
        kind = "infra"
        retryable = True

    err = InfrastructureError("conn refused", retryable=False)
    assert err.retryable is False
    assert InfrastructureError.retryable is True


def test_per_instance_override_of_hint_and_details() -> None:
    class NotFound(AppError):
        kind = "input"
        hint = "default hint"

    err = NotFound("x", hint="custom hint", details={"id": "abc"})
    assert err.hint == "custom hint"
    assert err.details == {"id": "abc"}


def test_kind_is_not_per_instance_overridable() -> None:
    class NotFound(AppError):
        kind = "input"

    err = NotFound("x")
    with pytest.raises(TypeError, match="kind"):
        NotFound("x", kind="infra")  # type: ignore[call-arg]
    assert err.kind == "input"


def test_unregistered_extended_kind_raises_at_class_creation() -> None:
    with pytest.raises(TypeError, match="weird"):

        class Weird(AppError):
            kind = "weird"


def test_extended_kind_registers_and_resolves_base_kind() -> None:
    register_error_kind("rate_limit", base="infra", retryable=True)

    class RateLimit(AppError):
        kind = "rate_limit"

    err = RateLimit("hit")
    assert err.kind == "rate_limit"
    assert err.base_kind == "infra"
    assert err.retryable is True


def test_class_level_metadata_defaults() -> None:
    class AuthFailed(AppError):
        kind = "auth"

    assert AuthFailed.retryable is False
    assert AuthFailed.hint is None
    assert AuthFailed.http_status is None
    assert AuthFailed.cli_exit_code is None


def test_class_level_http_status_override() -> None:
    class NotFound(AppError):
        kind = "input"
        http_status = 404

    assert NotFound("x").http_status == 404


def test_app_error_base_itself_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError, match="kind"):
        AppError("x")
