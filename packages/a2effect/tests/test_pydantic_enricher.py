"""Default a2effect enricher: translates pydantic ValidationError to InputError."""

from pydantic import BaseModel, Field, ValidationError

from a2effect.enrichers import pydantic_validation_error_enricher
from a2effect.errors import InputError


class _UserPayload(BaseModel):
    id: str = Field(min_length=1)
    age: int = Field(ge=0)


def test_enricher_returns_none_for_unrelated_exception() -> None:
    assert pydantic_validation_error_enricher(KeyError("x")) is None


def test_enricher_returns_none_for_app_error_subclasses() -> None:
    assert pydantic_validation_error_enricher(InputError("x")) is None


def test_enricher_translates_validation_error_to_input_error() -> None:
    try:
        _UserPayload(id="", age=-3)
    except ValidationError as e:
        translated = pydantic_validation_error_enricher(e)
    assert isinstance(translated, InputError)


def test_translated_error_carries_field_path_details() -> None:
    try:
        _UserPayload(id="", age=-3)
    except ValidationError as e:
        translated = pydantic_validation_error_enricher(e)
    assert "fields" in translated.details
    fields = translated.details["fields"]
    assert isinstance(fields, list)
    assert len(fields) == 2
    paths = {tuple(f["loc"]) for f in fields}
    assert ("id",) in paths
    assert ("age",) in paths


def test_translated_error_kind_is_input() -> None:
    try:
        _UserPayload(id="", age=-3)
    except ValidationError as e:
        translated = pydantic_validation_error_enricher(e)
    assert translated.kind == "input"


def test_input_error_is_app_error_subclass_with_kind_input() -> None:
    assert InputError.kind == "input"
    err = InputError("bad")
    assert err.base_kind == "input"


def test_translated_error_envelope_round_trips() -> None:
    try:
        _UserPayload(id="", age=-3)
    except ValidationError as e:
        translated = pydantic_validation_error_enricher(e)
    env = translated.to_envelope()
    assert env.type == "InputError"
    assert env.kind == "input"
    assert "fields" in env.details
