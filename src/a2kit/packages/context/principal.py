"""`Principal`: substrate-neutral identity record carried into `call_scope`.

Owned by the framework so auth wrappers (defined separately in `add-auth`)
stay producers rather than redefining the type. Populated by whichever
substrate authenticated the request; consumed via type annotation by tool
bodies and `authorize=` callables.

The per-request ambient that carries Principal from substrate auth
boundary to the dispatch call_scope opening lives in
``a2kit.packages.dispatch._principal_bridge`` — a private dispatch-layer
module. This file holds only the type.
"""

from __future__ import annotations

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
