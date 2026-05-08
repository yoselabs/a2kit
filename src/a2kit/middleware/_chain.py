"""Middleware chain primitives — `ToolContext`, `Middleware`, `_build_chain`,
`compose`.

The chain shape mirrors Starlette/FastAPI:

    async def mw(call_next, ctx, /, **kwargs) -> Any:
        # before
        result = await call_next(**kwargs)
        # after
        return result

`ctx: ToolContext` carries tool metadata. `kwargs` carries the runtime
arguments forwarded to the inner tool function.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2kit._capabilities import Capability
    from a2kit.formatter import FormatName


Verb = Literal["read", "write", "list", "tool"]


@dataclass(frozen=True)
class ToolContext:
    """Per-call middleware context (frozen).

    Threaded right-to-left through the chain; each middleware receives the
    same instance. Per-call mutable state (`loaded_conn`, `connection_key`,
    `dep_cache`, `lv_state`) lives in `state` — a plain dict carved out for
    middleware coordination (e.g. OTel reads `connection_key` set by
    connection-aware middleware).
    """

    tool_name: str
    verb: Verb
    write: bool
    capabilities: frozenset[Capability]
    format_hint: FormatName | None = None
    state: dict[str, Any] = field(default_factory=dict)


class Middleware(Protocol):
    """Async middleware shape."""

    async def __call__(
        self,
        call_next: Callable[..., Awaitable[Any]],
        ctx: ToolContext,
        /,
        **kwargs: Any,
    ) -> Any: ...


def compose(
    chain: list[Middleware],
    inner: Callable[..., Awaitable[Any]],
    ctx: ToolContext,
) -> Callable[..., Awaitable[Any]]:
    """Right-to-left composition of `chain` around `inner`.

    `chain[0]` is the outermost middleware (runs first / last). `inner` is
    the actual tool body. Returns a callable taking `**kwargs` and returning
    the result.
    """

    def _wrap(mw: Middleware, nxt: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        async def _call(**kwargs: Any) -> Any:
            return await mw(nxt, ctx, **kwargs)

        return _call

    handler: Callable[..., Awaitable[Any]] = inner
    for mw in reversed(chain):
        handler = _wrap(mw, handler)
    return handler


def _build_chain(
    *,
    verb: Verb,
    write: bool,
    has_listview: bool,
    enricher: Any,
    router_middleware: list[Middleware] | None,
    app_middleware: list[Middleware] | None,
    otel: bool,
    tool_call_guard_on: bool,
    bare: bool,
    extra_pre: list[Middleware] | None = None,
    extra_post: list[Middleware] | None = None,
) -> list[Middleware]:
    """Assemble the implicit middleware chain.

    Order (outermost → innermost):
        1. enrich_errors (so it sees everything that follows raise)
        2. otel_span (records timing/attrs around the call)
        3. tool_call_guard (rejects accidental tool-call contamination)
        4. capability_guard (placeholder; today caps are enforced at select)
        5. extra_pre  (e.g. write_enforce from contrib.connections)
        6. list_view_apply (transforms result for @list)
        7. router.middleware
        8. app.middleware
        9. extra_post (rare)

    `bare=True` returns an empty chain — author opted out of all implicit
    middleware.
    """
    from a2kit.middleware._guards import capability_guard, tool_call_guard  # noqa: PLC0415
    from a2kit.middleware._listview import list_view_apply_factory  # noqa: PLC0415
    from a2kit.middleware._otel import otel_span_factory  # noqa: PLC0415

    if bare:
        return []

    chain: list[Middleware] = []
    # Note: in v0.13 phase 2 the enricher is *also* applied at the wrapper
    # boundary so prelude exceptions (connection-load failures) get enriched
    # too. Phase 3 folds prelude into the chain and the wrapper boundary
    # collapses; until then we accept a single enrichment site (the wrapper)
    # and skip adding the middleware here. The factory is still exported for
    # explicit chains and unit tests.
    _ = enricher  # consumed by the wrapper, kept here for forward compat
    if otel:
        chain.append(otel_span_factory())
    if tool_call_guard_on:
        chain.append(tool_call_guard)
    chain.append(capability_guard)
    if extra_pre:
        chain.extend(extra_pre)
    if has_listview and verb == "list":
        chain.append(list_view_apply_factory())
    elif has_listview:
        # @read/@tool with explicit filter/fields/pagination still get listview
        chain.append(list_view_apply_factory())
    if router_middleware:
        chain.extend(router_middleware)
    if app_middleware:
        chain.extend(app_middleware)
    if extra_post:
        chain.extend(extra_post)
    return chain


__all__ = [
    "Middleware",
    "ToolContext",
    "Verb",
    "_build_chain",
    "compose",
]
