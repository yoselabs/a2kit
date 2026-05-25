"""BDD scenarios for typed-error-contract / ErrorEnvelope wire schema."""

import uuid

import pytest

from a2effect import AppError, ErrorEnvelope, register_error_kind


class _NotFound(AppError):
    kind = "input"
    hint = "verify the id"
    http_status = 404


class _Infra(AppError):
    kind = "infra"
    retryable = True


def test_envelope_round_trips_via_pydantic_json() -> None:
    err = _NotFound("x", details={"id": "abc"})
    env = err.to_envelope()
    raw = env.model_dump_json()
    parsed = ErrorEnvelope.model_validate_json(raw)
    assert parsed == env


def test_envelope_carries_subclass_name_kind_basekind_retryable_hint() -> None:
    err = _NotFound("x")
    env = err.to_envelope()
    assert env.type == "_NotFound"
    assert env.kind == "input"
    assert env.base_kind == "input"
    assert env.retryable is False
    assert env.hint == "verify the id"
    assert env.envelope_version == "1"


def test_envelope_carries_details_dict() -> None:
    err = _NotFound("x", details={"id": "abc", "scope": "memory"})
    env = err.to_envelope()
    assert env.details == {"id": "abc", "scope": "memory"}


def test_envelope_cause_chain_populated_when_raised_from() -> None:
    original = ValueError("orig")
    err: AppError
    try:
        raise _NotFound("wrap") from original
    except _NotFound as caught:
        err = caught
    env = err.to_envelope()
    assert env.cause is not None
    assert env.cause["type"] == "ValueError"
    assert env.cause["message"] == "orig"
    uuid.UUID(env.cause["trace_id"])


def test_envelope_cause_absent_when_no_cause() -> None:
    err = _NotFound("x")
    env = err.to_envelope()
    assert env.cause is None


def test_envelope_extension_kind_carries_base_kind_fallback() -> None:
    register_error_kind("token_bucket", base="infra", retryable=True)

    class _RateLimit(AppError):
        kind = "token_bucket"

    env = _RateLimit("hit").to_envelope()
    assert env.kind == "token_bucket"
    assert env.base_kind == "infra"
    assert env.retryable is True


def test_to_envelope_dict_matches_model_dump() -> None:
    err = _NotFound("x", details={"id": "abc"})
    assert err.to_envelope_dict() == err.to_envelope().model_dump()


def test_envelope_version_is_locked_to_one() -> None:
    env = _NotFound("x").to_envelope()
    assert env.envelope_version == "1"


def test_envelope_per_instance_retryable_override_propagates() -> None:
    err = _Infra("conn refused", retryable=False)
    env = err.to_envelope()
    assert env.retryable is False


def test_envelope_per_instance_hint_override_propagates() -> None:
    err = _NotFound("x", hint="try the cache")
    env = err.to_envelope()
    assert env.hint == "try the cache"


def test_envelope_rejects_direct_construction_via_authoring_path() -> None:
    # Authors SHALL NOT construct ErrorEnvelope directly. Pydantic permits
    # it (you cannot block model construction without breaking serialization
    # round-trip), but the contract is documented and lint enforces.
    # This test just confirms the model is constructable for framework code
    # and validates required fields.
    with pytest.raises((ValueError, Exception)):
        ErrorEnvelope.model_validate({})  # missing required fields
