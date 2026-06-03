"""Per-call scope — the neutral spine published on the request scope.

Every dispatcher (CLI runtime, MCP wrapper, in-process test client) wraps a
tool invocation in :func:`bind_call_scope`, which publishes a
:class:`_CallScope` on the shared request scope for the call's lifetime. The
emission level methods read ``ctx`` from it (the inline wire endpoint), and a
:class:`_CallScopeFilter` injects ``call_id`` / ``tool_name`` / ``elapsed_ms``
onto every record the ``a2kit`` logger handles.

``_CallScope`` is deliberately neutral (NOT ``_LogScope``): it is the shared
spine for BOTH the author app-log and the framework access-record. ``record``
accumulates the access-log row when the call-log is enabled; it is None
otherwise.
"""

from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

    from a2kit._context_protocol import ToolContext


@dataclass
class _CallScope:
    """Per-call identity for the lifetime of one tool dispatch."""

    ctx: Any = None
    call_id: str | None = None
    tool_name: str | None = None
    start_monotonic: float = field(default_factory=time.monotonic)
    #: Span fields (OTel data model, not the SDK). Set at dispatch for nesting.
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    #: The accumulating access-log record (None unless the call-log is on).
    record: Any = None


def _active_scope() -> _CallScope | None:
    """Return the active :class:`_CallScope`, or None outside a dispatch."""
    from a2kit.packages.context import request_scope  # noqa: A2K-LAYER

    return request_scope.try_get(_CallScope)


def _elapsed_ms(scope: _CallScope) -> int:
    return round((time.monotonic() - scope.start_monotonic) * 1000)


@contextlib.contextmanager
def bind_call_scope(
    *,
    ctx: ToolContext,
    call_id: str | None = None,
    tool_name: str | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
) -> Iterator[_CallScope]:
    """Publish per-call :class:`_CallScope` on ``request_scope`` for the block.

    Called by every dispatcher immediately before invoking the tool body. The
    ``ctx`` it receives becomes the ambient wire endpoint the level methods
    resolve against — neither callers nor tool bodies pass ``ctx`` explicitly.
    """
    from a2kit.packages.context import request_scope  # noqa: A2K-LAYER

    scope = _CallScope(
        ctx=ctx,
        call_id=call_id,
        tool_name=tool_name,
        start_monotonic=time.monotonic(),
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
    )
    token = request_scope.publish(scope)
    try:
        yield scope
    finally:
        request_scope.reset(token)


def _is_fastmcp_context(ctx: Any) -> bool:
    """Identity check: distinguish a real ``fastmcp.Context`` from a CLI stub.

    Cold-start preserving: only consults ``sys.modules``; if fastmcp has not
    been imported, the object cannot be a fastmcp Context.
    """
    import sys

    fastmcp_mod = sys.modules.get("fastmcp")
    if fastmcp_mod is None:
        return False
    fastmcp_context = getattr(fastmcp_mod, "Context", None)
    if fastmcp_context is None:
        return False
    return isinstance(ctx, fastmcp_context)


class _CallScopeFilter(logging.Filter):
    """Inject per-call context onto every record from the active scope.

    Attached to the ``a2kit`` logger at app boot. When no dispatch is active
    the fields are None — emission outside a tool call is still valid logging,
    it simply carries no correlation id.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        scope = _active_scope()
        record.call_id = scope.call_id if scope is not None else None
        record.tool_name = scope.tool_name if scope is not None else None
        record.elapsed_ms = _elapsed_ms(scope) if scope is not None else None
        return True
