"""BDD scenarios for error-translation-pipeline / inline helpers."""

import pytest

from a2effect import AppError, raises_as, translate_to


class _NotFound(AppError):
    kind = "input"


class _InvalidId(AppError):
    kind = "input"


class _Infra(AppError):
    kind = "infra"
    retryable = True


async def _raises_value_error(msg: str = "bad") -> None:
    raise ValueError(msg)


async def _raises_key_error() -> None:
    raise KeyError("missing")


async def _returns_value(v: int) -> int:
    return v * 2


async def test_raises_as_translates_mapped_type_to_app_error() -> None:
    with pytest.raises(_NotFound) as exc_info:
        await raises_as(_raises_value_error(), {ValueError: _NotFound})
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, ValueError)


async def test_raises_as_with_callable_value_receives_original_exception() -> None:
    def _build(e: Exception) -> _InvalidId:
        return _InvalidId(str(e), details={"raw": e.args})

    with pytest.raises(_InvalidId) as exc_info:
        await raises_as(_raises_value_error("oops"), {ValueError: _build})
    assert exc_info.value.details == {"raw": ("oops",)}


async def test_raises_as_unmatched_exception_propagates_unchanged() -> None:
    with pytest.raises(KeyError):
        await raises_as(_raises_key_error(), {ValueError: _NotFound})


async def test_raises_as_passes_through_success_value() -> None:
    result = await raises_as(_returns_value(3), {ValueError: _NotFound})
    assert result == 6


async def test_translate_to_wraps_block_into_target() -> None:
    with pytest.raises(_Infra) as exc_info:
        async with translate_to(_Infra, ValueError):
            await _raises_value_error("conn refused")
    assert isinstance(exc_info.value.__cause__, ValueError)


async def test_translate_to_passes_through_unrelated_exception() -> None:
    with pytest.raises(KeyError):
        async with translate_to(_Infra, ValueError):
            await _raises_key_error()


async def test_translate_to_handles_multiple_source_types() -> None:
    with pytest.raises(_Infra):
        async with translate_to(_Infra, ValueError, KeyError):
            await _raises_key_error()


async def test_translate_to_no_op_when_no_exception() -> None:
    async with translate_to(_Infra, ValueError):
        result = await _returns_value(7)
    assert result == 14
