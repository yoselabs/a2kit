from __future__ import annotations

from typing import Any

from a2effect.errors import AppError


class UnexpectedDefect(AppError):
    kind = "bug"
    retryable = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError(
            f"UnexpectedDefect is final and SHALL NOT be subclassed; got {cls.__name__!r}. "
            f"To carry a typed defect, subclass AppError directly with kind='bug'."
        )


def quarantine(exc: BaseException) -> AppError:
    if isinstance(exc, AppError):
        return exc
    wrapped = UnexpectedDefect(str(exc) or type(exc).__name__)
    wrapped.__cause__ = exc
    return wrapped
