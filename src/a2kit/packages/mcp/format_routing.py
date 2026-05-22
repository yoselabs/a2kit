"""Format-routing middleware — compresses the MCP ``content`` channel (ADR 0014)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastmcp.server.middleware import Middleware

from a2kit.packages.formatter import render_plain

if TYPE_CHECKING:
    from fastmcp.server.middleware import MiddlewareContext

    from a2kit.packages.formatter import Consumer, EncodingPlan

_log = logging.getLogger(__name__)
_WARN_ONCE: set[str] = set()


class FormatRoutingMiddleware(Middleware):
    """Re-derive the MCP ``content`` channel from a tool's :class:`EncodingPlan`.

    Added before ``ListViewMiddleware`` so its post-call processing runs
    *after* list-view projection — ``content`` is always derived from the
    final ``structured_content``.
    """

    def __init__(
        self,
        *,
        plans: dict[str, EncodingPlan],
        consumer: Consumer,
        compact: bool = False,
    ) -> None:
        self._plans = plans
        self._consumer: Consumer = consumer
        self._compact = compact

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: Any,
    ) -> Any:
        result = await call_next(context)

        # Only the `llm` consumer compresses. `code` / `machine` want the
        # structure uncompressed — the middleware is a no-op for them.
        if self._consumer != "llm":
            return result

        tool_name = getattr(context.message, "name", None)
        if not tool_name:
            return result

        plan = self._plans.get(tool_name)
        structured = getattr(result, "structured_content", None)

        try:
            # Re-derive the compressed `content` for a tabular result.
            new_content: Any = None
            if plan is not None and plan.kind != "json" and isinstance(structured, dict):
                if plan.kind == "tsv":
                    if "result" in structured:
                        new_content = render_plain(structured["result"], plan)
                else:  # page-tsv / envelope — the BaseModel envelope itself
                    new_content = render_plain(structured, plan)

            if self._compact:
                # `--compact`: drop `structuredContent` entirely for
                # non-conformant MCP clients that mishandle dual channels.
                content = new_content if new_content is not None else result.content
                return type(result)(
                    content=content,
                    structured_content=None,
                    meta=getattr(result, "meta", None),
                )

            if new_content is None:
                # Nothing tabular to recompress — both channels already fine.
                return result
            return type(result)(
                content=new_content,
                structured_content=structured,
                meta=getattr(result, "meta", None),
            )
        except Exception as exc:  # noqa: BLE001 -- middleware must not raise; degrade observably
            key = f"{tool_name}::format-routing"
            if key not in _WARN_ONCE:
                _WARN_ONCE.add(key)
                _log.warning(
                    "FormatRoutingMiddleware: content re-derivation failed for %s: %s",
                    tool_name,
                    exc,
                )
            return result


__all__ = ["FormatRoutingMiddleware"]
