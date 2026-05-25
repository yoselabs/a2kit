from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from a2effect.errors import AppError

T = TypeVar("T")
_Mapping = dict[type[BaseException], type[AppError] | Callable[[BaseException], AppError]]


async def raises_as(awaitable: Awaitable[T], mapping: _Mapping) -> T:
    try:
        return await awaitable
    except BaseException as exc:
        for source, target in mapping.items():
            if isinstance(exc, source):
                if isinstance(target, type) and issubclass(target, AppError):
                    new = target(str(exc) or type(exc).__name__)
                    new.__cause__ = exc
                    raise new from exc
                translated = target(exc)
                if not isinstance(translated, AppError):
                    raise TypeError(
                        f"raises_as callable for {source.__name__} must return AppError, got {type(translated).__name__}"
                    ) from exc
                if translated.__cause__ is None:
                    translated.__cause__ = exc
                raise translated from exc
        raise


@asynccontextmanager
async def translate_to(target: type[AppError], *sources: type[BaseException]) -> Any:
    try:
        yield
    except BaseException as exc:
        if sources and isinstance(exc, sources):
            new = target(str(exc) or type(exc).__name__)
            new.__cause__ = exc
            raise new from exc
        raise
