"""Implicit middleware chain for `@a2kit.tool` (v0.13).

Per todo.md "Headline architectural pattern: implicit middleware chain":
the kit assembles a Starlette-style chain at decoration time from the verb,
the Router's config, and the resolved connection. Authors don't write
middleware boilerplate in the 99% case.

Public surface:

- `ToolContext`     — frozen dataclass threaded through every middleware
- `Middleware`      — Protocol: `async (call_next, ctx, /, **kw) -> Any`
- `_build_chain`    — assemble the Tier-1/2/3 chain for a tool
- `compose`         — right-to-left composition into a single callable
- middleware functions in submodules: `_otel`, `_guards`, `_listview`,
  `_enricher`

The middleware chain replaces the v0.12 `_prelude_async` monolith. Each
middleware is unit-testable without a live router.
"""

from __future__ import annotations

from a2kit.middleware._chain import (
    Middleware,
    ToolContext,
    _build_chain,
    compose,
)
from a2kit.middleware._enricher import enrich_errors_factory
from a2kit.middleware._guards import capability_guard, tool_call_guard
from a2kit.middleware._listview import list_view_apply_factory
from a2kit.middleware._otel import otel_span_factory

__all__ = [
    "Middleware",
    "ToolContext",
    "_build_chain",
    "capability_guard",
    "compose",
    "enrich_errors_factory",
    "list_view_apply_factory",
    "otel_span_factory",
    "tool_call_guard",
]
