"""Connection-aware middleware — `write_enforce_factory`.

The v0.12 tool decorator enforced `WriteNotAllowed` inline inside the
prelude. v0.13 lifts that into a middleware so:

  * the core decorator doesn't reach into ConnectionConfig to read
    `read_only`,
  * authors writing custom routers can add their own write gates by
    composing different middleware,
  * the connection-aware path lives entirely in `contrib.connections`.

The middleware reads the loaded ConnectionConfig from
`ctx.state["loaded_conn"]` (set by the connection-load step). When
`ctx.write` is True and the connection is read-only, it raises
`WriteNotAllowed` *before* `call_next` runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.exceptions import WriteNotAllowed
from a2kit.middleware._chain import STATE_CONNECTION_KEY, STATE_LOADED_CONN

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2kit.middleware._chain import Middleware, ToolContext


def write_enforce_factory() -> Middleware:
    """Return the WriteEnforce middleware.

    Tier-2 implicit: added when `@write` decorator is used AND a connection
    is loaded. Reads `ctx.state["loaded_conn"]` and `ctx.state["connection_key"]`.
    """

    async def _write_enforce(
        call_next: Callable[..., Awaitable[Any]],
        ctx: ToolContext,
        /,
        **kwargs: Any,
    ) -> Any:
        if ctx.write:
            info = ctx.state.get(STATE_LOADED_CONN)
            if info is not None and getattr(info, "read_only", False):
                conn_key = ctx.state.get(STATE_CONNECTION_KEY) or ()
                raise WriteNotAllowed(conn_key, tool_name=ctx.tool_name)
        return await call_next(**kwargs)

    return _write_enforce


__all__ = ["write_enforce_factory"]
