"""Per-call LDD state — published on the shared request scope by every dispatcher.

Every dispatcher (CLI runtime, MCP wrapper, in-process test client) wraps a
tool invocation in :func:`ldd_state_for_call`, which publishes a
:class:`_LddState` instance on
:mod:`a2kit.packages.dispatch.request_scope` (the shared request-scope
bridge — Principal, per-request Container, and LDD state all flow
through it). The LDD primitives read it from there; calling one outside
an active dispatch raises :exc:`a2kit.exceptions.AmbientContextMissing`
(a deprecation-shim subclass of
:class:`a2kit.packages.dispatch.request_scope.RequestScopeMissing`),
fail loud, never silently no-op.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from a2kit.exceptions import AmbientContextMissing

if TYPE_CHECKING:
    from collections.abc import Iterator

    from a2kit._context_protocol import ToolContext
    from a2kit.packages.ldd.sinks import LddSink


@dataclass
class _LddState:
    ctx: Any = None
    events_enabled: bool = True
    reports_enabled: bool = True
    report_type: type | None = None
    tool_name: str | None = None
    start_monotonic: float = field(default_factory=time.monotonic)
    sinks: tuple[LddSink, ...] = ()
    #: Numeric rank threshold; emissions with rank < threshold are dropped at
    #: the primitive. Default ``0`` is a sentinel meaning "no filtering" so
    #: bare ``ldd_state_for_call(ctx=...)`` callers (tests, ad-hoc harnesses)
    #: observe every emission. The dispatch site stamps the real value from
    #: ``app.config.ldd.level`` per call.
    level_threshold: int = 0


def _require_ambient_state(fn_name: str) -> _LddState:
    """Return the active LDD state or raise :exc:`AmbientContextMissing`.

    LDD primitives only work inside a tool dispatch. Tests that exercise
    primitives directly must wrap with ``ldd_state_for_call(ctx=stub, ...)``.

    v0.33: distinguishes two failure modes — see :class:`AmbientContextMissing`.
    Post ``generalise-context-bridges``: the underlying lookup uses
    ``request_scope.try_get(_LddState)``. When absent, the raised
    ``AmbientContextMissing`` chains from ``RequestScopeMissing(_LddState)``
    via ``__cause__``. Local import keeps ldd off the dispatch package's
    import-time graph (avoids dispatch -> stages -> ldd cycle).
    """
    from a2kit.packages.context import request_scope

    state = request_scope.try_get(_LddState)
    if state is None:
        try:
            request_scope.get(_LddState)
        except request_scope.RequestScopeMissing as exc:
            raise AmbientContextMissing(fn_name, mode=AmbientContextMissing.MODE_NO_DISPATCH) from exc
        raise AmbientContextMissing(fn_name, mode=AmbientContextMissing.MODE_NO_DISPATCH)
    if state.ctx is None:
        raise AmbientContextMissing(fn_name, mode=AmbientContextMissing.MODE_MISSING_CTX_PARAM)
    return state


def _elapsed_ms_from(state: _LddState) -> int:
    return round((time.monotonic() - state.start_monotonic) * 1000)


@contextlib.contextmanager
def ldd_state_for_call(
    *,
    ctx: ToolContext,
    events_enabled: bool = True,
    reports_enabled: bool = True,
    report_type: type | None = None,
    tool_name: str | None = None,
    sinks: tuple[LddSink, ...] = (),
    level_threshold: int = 0,
) -> Iterator[None]:
    """Publish per-call LDD state on ``request_scope`` for the wrapped block.

    Called by every dispatcher (CLI runtime, MCP wrapper, in-process test
    client) immediately before invoking the tool body. The ``ctx`` it
    receives becomes the ambient context that LDD primitives
    (:func:`event`, :func:`report`, :func:`log`, and shorthands) resolve
    against — neither callers nor tool bodies pass ``ctx`` explicitly.

    ``sinks`` is the tuple of in-process observers registered on the App
    via ``app.ldd.add_sink(...)``; the primitives fan out to each after
    the wire emit.
    """
    from a2kit.packages.context import request_scope  # noqa: A2K-LAYER

    state = _LddState(
        ctx=ctx,
        events_enabled=events_enabled,
        reports_enabled=reports_enabled,
        report_type=report_type,
        tool_name=tool_name,
        start_monotonic=time.monotonic(),
        sinks=sinks,
        level_threshold=level_threshold,
    )
    token = request_scope.publish(state)
    try:
        yield
    finally:
        request_scope.reset(token)


def _is_fastmcp_context(ctx: Any) -> bool:
    """Identity check: distinguish real ``fastmcp.Context`` from CLI stub.

    Both expose ``log``, so duck typing isn't sufficient — the CLI stub
    needs the bespoke ``_emit`` wire format, while real ``fastmcp.Context``
    rides ``ctx.log(extra=...)`` notifications. Cold-start preserving:
    only consults ``sys.modules``; if fastmcp hasn't been imported, the
    object can't be a fastmcp Context.
    """
    import sys as _sys

    fastmcp_mod = _sys.modules.get("fastmcp")
    if fastmcp_mod is None:
        return False
    fastmcp_context = getattr(fastmcp_mod, "Context", None)
    if fastmcp_context is None:
        return False
    return isinstance(ctx, fastmcp_context)
