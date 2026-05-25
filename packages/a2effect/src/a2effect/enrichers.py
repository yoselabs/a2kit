from __future__ import annotations

from pydantic import ValidationError

from a2effect.errors import AppError, InputError


def pydantic_validation_error_enricher(exc: BaseException) -> AppError | None:
    if isinstance(exc, AppError):
        return None
    if not isinstance(exc, ValidationError):
        return None
    fields = [{"loc": list(err["loc"]), "type": err["type"], "msg": err["msg"]} for err in exc.errors()]
    translated = InputError("validation failed", details={"fields": fields})
    translated.__cause__ = exc
    return translated
