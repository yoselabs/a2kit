"""Round-4 Soft A: `a2kit.Param` positional-string shorthand.

Gherkin scenarios (mirroring `specs/tool-description-contract/spec.md`
MODIFIED requirement "Per-parameter descriptions via a2kit.Param"):

  Scenario: Param positional shorthand
    GIVEN a kwarg annotated Annotated[str, a2kit.Param("Absolute URL.")]
    THEN the description is "Absolute URL." (equivalent to description=)

  Scenario: Param keyword form still works
    GIVEN Annotated[str, a2kit.Param(description="Absolute URL.")]
    THEN the description is "Absolute URL."

  Scenario: Positional + description kwarg raises
    WHEN Param("first", description="second") is constructed
    THEN TypeError is raised at construction
"""

from __future__ import annotations

from typing import Annotated

import pytest

import a2kit
from a2kit.params import description_of


def test_param_positional_shorthand() -> None:
    field = a2kit.Param("Absolute URL.")
    assert field.description == "Absolute URL."


def test_param_keyword_form_still_works() -> None:
    field = a2kit.Param(description="Absolute URL.")
    assert field.description == "Absolute URL."


def test_param_positional_and_kwarg_conflict_raises() -> None:
    with pytest.raises(TypeError, match="description"):
        a2kit.Param("first", description="second")


def test_param_positional_with_extra_kwargs() -> None:
    """Positional description coexists with extras (examples, ge, le, etc.)."""
    field = a2kit.Param("URL.", examples=["https://x"])
    assert field.description == "URL."
    assert field.examples == ["https://x"]


def test_description_of_picks_up_positional_form() -> None:
    annotation = Annotated[str, a2kit.Param("hello")]
    assert description_of(annotation) == "hello"


def test_description_of_picks_up_kwarg_form() -> None:
    annotation = Annotated[str, a2kit.Param(description="hello")]
    assert description_of(annotation) == "hello"
