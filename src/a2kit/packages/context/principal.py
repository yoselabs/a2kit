"""`Principal`: substrate-neutral identity record carried into `call_scope`.

Owned by the framework so auth wrappers (defined separately in `add-auth`)
stay producers rather than redefining the type. Populated by whichever
substrate authenticated the request; consumed via type annotation by tool
bodies and `authorize=` callables.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    scopes: frozenset[str]
    claims: Mapping[str, Any] = field(default_factory=dict)
    issued_by: str = ""
    raw_token: str | None = None


# Set by substrate-side authentication (FastAPI Security guard return value or
# MCP middleware) before `Container.call_scope` opens, then consumed by the
# scope-open hook to seed a SCOPED `Principal` provider into the per-call
# child container. Single contextvar, single read site — substrates differ
# only in WHO writes it.
_a2kit_request_principal: contextvars.ContextVar[Principal | None] = contextvars.ContextVar("_a2kit_request_principal", default=None)
