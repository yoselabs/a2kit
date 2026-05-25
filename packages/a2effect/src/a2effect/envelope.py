from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

ENVELOPE_VERSION: Literal["1"] = "1"


class ErrorEnvelope(BaseModel):
    type: str
    kind: str
    base_kind: str
    retryable: bool
    hint: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    cause: dict[str, str] | None = None
    envelope_version: Literal["1"] = ENVELOPE_VERSION


def _extract_cause(exc: BaseException) -> dict[str, str] | None:
    original = exc.__cause__
    if original is None:
        return None
    type_name = type(original).__name__
    module = type(original).__module__
    qualified = f"{module}.{type_name}" if module not in ("builtins", "__main__") else type_name
    return {
        "type": qualified,
        "message": str(original),
        "trace_id": str(uuid.uuid4()),
    }
