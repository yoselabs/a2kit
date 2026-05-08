"""List-view middleware — applies filter/fields/pagination to the result.

Decoration-time settings live in `ctx.state["lv_settings"]`. The wrapper
extracts list-view kwargs *before* the chain runs (so tool_call_guard never
sees them) and stashes the per-call state in `ctx.state["lv_state"]`. The
streaming-drain pass (for `streaming=True` tools) lives here too — it sits
just outside the inner call so it sees the raw `AsyncIterator`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from a2kit.tools._runtime import _consume_or_passthrough_async
from a2kit.tools._signature import _listview_apply

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2kit.middleware._chain import Middleware, ToolContext


def list_view_apply_factory() -> Middleware:
    """Return a list-view middleware (post-result transform + stream drain)."""

    async def _lv_mw(
        call_next: Callable[..., Awaitable[Any]],
        ctx: ToolContext,
        /,
        **kwargs: Any,
    ) -> Any:
        settings: dict[str, Any] = ctx.state.get("lv_settings", {})
        filter_mode = settings.get("filter")
        fields_mode = settings.get("fields")
        pagination_mode = settings.get("pagination")
        format_hint = settings.get("format")
        lv_state: dict[str, Any] = ctx.state.get("lv_state", {})
        streaming: bool = bool(ctx.state.get("streaming"))

        result = await call_next(**kwargs)
        if streaming and isinstance(result, AsyncIterator):
            result = await _consume_or_passthrough_async(result)
        return _listview_apply(
            result,
            lv_state,
            filter_mode=filter_mode,
            fields_mode=fields_mode,
            pagination_mode=pagination_mode,
            format_hint=format_hint,
        )

    return _lv_mw


__all__ = ["list_view_apply_factory"]
