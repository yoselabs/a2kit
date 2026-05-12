"""Mirror tests for ``a2kit._field_introspect``.

The introspection helper reads ``pydantic.Field`` metadata off
``Annotated[T, Field(...)]`` annotations and returns the description
string (or ``None`` when absent).
"""

from __future__ import annotations

from typing import Annotated

import pydantic

from a2kit._field_introspect import description_of


def test_description_of_picks_up_pydantic_field() -> None:
    annotation = Annotated[str, pydantic.Field(description="hello")]
    assert description_of(annotation) == "hello"


def test_description_of_returns_none_for_plain_type() -> None:
    assert description_of(str) is None


def test_description_of_returns_none_for_annotated_without_field() -> None:
    annotation = Annotated[str, "just-a-string-tag"]
    assert description_of(annotation) is None


def test_description_of_handles_field_with_no_description() -> None:
    annotation = Annotated[int, pydantic.Field(ge=0)]
    assert description_of(annotation) is None
