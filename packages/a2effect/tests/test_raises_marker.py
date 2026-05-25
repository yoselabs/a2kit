"""BDD scenarios for raises-annotation-contract / Raises marker."""

from dataclasses import dataclass
from typing import Annotated

import pytest

from a2effect import AppError, Raises


class _NotFound(AppError):
    kind = "input"


class _InvalidId(AppError):
    kind = "input"


def test_raises_is_frozen_dataclass_with_types_tuple() -> None:
    marker = Raises(_NotFound, _InvalidId)
    assert marker.types == (_NotFound, _InvalidId)
    with pytest.raises((AttributeError, Exception)):
        marker.types = ()  # type: ignore[misc]


def test_flatten_from_callable_with_single_marker() -> None:
    async def fetch() -> Annotated[str, Raises(_NotFound, _InvalidId)]:
        return "ok"

    assert Raises.flatten_from_annotation(fetch) == (_NotFound, _InvalidId)


def test_flatten_from_callable_with_multiple_markers_dedupes_and_unions() -> None:
    async def fetch() -> Annotated[str, Raises(_NotFound), Raises(_InvalidId)]:
        return "ok"

    result = Raises.flatten_from_annotation(fetch)
    assert set(result) == {_NotFound, _InvalidId}


def test_flatten_order_irrelevant_with_other_metadata() -> None:
    @dataclass(frozen=True)
    class _OtherMeta:
        tag: str

    async def a() -> Annotated[str, Raises(_NotFound), _OtherMeta("x")]:
        return "ok"

    async def b() -> Annotated[str, _OtherMeta("x"), Raises(_NotFound)]:
        return "ok"

    assert Raises.flatten_from_annotation(a) == Raises.flatten_from_annotation(b)


def test_flatten_returns_empty_when_no_raises_marker() -> None:
    async def now() -> str:
        return "ok"

    assert Raises.flatten_from_annotation(now) == ()


def test_flatten_returns_empty_when_annotated_without_raises() -> None:
    async def now() -> Annotated[str, "doc"]:
        return "ok"

    assert Raises.flatten_from_annotation(now) == ()


def test_raises_rejects_non_app_error_member_at_flatten() -> None:
    class _NotAppError(Exception):
        pass

    async def bad() -> Annotated[str, Raises(_NotAppError)]:  # type: ignore[arg-type]
        return "ok"

    with pytest.raises(TypeError, match="_NotAppError"):
        Raises.flatten_from_annotation(bad)


def test_raises_marker_construction_allows_any_type_lint_catches_later() -> None:
    # Construction itself permits non-AppError; flatten-time validation
    # is the contract (so lint can report at call-site without import-time crash).
    class _Other(Exception):
        pass

    Raises(_Other)  # type: ignore[arg-type] — no exception at construction
